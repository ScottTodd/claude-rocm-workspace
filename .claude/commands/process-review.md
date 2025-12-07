---
description: Find and address RVW review comments
allowed-tools: Bash(python:*), Read, Edit, Bash(git:*), mcp__vscode__openFile
---

Find and process all RVW review comments. Argument: `{{arg1}}` (optional repo alias)

## Comment Types

- `// RVW: comment` - Discuss with user, propose fix, wait for confirmation
- `// RVWY: comment` - YOLO mode: make the fix without asking

## 1. Discover comments

```bash
python scripts/review.py comments {{arg1}}
```

Parse the JSON output to get list of `{file, line, comment, yolo}`.

## 2. If no comments found

Say "No RVW comments found." and stop.

## 3. For each comment

### If `yolo: true` (RVWY)

1. Read the context around the comment
2. Make the fix you think is best
3. Remove the RVWY comment marker
4. Briefly report what you did (one line)

### If `yolo: false` (RVW)

1. Open the file at the comment line in VSCode:
   ```
   mcp__vscode__openFile(path=<file>, line=<line>)
   ```

2. Show:
   - **File:line** and the comment text
   - Read the surrounding context (5 lines before/after)
   - Propose a specific fix

3. Wait for user confirmation before proceeding.

4. After user confirms:
   - Make the fix
   - Remove the RVW comment marker

## 4. After all comments addressed

```bash
git add -A
git commit -m "Address review feedback"
```

Ask: "Stage for another review round (`/stage-review`) or ready to finalize?"
