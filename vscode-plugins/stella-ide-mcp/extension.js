// Stella IDE MCP Server - VSCode Extension
// Pure JavaScript, no npm dependencies
// Uses only Node.js built-ins + VSCode API

const vscode = require('vscode');
const http = require('http');
const { exec } = require('child_process');
const path = require('path');
const url = require('url');

let server = null;
let outputChannel = null;

// MCP Tool definitions
const TOOLS = [
    {
        name: 'openFile',
        description: 'Open a file in VSCode editor',
        inputSchema: {
            type: 'object',
            properties: {
                path: { type: 'string', description: 'Absolute path to the file' },
                line: { type: 'number', description: 'Optional line number to jump to' }
            },
            required: ['path']
        }
    },
    {
        name: 'openDiff',
        description: 'Open a file in diff view comparing to a git ref',
        inputSchema: {
            type: 'object',
            properties: {
                path: { type: 'string', description: 'Absolute path to the file' },
                ref: { type: 'string', description: 'Git ref to compare against (default: HEAD)' }
            },
            required: ['path']
        }
    },
    {
        name: 'getChangedFiles',
        description: 'Get list of files changed between two git refs',
        inputSchema: {
            type: 'object',
            properties: {
                repoPath: { type: 'string', description: 'Path to git repository' },
                fromRef: { type: 'string', description: 'Base ref (default: HEAD~1)' },
                toRef: { type: 'string', description: 'Target ref (default: HEAD)' }
            },
            required: ['repoPath']
        }
    },
    {
        name: 'openChangedFiles',
        description: 'Open all changed files in diff view',
        inputSchema: {
            type: 'object',
            properties: {
                repoPath: { type: 'string', description: 'Path to git repository' },
                fromRef: { type: 'string', description: 'Base ref (default: HEAD~1)' },
                toRef: { type: 'string', description: 'Target ref (default: HEAD)' },
                newWindow: { type: 'boolean', description: 'Move diffs to a new window' }
            },
            required: ['repoPath']
        }
    },
    {
        name: 'runCommand',
        description: 'Run a VSCode command by ID',
        inputSchema: {
            type: 'object',
            properties: {
                command: { type: 'string', description: 'VSCode command ID' },
                args: { type: 'array', description: 'Optional command arguments' }
            },
            required: ['command']
        }
    }
];

// Tool implementations
async function openFile(args) {
    const uri = vscode.Uri.file(args.path);
    const doc = await vscode.workspace.openTextDocument(uri);
    const editor = await vscode.window.showTextDocument(doc);

    if (args.line) {
        const position = new vscode.Position(args.line - 1, 0);
        editor.selection = new vscode.Selection(position, position);
        editor.revealRange(new vscode.Range(position, position), vscode.TextEditorRevealType.InCenter);
    }

    return { success: true, path: args.path };
}

async function openDiff(args) {
    const ref = args.ref || 'HEAD';
    const filePath = args.path;
    const uri = vscode.Uri.file(filePath);

    // Construct git URI for the old version
    // Format: git:/path/to/file?{"path":"/path/to/file","ref":"REF"}
    const query = JSON.stringify({ path: filePath, ref: ref });
    const gitUri = vscode.Uri.parse(`git:${filePath}?${encodeURIComponent(query)}`);

    // Open diff
    const fileName = path.basename(filePath);
    await vscode.commands.executeCommand('vscode.diff', gitUri, uri, `${fileName} (${ref} ↔ Working)`);

    return { success: true, path: filePath, ref };
}

function getChangedFiles(args) {
    return new Promise((resolve, reject) => {
        const fromRef = args.fromRef || 'HEAD~1';
        const toRef = args.toRef || 'HEAD';
        const repoPath = args.repoPath;

        exec(
            `git diff --name-only ${fromRef}..${toRef}`,
            { cwd: repoPath },
            (error, stdout, stderr) => {
                if (error) {
                    reject(new Error(`git diff failed: ${stderr}`));
                    return;
                }
                const files = stdout.trim().split('\n').filter(f => f);
                resolve({
                    files: files.map(f => path.join(repoPath, f)),
                    fromRef,
                    toRef
                });
            }
        );
    });
}

async function openChangedFiles(args) {
    const result = await getChangedFiles(args);
    const opened = [];

    // If newWindow requested, create a new editor group first so we only move the diffs
    if (args.newWindow) {
        await vscode.commands.executeCommand('workbench.action.newGroupRight');
    }

    for (const filePath of result.files) {
        try {
            await openDiff({ path: filePath, ref: args.fromRef || 'HEAD~1' });
            opened.push(filePath);
        } catch (e) {
            // Skip files that can't be opened (deleted, etc.)
            log(`Skipping ${filePath}: ${e.message}`);
        }
    }

    // Move the new group to its own window
    if (args.newWindow && opened.length > 0) {
        await vscode.commands.executeCommand('workbench.action.moveEditorGroupToNewWindow');
    }

    return { opened, total: result.files.length, newWindow: !!args.newWindow };
}

async function runCommand(args) {
    const result = await vscode.commands.executeCommand(args.command, ...(args.args || []));
    return { success: true, command: args.command, result: result ?? null };
}

// Tool dispatcher
async function callTool(name, args) {
    switch (name) {
        case 'openFile': return openFile(args);
        case 'openDiff': return openDiff(args);
        case 'getChangedFiles': return getChangedFiles(args);
        case 'openChangedFiles': return openChangedFiles(args);
        case 'runCommand': return runCommand(args);
        default: throw new Error(`Unknown tool: ${name}`);
    }
}

// Logging
function log(msg) {
    if (outputChannel) {
        outputChannel.appendLine(`[${new Date().toISOString()}] ${msg}`);
    }
}

// HTTP request body parser
function parseBody(req) {
    return new Promise((resolve, reject) => {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', () => {
            try {
                resolve(body ? JSON.parse(body) : {});
            } catch (e) {
                reject(new Error('Invalid JSON'));
            }
        });
        req.on('error', reject);
    });
}

// SSE session management
const sessions = new Map();

function createSession() {
    const id = Math.random().toString(36).substring(2, 15);
    sessions.set(id, { messages: [], res: null });
    return id;
}

function sendSSE(sessionId, data) {
    const session = sessions.get(sessionId);
    if (session && session.res) {
        session.res.write(`data: ${JSON.stringify(data)}\n\n`);
    }
}

// MCP Protocol handlers
function handleInitialize(params) {
    return {
        protocolVersion: '2024-11-05',
        capabilities: {
            tools: {}
        },
        serverInfo: {
            name: 'stella-ide-mcp',
            version: '0.0.1'
        }
    };
}

function handleListTools() {
    return { tools: TOOLS };
}

async function handleCallTool(params) {
    const { name, arguments: args } = params;
    log(`Calling tool: ${name} with args: ${JSON.stringify(args)}`);

    try {
        const result = await callTool(name, args || {});
        return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
    } catch (e) {
        log(`Tool error: ${e.message}`);
        return { content: [{ type: 'text', text: `Error: ${e.message}` }], isError: true };
    }
}

// HTTP Server
function startServer(port) {
    server = http.createServer(async (req, res) => {
        const parsedUrl = url.parse(req.url, true);

        // CORS headers
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

        if (req.method === 'OPTIONS') {
            res.writeHead(204);
            res.end();
            return;
        }

        try {
            // SSE endpoint
            if (parsedUrl.pathname === '/sse' && req.method === 'GET') {
                const sessionId = createSession();

                res.writeHead(200, {
                    'Content-Type': 'text/event-stream',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive'
                });

                sessions.get(sessionId).res = res;

                // Send endpoint info
                res.write(`event: endpoint\ndata: /message?sessionId=${sessionId}\n\n`);

                req.on('close', () => {
                    sessions.delete(sessionId);
                    log(`Session ${sessionId} closed`);
                });

                log(`New SSE session: ${sessionId}`);
                return;
            }

            // Message endpoint
            if (parsedUrl.pathname === '/message' && req.method === 'POST') {
                const sessionId = parsedUrl.query.sessionId;
                if (!sessionId || !sessions.has(sessionId)) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'Invalid session' }));
                    return;
                }

                const body = await parseBody(req);
                log(`Received: ${JSON.stringify(body)}`);

                let result;
                switch (body.method) {
                    case 'initialize':
                        result = handleInitialize(body.params);
                        break;
                    case 'notifications/initialized':
                        result = {};
                        break;
                    case 'tools/list':
                        result = handleListTools();
                        break;
                    case 'tools/call':
                        result = await handleCallTool(body.params);
                        break;
                    default:
                        result = { error: `Unknown method: ${body.method}` };
                }

                const response = {
                    jsonrpc: '2.0',
                    id: body.id,
                    result
                };

                // Send via SSE
                sendSSE(sessionId, response);

                res.writeHead(202, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ status: 'accepted' }));
                return;
            }

            // Health check
            if (parsedUrl.pathname === '/health') {
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ status: 'ok', tools: TOOLS.length }));
                return;
            }

            // 404
            res.writeHead(404, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Not found' }));

        } catch (e) {
            log(`Error: ${e.message}`);
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: e.message }));
        }
    });

    server.listen(port, '127.0.0.1', () => {
        log(`MCP server listening on http://127.0.0.1:${port}`);
        vscode.window.showInformationMessage(`Stella IDE MCP server running on port ${port}`);
    });

    server.on('error', (e) => {
        log(`Server error: ${e.message}`);
        vscode.window.showErrorMessage(`Stella IDE MCP server error: ${e.message}`);
    });
}

function stopServer() {
    if (server) {
        server.close();
        server = null;
        log('Server stopped');
    }
}

// Extension activation
function activate(context) {
    outputChannel = vscode.window.createOutputChannel('Stella IDE MCP');
    log('Extension activating...');

    const config = vscode.workspace.getConfiguration('stella-ide-mcp');
    const port = config.get('port', 3742);

    startServer(port);

    // Status command
    const statusCmd = vscode.commands.registerCommand('stella-ide-mcp.status', () => {
        if (server && server.listening) {
            vscode.window.showInformationMessage(
                `Stella IDE MCP server running on port ${port}. Tools: ${TOOLS.map(t => t.name).join(', ')}`
            );
        } else {
            vscode.window.showWarningMessage('Stella IDE MCP server is not running');
        }
    });

    context.subscriptions.push(statusCmd, { dispose: stopServer });

    log('Extension activated');
}

function deactivate() {
    stopServer();
}

module.exports = { activate, deactivate };
