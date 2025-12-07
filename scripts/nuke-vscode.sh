#!/bin/bash
# Nuke all VSCode remote server state
# Use when VSCode remote gets into a bad state

echo "Killing vscode-server processes..."
pkill -f vscode-server 2>/dev/null || true

echo "Removing stale IPC sockets..."
rm -f /run/user/1000/vscode-ipc-*.sock 2>/dev/null

echo "Done. Reconnect from VSCode to start fresh."
