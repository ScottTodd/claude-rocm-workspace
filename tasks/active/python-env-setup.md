---
repositories:
  - claude-rocm-workspace
---

# Python Environment Setup for Claude Code

**Status:** Not started
**Priority:** P3 (Low)
**Started:** 2026-01-15

## Overview

Set up a Python virtual environment for this Claude Code workspace so that tools like `pytest` are available when Claude runs commands. Currently pytest isn't installed in the system Python, causing test runs to fall back to `unittest`.

## Goals

- [ ] Create a Python virtual environment in this workspace
- [ ] Install required packages (pytest, etc.)
- [ ] Create a launcher script to activate venv before launching Claude
- [ ] Document the setup process

## Context

### Background

When running tests, Claude attempted:
```
python -m pytest build_tools/github_actions/tests/github_actions_utils_test.py
```

But got:
```
No module named pytest
```

Had to fall back to `python -m unittest` which works but is less ergonomic.

### Prior Art

A coworker had a script at `scripts/claude.sh` (deleted in commit history) that:
1. Deactivated any existing Python venv
2. Activated a workspace-local venv at `$WORKSPACE_DIR/venv/`
3. Set up ccache via `setup_ccache.py`
4. Launched `claude` in the workspace directory

Reference: `git show 1cb9e4b02a7314a893b07e0de9620670f28753fc:scripts/claude.sh`

### Directories/Files Involved
```
D:/projects/claude-rocm-workspace/
  scripts/           # Launcher scripts (to create)
  venv/              # Virtual environment (to create)
  requirements.txt   # Package list (to create)
```

## Implementation Plan

### 1. Create requirements.txt

```
pytest
# Add other packages as needed
```

### 2. Create virtual environment

```bash
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Linux/macOS
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Create launcher script

**Windows (`scripts/claude.ps1`):**
```powershell
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceDir = Split-Path -Parent $ScriptDir

# Activate venv
& "$WorkspaceDir\venv\Scripts\Activate.ps1"

# Launch Claude
Set-Location $WorkspaceDir
claude $args
```

**Linux/macOS (`scripts/claude.sh`):**
```bash
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(dirname "$SCRIPT_DIR")"

# Deactivate any active venv
[[ -n "$VIRTUAL_ENV" ]] && deactivate 2>/dev/null || true

# Activate workspace venv
source "$WORKSPACE_DIR/venv/bin/activate"

cd "$WORKSPACE_DIR"
exec claude "$@"
```

### 4. Add to .gitignore

```
venv/
```

## Next Steps

1. [ ] Decide on required packages for requirements.txt
2. [ ] Create venv and install packages
3. [ ] Create launcher script(s)
4. [ ] Test that pytest works when Claude is launched via the script
5. [ ] Update CLAUDE.md with setup instructions if needed
