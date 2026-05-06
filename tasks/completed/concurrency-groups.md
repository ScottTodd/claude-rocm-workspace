---
repositories:
  - therock
---

# Fix CI Concurrency Groups

- **Status:** Complete
- **Priority:** P2 (Medium)
- **Started:** 2026-03-04

## Overview

The concurrency groups in CI workflows have two issues:
1. `workflow_dispatch` runs on the same branch cancel each other (blocks parallel prebuilt testing)
2. PR events (`labeled`/`opened`/`synchronize`) can overlap and cancel each other in `ci.yml`

## Goals

- [x] Fix concurrency groups so multiple `workflow_dispatch` runs don't cancel each other
- [x] Apply consistent pattern across `ci.yml` and `multi_arch_ci.yml`
- [ ] Fix PR `labeled` double-trigger (follow-up, IREE pattern)

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

## Testing (2026-05-06)

All testing done on ScottTodd/TheRock fork, `multi_arch_ci.yml` workflow.

| Scenario | Runs | Result |
|----------|------|--------|
| workflow_dispatch x2 same branch (runs 15+16) | Both completed success | No cancellation — unique `run_id` groups |
| workflow_dispatch x2 same branch (runs 17+18) | Both queued (runner capacity) | No cancellation — correct |
| PR open + labeled (PR #7, runs 19+20) | Run 19 cancelled, run 20 active | Dedup by `head_ref` works |
| PR open then force-push (PR #8, runs 21+22) | Run 21 cancelled, run 22 took over | Dedup by `head_ref` works |

Not explicitly tested (low risk, same mechanism):
- Push to main (falls through to `run_id`, same as workflow_dispatch)
- `ci.yml` (identical change)

## Known Limitation: `labeled` Double-Trigger

The `head_ref || run_id` fix does NOT prevent the `opened` + `labeled`
double-trigger when a PR is opened with a label already attached. Both
events fire simultaneously, one gets cancelled, and the cancelled run's
CI Summary (with `if: always()`) reports failure in the PR checks.

Example: upstream PR #5080 — CI and Multi-Arch CI each got 2 runs,
pre-commit and Unit Tests (which don't trigger on `labeled`) got 1 each.

**Fix:** Separate `labeled` into its own trigger workflow that re-runs the
existing CI run (IREE pattern: `benchmark_trigger.yml` at commit 089f3d60).
This is a separate PR.

## Next Steps

1. [x] Update `multi_arch_ci.yml` concurrency group
2. [x] Update `ci.yml` concurrency group
3. [x] Verify PR behavior (no double-cancel)
4. [x] Verify workflow_dispatch allows parallel runs
5. [x] Send PR upstream — PR #5082 (merged)
6. [ ] Follow-up PR: separate `labeled` trigger workflow (IREE pattern)
