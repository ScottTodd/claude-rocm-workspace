# Task: Create Skill Definitions for Review Commands

**Status:** Complete
**Started:** 2026-01-08
**Last Updated:** 2026-01-12
**Completed:** 2026-01-12

---

## Objective

Create shorthand skill commands for the review system documented in `reviews/`:

1. `/review-pr {LINK_TO_GITHUB_PR}` - Review a GitHub pull request
2. `/review-branch` - Review the current local branch

---

## Background

We have a comprehensive review system in `reviews/` with:
- **Review guidelines:** `reviews/REVIEW_GUIDELINES.md`
- **Review types:** `reviews/REVIEW_TYPES.md` (comprehensive, style, tests, documentation, architecture, security, performance)
- **Example reviews:** `reviews/pr_2547.md`, `reviews/pr_2761.md`, `reviews/local_001_remove-pytorch-patch-support.md`

Currently, reviews are triggered by natural language like:
- "Review my current branch"
- "Review PR #1234"
- "Do a style review of my changes"
- "Run tests and documentation reviews in parallel"

We want to add formal skill definitions for common review operations.

---

## Research Needed

### Where are skills defined?

Need to determine:
1. Where skill definition files are stored (likely in `.claude/` directory)
2. What format skill definitions use (likely markdown with frontmatter or JSON)
3. How skills invoke agents or tools
4. Whether skills can accept parameters (like the PR link)

### Existing skills to reference

From CLAUDE.md and the Skill tool description, we know these skills exist:
- `task` - Switch to working on a specific task (project)
- `wip` - Quick WIP commit

Need to find their definitions to use as templates.

### Directory exploration

The workspace `.claude/` directory contains:
- `active-task` - likely current task tracking
- `agents/` - agent definitions or history
- `commands/` - possibly where skills are defined?
- `settings.json` and `settings.local.json` - configuration

Need to explore:
- `D:/projects/claude-rocm-workspace/.claude/commands/` - likely location for skill definitions
- User's global `.claude/` at `/c/Users/Nod-Shark16/.claude` - might have skill examples

---

## Proposed Skill Definitions

### `/review-branch`

**Purpose:** Review the current local branch comprehensively

**Behavior:**
1. Get current branch name
2. Determine next local review counter (scan `reviews/local_*` files)
3. Create review file: `reviews/local_{COUNTER}_{branch-name}.md`
4. Run comprehensive review following `reviews/REVIEW_GUIDELINES.md`
5. Report findings and location of review file

**Parameters:** None (uses current branch)

**Example usage:**
```
/review-branch
```

### `/review-pr {LINK_TO_GITHUB_PR}`

**Purpose:** Review a GitHub pull request

**Behavior:**
1. Extract PR number from GitHub URL
2. Fetch PR details using `gh` CLI
3. Create review file: `reviews/pr_{NUMBER}.md`
4. Run comprehensive review following `reviews/REVIEW_GUIDELINES.md`
5. Report findings and location of review file

**Parameters:**
- `{LINK_TO_GITHUB_PR}` - Full GitHub PR URL (e.g., `https://github.com/ROCm/TheRock/pull/2761`)

**Example usage:**
```
/review-pr https://github.com/ROCm/TheRock/pull/2761
```

---

## Implementation Steps

1. **Explore skill system:**
   - Check `D:/projects/claude-rocm-workspace/.claude/commands/`
   - Look at existing skill definitions (`wip`, `task`)
   - Understand skill file format and structure

2. **Create `/review-branch` skill:**
   - Write skill definition file
   - Test with current branch
   - Verify review file is created correctly

3. **Create `/review-pr` skill:**
   - Write skill definition file
   - Add parameter parsing for GitHub URL
   - Test with a real PR (maybe PR #2761)
   - Verify review file is created correctly

4. **Document skills:**
   - Update CLAUDE.md with new review skills
   - Add examples to `reviews/README.md`
   - Consider adding to Review Workflow section in CLAUDE.md

---

## Additional Considerations

### Focused review variants

Might also want skills for focused reviews:
- `/review-branch style` - style-only review
- `/review-branch tests` - test-only review
- `/review-pr {URL} architecture` - architecture-only review

Or keep it simple and stick with natural language for focused reviews.

### Parallel reviews

Should we support:
- `/review-branch --parallel style,tests,docs`

Or again, keep natural language: "Run style, tests, and docs reviews in parallel"

### Re-reviews

After fixing issues, users might want:
- `/re-review` - review changes since last review

Start simple: comprehensive reviews only. Can expand later.

---

## Next Session TODO

1. Explore `.claude/commands/` directory structure
2. Find and read existing skill definitions as templates
3. Create `review-branch.md` skill definition
4. Create `review-pr.md` skill definition
5. Test both skills
6. Update documentation

---

## Related Files

- `reviews/README.md` - Review system overview
- `reviews/REVIEW_GUIDELINES.md` - How to structure reviews
- `reviews/REVIEW_TYPES.md` - Different review focus areas
- `CLAUDE.md` - Project conventions (Review Workflow section)
- `.claude/commands/review-pr.md` - PR review skill
- `.claude/commands/review-branch.md` - Branch review skill

---

## Completion Summary

### What was implemented

1. **`/review-pr` skill** (`.claude/commands/review-pr.md`)
   - Takes GitHub PR URL as first argument
   - Optional review types as additional arguments
   - Uses `gh` CLI to fetch PR details and diff
   - Follows `reviews/REVIEW_GUIDELINES.md` for output format
   - Outputs to `reviews/pr_{NUMBER}.md`

2. **`/review-branch` skill** (`.claude/commands/review-branch.md`)
   - Reviews current local branch against main
   - Optional review types as arguments
   - Auto-increments local review counter
   - Outputs to `reviews/local_{COUNTER}_{branch-name}.md`

3. **Conversational interface** (`CLAUDE.md` Review Workflow section)
   - Documents trigger phrases for reviews
   - Lists available review types
   - Shows example commands
   - Explains output file naming
   - Includes severity level reference

### Design decisions

- **Flexible review types**: Both skills accept optional type arguments, defaulting to comprehensive review
- **Natural language support**: CLAUDE.md documents conversational triggers so users can say "review this PR: URL" without using slash commands
- **Consistent with existing skills**: Format matches `wip.md` and `task.md` patterns
- **Extensible**: Adding new review types just requires updating `REVIEW_TYPES.md` - skills reference it dynamically
