---
repositories:
  - claude-rocm-workspace
---

# Python Environment Setup for Claude Code

- **Status:** Complete
- **Priority:** P3 (Low)
- **Started:** 2026-01-15

## Overview

Set up a Python virtual environment for this Claude Code workspace so that tools like `pytest` are available when Claude runs commands. Currently pytest isn't installed in the system Python, causing test runs to fall back to `unittest`.

## Goals

- [x] Create a Python virtual environment in this workspace
- [x] Install required packages (pytest, etc.)
- [x] Create a launcher script to activate venv before launching Claude
- [x] Document the setup process

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
  scripts/claude.bat   # Launcher script (created)
  3.12.venv/           # Virtual environment (created)
  ../TheRock/requirements.txt  # Using TheRock's existing requirements
```

## Implementation Notes

**Deviation from original plan:** Instead of creating a separate `requirements.txt`, we reuse TheRock's existing `requirements.txt` which already includes pytest and other needed tools.

### Actual setup (Windows)

```powershell
cd D:\projects\claude-rocm-workspace
py -V:3.12 -m venv 3.12.venv
.\3.12.venv\Scripts\activate.bat
pip install -r ..\TheRock\requirements.txt
```

### Launcher script

Created `scripts/claude.bat` - a batch file that activates the venv and launches Claude with all arguments passed through.

### .gitignore

The venv directory pattern (`*.venv/`) should be in `.gitignore`.

## Completion Checklist

1. [x] Decide on required packages - reused TheRock's requirements.txt
2. [x] Create venv and install packages
3. [x] Create launcher script (Windows batch file)
4. [x] Test that pytest works when Claude is launched via the script
5. [x] Document setup in README.md

## Future Work

- [ ] Add Linux/macOS launcher script (`scripts/claude.sh`) if needed
