---
repositories:
  - therock
---

# Fix CI Concurrency Groups

- **Status:** Not started
- **Priority:** P2 (Medium)
- **Started:** 2026-03-04

## Overview

The concurrency groups in CI workflows have two issues:
1. `workflow_dispatch` runs on the same branch cancel each other (blocks parallel prebuilt testing)
2. PR events (`labeled`/`opened`/`synchronize`) can overlap and cancel each other in `ci.yml`

## Goals

- [ ] Fix concurrency groups so multiple `workflow_dispatch` runs don't cancel each other
- [ ] Fix PR double-trigger cancellation in `ci.yml`
- [ ] Apply consistent pattern across `ci.yml` and `multi_arch_ci.yml`

## Context

### Current State

`multi_arch_ci.yml` uses:
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.number || github.sha }}
  cancel-in-progress: true
```

For `workflow_dispatch`, `event.number` is empty so it falls back to `github.sha`.
Multiple dispatches on the same branch share the SHA and cancel each other.

For PRs, `labeled` and `synchronize` events fire at the same time, share the
same `event.number`, and one cancels the other — but the Actions UI shows the
cancelled run, confusing PR authors.

### Recommended Pattern

From GitHub docs and common practice:
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.head_ref || github.run_id }}
  cancel-in-progress: true
```

- **PRs:** `head_ref` is the branch name — all events for the same PR share a
  group, so only the last-triggered one runs. Avoids the double-trigger race.
- **Push:** `head_ref` is empty, falls through to `run_id` (unique per run).
  No cancellation between pushes.
- **workflow_dispatch:** Same as push — `run_id` is unique, so parallel
  dispatches never cancel each other.

Trade-off: loses push-cancellation (new push to main won't cancel old one),
but main pushes should generally run to completion anyway.

### Files to Change

- `.github/workflows/multi_arch_ci.yml`
- `.github/workflows/ci.yml` (same pattern, same issues)

### References

- [GitHub Docs: Control concurrency](https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs)
- Discovered during multi-arch-prebuilt testing (2026-03-04)

## Next Steps

1. [ ] Update `multi_arch_ci.yml` concurrency group
2. [ ] Update `ci.yml` concurrency group
3. [ ] Verify PR behavior (no double-cancel)
4. [ ] Verify workflow_dispatch allows parallel runs
