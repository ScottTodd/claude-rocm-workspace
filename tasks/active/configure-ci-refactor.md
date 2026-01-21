---
repositories:
  - therock
---

# Refactor configure_ci.py for Clarity and Extensibility

**Status:** Not started
**Priority:** P2 (Medium)
**Started:** 2025-01-21
**Target:** TBD

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

Current `matrix_generator()` structure (lines 378-631):
1. **Lines 398-437**: Trigger type detection, lookup matrix selection
2. **Lines 439-478**: Workflow dispatch handling (families + test labels)
3. **Lines 480-528**: Pull request handling (PR labels → targets + tests)
4. **Lines 530-548**: Push handling (long-lived vs regular branches)
5. **Lines 550-558**: Schedule handling (nightly runs)
6. **Lines 560-580**: Deduplication of targets/tests
7. **Lines 582-631**: Matrix expansion (targets → matrix rows with variants)

Key observations:
- Trigger handlers are interleaved with shared setup code
- Label parsing logic is inline rather than extracted
- Matrix expansion is separate concern from target selection

## Decisions & Trade-offs

*To be filled in during implementation*

## Code Changes

### Files Modified
*To be filled in during implementation*

### Testing Done
*To be filled in during implementation*

## Blockers & Issues

None currently identified.

## Resources & References

- [configure_ci.py](../TheRock/build_tools/github_actions/configure_ci.py)
- [configure_ci_test.py](../TheRock/build_tools/github_actions/tests/configure_ci_test.py)
- [amdgpu_family_matrix.py](../TheRock/build_tools/github_actions/amdgpu_family_matrix.py)
- [fetch_test_configurations.py](../TheRock/build_tools/github_actions/fetch_test_configurations.py)

## Next Steps

1. [ ] Review proposed refactoring approach
2. [ ] Implement Phase 1: Extract trigger handlers
3. [ ] Update tests to cover extracted functions
4. [ ] Implement Phase 2: Structured label processing (if beneficial)
5. [ ] Document extension points for future opt-in/opt-out work

## Completion Notes

<!-- Fill this in when task is done -->
