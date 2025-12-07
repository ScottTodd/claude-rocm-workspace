---
description: Prepare commit stack for PR (milestone review)
allowed-tools: Bash(python:*), Bash(git:*), mcp__vscode__openChangedFiles
---

Prepare for PR with milestone review. Argument: `{{arg1}}` (optional repo alias)

## 1. Show commit stack

```bash
python scripts/review.py stack {{arg1}}
```

Parse the JSON and display the commits since main, showing what will be in the PR.

## 2. Get merge base for diff

```bash
cd <repo_path>
git merge-base HEAD main
```

## 3. Open milestone diff in VSCode

Use MCP to open all changed files since main in diff view:

```
mcp__vscode__openChangedFiles(repoPath=<repo_path>, fromRef=<merge_base>, toRef="HEAD", newWindow=true)
```

## 4. Report

Show:
- Number of commits
- Number of files changed
- Summary stats

Say: "Staged full diff for milestone review. After approval, I can help squash into logical commits for PR."

**STOP and wait for user review.**
