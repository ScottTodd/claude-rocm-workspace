---
repositories:
  - therock        # Will move guidelines here once tested
  - claude-rocm-workspace  # Current development location
---

# Code Review Guidelines

**Status:** In progress
**Priority:** P2 (Medium)
**Started:** 2026-01-12

## Overview

Create actionable code review guidelines that serve two audiences:
1. **Human contributors** - Quick-scan checklists for self-review before submitting PRs
2. **Claude Code** - Prescriptive rules for automated focused reviews

The guidelines live in `reviews/guidelines/` and integrate with the existing
review system in `reviews/README.md`.

## Goals

- [x] Create initial structure with pr_hygiene.md, tests.md, pr_patterns.md
- [x] Add summary/TOC to each page for quick scanning
- [x] Add exemptions for trivial changes (avoid busy-work)
- [x] Tailor test duration guidance for superproject context
- [ ] Streamline docs for human scanning vs tool prescriptiveness
- [ ] Create documentation.md guidelines
- [ ] Create security.md guidelines
- [ ] Add summary/TOC to pr_patterns.md
- [ ] Test guidelines with actual PR reviews
- [ ] Move to TheRock repository once validated

## Context

### Background

Started from raw notes in `reviews/raw_notes.md` capturing review criteria learned
from experience. Goal is to formalize these into structured guidelines that:
- Help contributors self-review (reduce reviewer burden)
- Enable automation (bot for hygiene checks, Claude for focused reviews)
- Shift burden to PR authors ("author provides, reviewer verifies")

### Related Work
- `reviews/README.md` - Main review system documentation
- `reviews/REVIEW_TYPES.md` - Review type definitions
- TheRock style guides in `docs/development/style_guides/`

### Directories/Files Involved
```
reviews/guidelines/
  pr_hygiene.md      # Bot-enforceable gatekeeping
  tests.md           # Test review checklist
  pr_patterns.md     # Pattern detection → guidelines mapping
reviews/raw_notes.md # Source notes (not committed)
```

## Investigation Notes

### 2026-01-12 - Initial Implementation

Created three guideline files:

**pr_hygiene.md** - Gatekeeping rules for PR quality
- Title format, description completeness, testing evidence, metrics
- Self-evident changes exemption to avoid busy-work
- Auto-comment templates for eventual bot integration
- Summary table with links as TOC

**tests.md** - Test review checklist
- PR description requirements (author provides duration/metrics)
- Coverage, quality, determinism, runnability checks
- Adapted for superproject context (relative duration vs absolute thresholds)
- Exemptions for trivial test changes

**pr_patterns.md** - Pattern detection
- Maps PR types (tests, dependencies, reverts, etc.) to relevant guidelines
- Detection rules based on files changed, title, description
- Pattern matrix for quick reference

## Decisions & Trade-offs

- **Decision:** Author provides metrics, reviewer verifies
  - **Rationale:** Saves reviewer time, ensures authors actually run tests
  - **Alternatives considered:** Reviewer extracts from CI logs (slower, duplicates work)

- **Decision:** Relative test duration thresholds vs absolute
  - **Rationale:** TheRock is a superproject with 100k+ tests per subproject
  - **Alternatives considered:** Absolute thresholds (don't apply uniformly)

- **Decision:** Self-evident changes exempt from detailed descriptions
  - **Rationale:** Avoid busy-work for typo fixes, version bumps
  - **Alternatives considered:** Require everything (creates friction)

## Next Steps

1. [ ] Streamline documentation for dual audience (human scan vs tool rules)
2. [ ] Add summary/TOC to pr_patterns.md
3. [ ] Create documentation.md with info density, code block, link checks
4. [ ] Create security.md with secrets, permissions, injection checks
5. [ ] Test with actual PR reviews to validate usefulness
6. [ ] Move to TheRock repo once stable

## Future Considerations

- Bot integration for pr_hygiene.md auto-comments
- Per-subproject test duration baselines
- Integration with GitHub Actions for automated checks
