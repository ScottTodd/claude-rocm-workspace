---
description: Set VSCode integration mode (local or remote)
allowed-tools: Write, Bash(mkdir:*)
---

Set VSCode integration mode. Argument: `{{arg1}}` (local | remote)

## Usage

- `/vscode-mode local` - Call `code` directly (same machine)
- `/vscode-mode remote` - Use file watcher (SSH/remote development)

## Action

1. Create `.state/` directory if needed: `mkdir -p .state`
2. Write mode to `.state/vscode-mode`:
   - If `{{arg1}}` is "local": write "local"
   - If `{{arg1}}` is "remote": write "remote"
   - If no arg or invalid: show current mode and usage

## Output

Confirm the mode was set. If remote, remind user to start the watcher:
```
./scripts/vscode-watcher.sh
```
