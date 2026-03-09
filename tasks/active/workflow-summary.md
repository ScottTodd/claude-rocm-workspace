---
repositories:
  - therock
---

# Workflow Summary Consolidation

- **Status:** In progress
- **Priority:** P2 (Medium)
- **Started:** 2026-03-09

## Overview

The `_summary` gate jobs at the end of `ci.yml`, `multi_arch_ci.yml`, and `unit_test.yml`
duplicate the same jq-based result-checking logic. Consolidate into shared code and improve
the developer experience when builds fail.

## Goals

- [x] Extract shared summary/gate logic so all three workflows call one implementation
- [x] Summary job stays useful as a single "required check" anchor (auto-captures new jobs)
- [ ] Improve failure output: surface which jobs failed and ideally link/excerpt relevant errors
- [x] Keep `if: always()` semantics so the gate detects cancellation as failure

## Context

### Current State

Three workflows have near-identical gate jobs:

| Workflow | Job name | `needs:` | Notes |
|----------|----------|----------|-------|
| `unit_test.yml` | `unit_tests_summary` | `unit_tests` | Simpler jq (no continue-on-error) |
| `ci.yml` | `ci_summary` | `setup`, `linux_build_and_test`, `windows_build_and_test` | Filters `continue_on_error` output |
| `multi_arch_ci.yml` | `ci_summary` | `setup`, `linux_build_and_test`, `windows_build_and_test` | Same as ci.yml, minus debug echo |

All use the pattern: dump `${{ toJson(needs) }}`, pipe through jq, exit 1 if failures.

The `ci.yml` / `multi_arch_ci.yml` versions additionally respect a `continue_on_error` output
from upstream jobs so that "expected failure" variants don't break the gate.

Comment in `unit_test.yml` (line 61) already acknowledges the duplication.

### Design Goals

1. **Required-check anchor**: The summary job lists all other jobs in `needs:`. When new jobs
   are added to a workflow, they get added to `needs:` and are automatically gated — no branch
   protection settings change needed.

2. **Better failure UX**: Today a failing CI run links developers to the summary job, which
   just says "The following jobs failed: X". Developers then have to hunt for the actual error.
   We want to surface actionable information: which step failed, a link to it, and ideally a
   snippet of the error log.

3. **Single implementation**: One place to maintain the gate logic, not three copy-pasted blocks.

### Related Work
- Comment at `unit_test.yml:61` notes code should be shared with `ci_summary`
- Issue tracker: (create tracking issue if desired)

### Directories/Files Involved
```
.github/workflows/ci.yml
.github/workflows/multi_arch_ci.yml
.github/workflows/unit_test.yml
```

## Research

### Community Patterns

**`re-actors/alls-green` action** ([GitHub](https://github.com/re-actors/alls-green)):
- Most popular community solution for gate jobs
- Takes `${{ toJSON(needs) }}`, supports `allowed-failures` and `allowed-skips`
- Produces a Job Summary table showing per-job status
- Requires `if: always()` on the gate job
- Trade-off: adds a third-party action dependency

**`needs.*.result` patterns:**
- Result values: `success`, `failure`, `cancelled`, `skipped`
- `contains(needs.*.result, 'failure')` is the simplest check
- `needs.*` in job-level `if:` includes transitive dependencies (runner #2356)

**`GITHUB_STEP_SUMMARY` for error surfacing:**
- Each job can write markdown to `$GITHUB_STEP_SUMMARY`
- 1 MiB per step, 20 summaries per job
- No API to read one job's summary from another job (community discussion #27649)
- So error surfacing must happen _within each job_, not aggregated by the gate

**Workflow annotations:**
- `::error file=...,line=...::message` creates annotations visible in PR diff view
- Good for build errors pointing to specific files

### Approach Options

#### Option A: Python script called from each workflow

A script in `build_tools/` that:
- Receives `${{ toJSON(needs) }}` as an argument or stdin
- Applies the filtering logic (skip success/skipped, respect continue-on-error)
- Outputs a clear summary and writes to `$GITHUB_STEP_SUMMARY`
- Exits 1 on failure

```yaml
ci_summary:
  if: always()
  needs: [setup, linux_build_and_test, windows_build_and_test]
  runs-on: ubuntu-24.04
  steps:
    - uses: actions/checkout@v4
      with: { sparse-checkout: build_tools }
    - run: echo '${{ toJSON(needs) }}' | python build_tools/ci/workflow_summary.py
```

Pros: Full control, testable, no third-party dep, can add error-surfacing logic later.
Cons: Requires checkout step (adds ~5s), more code to maintain than alls-green.

#### Option B: Use `re-actors/alls-green`

```yaml
ci_summary:
  if: always()
  needs: [setup, linux_build_and_test, windows_build_and_test]
  runs-on: ubuntu-24.04
  steps:
    - uses: re-actors/alls-green@release/v1
      with:
        jobs: ${{ toJSON(needs) }}
        allowed-failures: ...  # map continue_on_error jobs
```

Pros: Zero maintenance, handles edge cases, produces nice summary.
Cons: Third-party dependency, less control over output format, `allowed-failures`
must be listed explicitly (doesn't read `continue_on_error` output dynamically).

#### Option C: Composite action in `.github/actions/workflow-summary/`

A local composite action that wraps the logic:

```yaml
ci_summary:
  if: always()
  needs: [setup, linux_build_and_test, windows_build_and_test]
  runs-on: ubuntu-24.04
  steps:
    - uses: actions/checkout@v4
      with: { sparse-checkout: .github/actions/workflow-summary }
    - uses: ./.github/actions/workflow-summary
      with:
        needs-json: ${{ toJSON(needs) }}
```

Pros: No third-party dep, reusable within repo, can use JS or shell.
Cons: Still needs checkout, composite actions have limitations (no `if:` on steps).

### Improving Failure UX

Since we can't read other jobs' summaries from the gate job, the best approach is:

1. **In the gate job**: Use the GitHub API to fetch failed job names and their URLs,
   then write a markdown summary with direct links.
2. **In build/test jobs**: Each job writes its own `$GITHUB_STEP_SUMMARY` with error
   excerpts (tail of build log, test failures, etc.) — this is orthogonal to the gate.

The gate job can use:
```bash
# Fetch failed jobs and their URLs via GitHub API
gh api repos/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID/jobs \
  --jq '.jobs[] | select(.conclusion == "failure") | "- [\(.name)](\(.html_url))"'
```

This gives developers clickable links directly to the failed jobs.

## Decisions & Trade-offs

- **Decision:** Option A — Python script in `build_tools/github_actions/`
  - **Rationale:** Fits project convention (share code at script level), testable with pytest,
    extensible for future error-surfacing features. alls-green's interface is good inspiration
    but we want full control.
  - **Alternatives rejected:** alls-green (third-party dep, can't dynamically read continue_on_error),
    composite action (limited, still needs checkout)

- **Decision:** Full `actions/checkout` (not sparse)
  - **Rationale:** Checkout is fast enough; sparse-checkout adds complexity for minimal gain.

- **Decision:** Pass `needs` JSON via argparse, not stdin/piping
  - **Rationale:** Cleaner interface, easier to test, avoids shell quoting issues with echo/pipe.

## Implementation Plan

### Phase 1: Consolidate gate logic
1. Choose approach (A, B, or C)
2. Implement shared gate logic
3. Update all three workflows to use it
4. Verify required checks still work

### Phase 2: Improve failure UX
1. Add GitHub API call to gate job to fetch failed job URLs
2. Write markdown summary with links to failed jobs
3. Optionally: add `$GITHUB_STEP_SUMMARY` to build/test jobs for error excerpts

### Phase 3: Error log surfacing (stretch)
1. Build jobs capture last N lines of error output
2. Write to `$GITHUB_STEP_SUMMARY` or upload as artifact
3. Gate job references these in its summary

## PRs

- **#3865** — Phase 1: shared `workflow_summary.py` + workflow wiring
  - Branch: `ci-summary-reuse`
  - `workflow_summary.py`: parses needs JSON, evaluates results (respects continue_on_error),
    colored per-job output
  - All three workflows updated to use it
  - Also fixes `upload_pytorch_manifest_test.py` fork-specific failures (missing `--bucket test`)
  - Tested on fork: https://github.com/ScottTodd/TheRock/actions/runs/22878689515

## Next Steps

1. [x] Decide on approach (A/B/C) — chose A (Python script)
2. [x] Prototype the Python script with tests
3. [x] Update workflows and verify in CI
4. [ ] Merge #3865
5. [ ] Add failure URL linking (Phase 2)
6. [ ] Add `$GITHUB_STEP_SUMMARY` markdown output (Phase 2)
