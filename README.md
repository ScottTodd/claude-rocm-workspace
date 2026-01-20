# ROCm Claude Code Workspace

A meta-workspace for using Claude Code to work on
[ROCm/TheRock](https://github.com/ROCm/TheRock) and related projects. This
repository serves as a "control center" that provides centralized context,
tooling, and documentation for AI-assisted development.

## Why a Meta-Workspace?

Build infrastructure work on ROCm involves multiple scattered repositories and
build directories. Rather than making any single ROCm project the Claude Code
workspace, this separate meta-repository:

- Provides centralized context and documentation for Claude Code
- Maps out where all the various directories live (see
  [`directory-map.md`](/directory-map.md))
- Contains workflows, notes, and helper scripts
- Stays version-controlled without polluting the actual ROCm repositories

## Directory Structure

```
claude-rocm-workspace/
├── CLAUDE.md              # Project context and instructions for Claude Code
├── ACTIVE-TASKS.md        # Current task tracking
├── directory-map.md       # Map of ROCm directories on your system
│
├── tasks/                 # Task management
│   ├── active/            # Currently active tasks
│   └── completed/         # Archived completed tasks
│
├── reviews/               # Code review system
│   ├── README.md          # Quick start guide
│   ├── REVIEW_GUIDELINES.md
│   ├── REVIEW_TYPES.md
│   ├── guidelines/        # Domain-specific review checklists
│   ├── pr_*.md            # PR reviews
│   └── local_*.md         # Local branch reviews
│
├── plans/                 # Implementation plans and design docs
├── reports/               # Audit reports and analyses
│
└── .claude/               # Claude Code configuration
    ├── commands/          # Slash commands (/task, /review-pr, etc.)
    ├── agents/            # Custom subagents (build-infra, ci-pipeline)
    └── settings.json      # Workspace settings
```

## Key Features

### Code Review System

The [`reviews/`](/reviews/) directory contains a structured code review system.

**Quick start:**
```bash
/review-pr https://github.com/ROCm/TheRock/pull/1234  # Review a PR
/review-branch                                        # Review current branch
/review-branch style tests                            # Focused reviews
```

See [`reviews/README.md`](/reviews/README.md) for full documentation.

### Task Management

Track and switch between multiple tasks without losing context.

**Commands:**
```bash
/task task-name                    # Switch to a task
```

**Workflow:**
1. Create `tasks/active/your-task.md` (use
   [`example-task.md`](/tasks/active/example-task.md) as template)
2. Add to `ACTIVE-TASKS.md`
3. Switch with `/task your-task` or "I'm working on your-task"
4. Move to `tasks/completed/` when done

### Custom Agents

Domain-specific subagents in [`.claude/agents/`](/.claude/agents/):

| Agent | Purpose |
|-------|---------|
| [`build-infra`](/.claude/agents/build-infra.md) | CMake, meson, pkg-config, ROCm build patterns |
| [`ci-pipeline`](/.claude/agents/ci-pipeline.md) | GitHub Actions, CI/CD workflows |

### Slash Commands

Available commands in [`.claude/commands/`](/.claude/commands/):

| Command | Description |
|---------|-------------|
| [`/task <name>`](/.claude/commands/task.md) | Switch to a task |
| [`/review-pr <URL>`](/.claude/commands/review-pr.md) | Review a GitHub PR |
| [`/review-branch`](/.claude/commands/review-branch.md) | Review current local branch |
| [`/wip`](/.claude/commands/wip.md) | Quick WIP commit |

## Setup

1. Clone this repository
2. Update `directory-map.md` with your actual directory paths
3. Customize `CLAUDE.md` with your project-specific context
4. Run Claude Code from this directory

```bash
cd /path/to/claude-rocm-workspace
claude
```

## Adapting for Your Project

This workspace pattern can be adapted for any multi-repository project:

1. Fork this repository
2. Replace ROCm-specific content in `CLAUDE.md`
3. Update `directory-map.md` for your environment
4. Customize the review guidelines for your project's conventions
5. Add task templates relevant to your work
