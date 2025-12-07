---
description: Open git diffs in VSCode (requires MCP extension)
allowed-tools: Bash(python:*), mcp__vscode__openChangedFiles
---

Open diffs in VSCode. Arguments: `{{arg1}}` (repo alias or path) `{{arg2}}` (optional: commit count, default 1)

## 1. Resolve repository

Run `python scripts/review.py stack {{arg1}}` to get repo path.

## 2. Open diffs

Use MCP to open changed files in diff view:

```
mcp__vscode__openChangedFiles(repoPath=<repo_path>, fromRef="HEAD~{{arg2 or 1}}", toRef="HEAD", newWindow=true)
```

## 3. Report

Show files opened and confirm they're in diff view.
