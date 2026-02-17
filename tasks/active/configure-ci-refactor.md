---
repositories:
  - therock
---

# Refactor configure_ci.py for Clarity and Extensibility

- **Status:** Not started
- **Priority:** P2 (Medium)
- **Started:** 2025-01-21
- **Target:** TBD

## Overview

The `configure_ci.py` script determines what CI jobs run for different GitHub events (PRs, pushes, scheduled runs, workflow_dispatch). The `matrix_generator()` function has grown to ~180 lines handling multiple concerns, making it difficult to understand and extend. This task refactors the code for clarity and prepares it for future opt-in/opt-out mechanisms.

## Goals

- [ ] Extract trigger-specific logic into separate handler functions
- [ ] Improve code organization so developers can easily trace CI behavior
- [ ] Prepare architecture for future opt-in/opt-out mechanisms
- [ ] Maintain backward compatibility (no behavior changes)
- [ ] Keep test coverage intact

## Context

### Background

When debugging CI issues (e.g., understanding why `test:miopen` label triggers full tests), developers need to trace through a large monolithic function. Recent logging improvements help visibility but the code structure still makes it hard to:
1. Understand what happens for a specific trigger type
2. Add new label-based behaviors
3. Implement opt-in/opt-out for specific jobs or tests

### Related Work
- Logging improvements committed in `849ae78c` (Add comprehensive logging to configure_ci.py)
- PR #3018 prompted investigation into label processing visibility
- GitHub Actions logs: https://github.com/ROCm/TheRock/actions/runs/21192383406/job/60961360600

### Directories/Files Involved
```
TheRock/build_tools/github_actions/configure_ci.py
TheRock/build_tools/github_actions/tests/configure_ci_test.py
```

## Proposed Refactoring

### Phase 1: Extract Trigger Handlers

Extract trigger-specific logic from `matrix_generator()` into separate functions:

```python
def _handle_workflow_dispatch(base_args, families, platform, lookup_matrix):
    """Handle workflow_dispatch trigger - returns (target_names, test_names)."""
    ...

def _handle_pull_request(base_args, lookup_matrix):
    """Handle pull_request trigger - returns (target_names, test_names, special_actions)."""
    ...

def _handle_push(base_args, is_long_lived_branch):
    """Handle push trigger - returns target_names."""
    ...

def _handle_schedule():
    """Handle schedule trigger - returns target_names."""
    ...
```

Benefits:
- Each function has single responsibility
- Easier to test individual trigger behaviors
- Clear entry points for future customization

### Phase 2: Improve Label Processing

Consider a structured approach to label parsing:

```python
@dataclass
class LabelActions:
    """Actions derived from PR labels."""
    target_names: List[str]
    test_names: List[str]
    skip_ci: bool = False
    run_all_archs: bool = False

def parse_pr_labels(labels: List[str]) -> LabelActions:
    """Parse PR labels into structured actions."""
    ...
```

### Phase 3: Future Extensibility Hooks

Prepare for opt-in/opt-out mechanisms:
- Job-level opt-out (e.g., `skip:windows` label)
- Test-level opt-out (e.g., `skip-test:rocblas` label)
- Architecture-specific controls

## Investigation Notes

### 2025-01-21 - Initial Analysis

Current `matrix_generator()` structure (lines 250-543, ~295 lines):
1. **Lines 265-273**: Init, branch detection
2. **Lines 276-309**: Trigger type detection, lookup matrix selection
3. **Lines 311-350**: Workflow dispatch handling (families + test labels)
4. **Lines 352-406**: Pull request handling (PR labels → targets + tests)
5. **Lines 408-426**: Push handling (long-lived vs regular branches)
6. **Lines 428-436**: Schedule handling (nightly runs)
7. **Lines 438-458**: Dedup, route to multi-arch or standard expansion
8. **Lines 460-543**: Standard matrix expansion (targets → matrix rows)

### 2026-02-16 - Full style review and coverage analysis

**Style guide violations (see Python style guide checklist):**

Blocking:
- Mutable default args (`base_args={}`, `families={}`) — classic Python bug
- `matrix_generator` is 295 lines (guide says <30 ideal, extract at 100+)
- `main` is 145 lines
- Missing type hints on most functions (5 functions untyped or partially typed)
- `base_args` is untyped dict with 12+ fields threaded through 4 functions — should be dataclass
- Wildcard import `from github_actions_utils import *`

Important:
- `assert` used for input validation (disabled with `-O`)
- Silent error handling: `filter_known_names` line 118 prints warning for unknown name_type instead of raising
- Duplicate code: test label parsing, build_pytorch computation, target list appending
- `label.split(":")` without `maxsplit` — crashes on multiple colons
- Nested `format_variants` function inside `main` — untestable
- `matrix_generator` called with positional args at lines 593-602

**Test coverage: 63% (branch: 65%)**

Untested code paths:
- `main()` — **zero coverage** (lines 552-695, 145 lines)
- `__main__` block — expected, not testable
- `skip-ci` label handling (lines 381-384)
- `run-all-archs-ci` label handling (lines 386-389)
- Workflow dispatch test labels (lines 339-341, 346)
- `expect_failure` from build variant (line 492)
- Non-release variant artifact group naming (line 509)
- `filter_known_names` unknown name_type path (lines 118-119)
- `generate_multi_arch_matrix` edge cases (lines 176, 211)

**Decision: incremental refactoring, not full rewrite.**
`matrix_generator` has enough untested edge cases that rewriting it in one go
is risky. `main()` has zero coverage and could be rewritten freely. Plan:
- Incremental refactoring of `matrix_generator` (extract pieces, add tests for gaps)
- Rewrite `main()` and `__main__` block alongside a `base_args` dataclass
- Standardized `os.environ.get` (done: 4 `os.getenv` calls fixed)

**Motivation: issue #3399** (stage-aware prebuilt artifacts) needs a clean
insertion point between target selection and matrix expansion. The refactoring
creates that seam.

## Decisions & Trade-offs

- Prefer `os.environ.get` over `os.getenv` for consistency — `os.environ` gives
  both `.get()` (optional) and `[]` (required) from one interface
- Incremental refactoring over rewrite — coverage gaps in `matrix_generator`
  make full rewrite risky without adding tests first

## Blockers & Issues

- Refactoring deferred while landing open PRs and fixing #2045 breakage

## Resources & References

- [configure_ci.py](../TheRock/build_tools/github_actions/configure_ci.py)
- [configure_ci_test.py](../TheRock/build_tools/github_actions/tests/configure_ci_test.py)
- [amdgpu_family_matrix.py](../TheRock/build_tools/github_actions/amdgpu_family_matrix.py)
- [fetch_test_configurations.py](../TheRock/build_tools/github_actions/fetch_test_configurations.py)
- [Issue #3399](https://github.com/ROCm/TheRock/issues/3399) — stage-aware prebuilt artifacts (motivating refactor)

## Next Steps

1. [x] Full style review against Python style guide
2. [x] Check test coverage to inform rewrite vs refactor decision
3. [x] Standardize `os.getenv` → `os.environ.get`
4. [ ] Add tests for untested edge cases (skip-ci, run-all-archs-ci, workflow dispatch test labels)
5. [ ] Introduce `base_args` dataclass, rewrite `main()` and `__main__` block
6. [ ] Extract trigger handlers from `matrix_generator`
7. [ ] Extract standard matrix expansion
8. [ ] Deduplicate build_pytorch computation and test label parsing

## Completion Notes

<!-- Fill this in when task is done -->
