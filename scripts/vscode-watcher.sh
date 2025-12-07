#!/bin/bash
# VSCode command watcher
# Run this in VSCode's integrated terminal to enable Claude to open files/diffs
#
# Usage: ./scripts/vscode-watcher.sh

WORKSPACE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="$WORKSPACE_DIR/.state"
COMMANDS_FILE="$STATE_DIR/vscode-commands"

mkdir -p "$STATE_DIR"
touch "$COMMANDS_FILE"

echo "VSCode watcher started"
echo "  Watching: $COMMANDS_FILE"
echo "  Press Ctrl+C to stop"
echo ""

# Check for inotifywait
if ! command -v inotifywait &> /dev/null; then
    echo "ERROR: inotifywait not found. Install with: sudo apt install inotify-tools"
    exit 1
fi

# Function to process pending commands
process_commands() {
    if [[ -s "$COMMANDS_FILE" ]]; then
        echo "--- Executing commands ---"
        while IFS= read -r cmd; do
            [[ -z "$cmd" || "$cmd" =~ ^# ]] && continue
            echo "> $cmd"
            eval "$cmd"
        done < "$COMMANDS_FILE"

        # Clear the file after execution
        > "$COMMANDS_FILE"
        echo "--- Done ---"
        echo ""
    fi
}

# Process any pending commands first
process_commands

# Watch for changes and execute commands
while true; do
    inotifywait -q -e modify "$COMMANDS_FILE" > /dev/null 2>&1
    process_commands
done
