# Stella IDE MCP Server

Zero-dependency VSCode extension that runs an MCP server for Claude Code integration.

## Loading the Extension

### Option 1: Symlink to extensions folder (recommended)

```bash
# For VSCode Remote SSH:
ln -s /home/stella/claude-rocm-workspace/vscode-plugins/stella-ide-mcp ~/.vscode-server/extensions/stella-ide-mcp

# For local VSCode:
ln -s /path/to/stella-ide-mcp ~/.vscode/extensions/stella-ide-mcp
```

Reload VSCode window: `Ctrl+Shift+P` → "Developer: Reload Window"

### Option 2: Launch VSCode with extension path

```bash
code --extensionDevelopmentPath=/home/stella/claude-rocm-workspace/vscode-plugins/stella-ide-mcp
```

## Configure Claude Code

```bash
claude mcp add --transport sse vscode http://127.0.0.1:3742/sse
```

Restart Claude Code. Tools will appear as `mcp__vscode__*`.

## Verify It's Working

1. In VSCode: `Ctrl+Shift+P` → "Stella IDE MCP: Show Status"
2. Check output: `View` → `Output` → select "Stella IDE MCP" from dropdown
3. Health check: `curl http://127.0.0.1:3742/health`

## Available Tools

| Tool | Description |
|------|-------------|
| `openFile` | Open a file, optionally at a specific line |
| `openDiff` | Open file in diff view vs a git ref |
| `getChangedFiles` | List files changed between git refs |
| `openChangedFiles` | Open all changed files in diff view |
| `runCommand` | Execute any VSCode command by ID |

## Configuration

In VSCode settings:

- `stella-ide-mcp.port`: Server port (default: 3742)

## No npm Required

This extension uses only:
- Node.js built-ins (`http`, `child_process`, `path`)
- VSCode API (provided by VSCode)

No `npm install`, no `node_modules`, no build step.
