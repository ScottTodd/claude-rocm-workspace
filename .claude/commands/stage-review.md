---
description: Stage changes and open VSCode diffs for review
allowed-tools: Bash(git:*), Bash(python:*), Read, mcp__vscode__openChangedFiles
---

Stage changes for review. Argument: `{{arg1}}` (optional repo alias or path)

## 1. Resolve repository

Run `python scripts/review.py stack {{arg1}}` to resolve the repo and get current state.
Parse the JSON output to get the repo path.

## 2. Create WIP commit (if needed)

```bash
cd <repo_path>
git status
# If uncommitted changes exist:
git add -A
git commit -m "WIP: staged for review"
```

## 3. Open diffs in VSCode

Use the MCP tool to open all changed files in diff view in a new window:

```
mcp__vscode__openChangedFiles(repoPath=<repo_path>, fromRef="HEAD~1", toRef="HEAD", newWindow=true)
```

## 4. Report results

Report:
- Repository and branch
- Number of files opened in diff view
- Commit info

Then say: "Staged for review. Add `// RVW:` comments, then `/process-review`"

**STOP and wait for user to review.**
