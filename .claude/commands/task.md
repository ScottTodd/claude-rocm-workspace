---
description: Switch to working on a specific task (project)
allowed-tools: Read, Write
---

Switch to working on task `{{arg1}}`:

1. Read the task file at `tasks/active/{{arg1}}.md`
2. If the task has a `repositories:` field in YAML frontmatter, note which repos are involved

Review the task context including:
- Current status and goals
- Previous investigation notes
- Any blockers or open questions
- Next steps
- **Repositories involved** (from frontmatter, if present)

Then ask me what I'd like to work on for this task.
