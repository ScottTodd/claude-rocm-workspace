# Branch Review: users/scotttodd/artifact-overlap-fixes

* **Branch:** `users/scotttodd/artifact-overlap-fixes`
* **Base:** `main`
* **Reviewed:** 2026-03-06
* **Commits:** 8 branch-specific commits (on top of merged main commits)

---

## Summary

This branch makes `test` components participate in the artifact extends chain (`lib -> run -> dbg -> dev -> doc -> test`), eliminating ~4,988 within-artifact component overlaps. It adds descriptor excludes to route files correctly, wires structure validation tests into all four CI orchestration workflows, and documents the extends chain behavior.

**Net changes:** +632 lines, -17 lines across 22 files (including merged main commits in the diff; branch-specific changes are ~12 files)

---

## Overall Assessment

**✅ APPROVED** - Well-structured change with thorough CI validation. The core fix (one line in artifact_builder.py) is sound, and the descriptor adjustments are individually justified by CI failures. Documentation is comprehensive.

**Strengths:**

- The systemic fix (`test extends doc`) is elegant — one line eliminates thousands of overlaps
- Each descriptor fix is motivated by a real CI failure with linked evidence
- Documentation in artifacts.md is excellent — extends chain, default patterns, and routing guidance
- CI workflow wiring follows existing patterns exactly
- The `platform` input on the structure test workflow correctly handles cross-platform validation

**Issues:**

- None on this branch (one pre-existing annotation issue in test file on main)

---

## Detailed Review

### 1. Core Fix: `artifact_builder.py`

**Well done.** The `ComponentDefaults("test", extends=["doc"])` change is the right fix. The WARNING comment on `run` (lines 53-58) and the explanatory comment on `test` (lines 92-96) are valuable for future maintainers.

No issues found.

### 2. Descriptor Fixes (7 TOML files)

All descriptor changes follow the same pattern: add `exclude` to prevent an earlier component from claiming files that belong in a later component.

Each fix is well-motivated:
- **miopen**: `run` catch-all → exclude `bin/miopen_gtest*`
- **rocprofiler-sdk**: `run` with explicit includes → exclude `share/rocprofiler-sdk/tests/**`
- **base/rocprofiler-register**: `run` catch-all → exclude `share/rocprofiler-register/tests/**`
- **rocrtst**: `run` catch-all → exclude `bin/**`
- **aqlprofile**: `run` catch-all → exclude `share/hsa-amd-aqlprofile/**`
- **rocgdb**: `dev` defaults (`**/include/**`) → exclude `tests/**`
- **hipSPARSE in blas**: `dev` explicit `**/*.cmake` → exclude `share/hipsparse/test/**`

No issues found. The exclude patterns are appropriately scoped.

### 3. `test_artifact_structure.py`

Not modified on this branch — merged to main via PR #3802. The test docstring update (`31378ac5`) is on this branch but applies to the copy already on main.

Note: `_format_component_overlaps` has a `-> str` annotation but returns `tuple[int, str]`. This is a pre-existing issue on main, not introduced here.

### 4. CI Workflow Wiring (4 workflow files + `test_artifacts_structure.yml`)

The validation jobs in all four CI workflows (`ci_linux`, `ci_windows`, `multi_arch_ci_linux`, `multi_arch_ci_windows`) follow the exact same pattern as existing test jobs:
- `needs:` the build job
- Same `if:` condition (failure/cancelled/prebuilt/expect_failure)
- Passes `artifact_group`, `artifact_run_id`, `platform`

The `platform` input on `test_artifacts_structure.yml` correctly handles the cross-platform case (Linux runners validating Windows artifacts).

Removing `amdgpu_targets` is correct — the structure test doesn't need per-target filtering.

No issues found.

### 5. `install_rocm_from_artifacts.py`

The `rocprofiler-compute_run` addition and the explanatory comment about `_run` fetch behavior are correct. The existing `_run` appends for rocgdb, miopen, rocprofiler-sdk, and rocprofiler-systems are appropriately preserved.

No issues found.

### 6. `docs/development/artifacts.md`

Excellent documentation additions:
- Extends chain diagram
- Default patterns table
- WARNING callout about `run` catch-all
- Two concrete routing approaches with real examples (rocBLAS, rocSPARSE, MIOpen, rocrtst)

The examples reference actual descriptors in the codebase, which is ideal for maintainability.

No issues found.

---

## Recommendations

### ❌ REQUIRED (Blocking):

None.

### ✅ Recommended:

1. Fix `_format_component_overlaps` return type annotation on main (`-> str` should be `-> tuple[int, str]`) — pre-existing, not from this branch

### 💡 Consider:

1. After rebasing onto main (which has the mxDataGenerator fix), verify that both structure tests pass with 0 overlaps before marking the PR as ready for review.
2. Note in the PR description that the structure test always runs on Linux runners, even for Windows artifacts.

### 📋 Future Follow-up:

1. Audit remaining bare `[components.run."..."]` entries across all descriptors (tracked in task file)
2. Target-specific content validation (kpack namespacing) — approach 4 from the task
3. Consider whether `test` should remain in the extends chain or revert to standalone with allowed duplicates (alternative approach noted in task)
4. The `ci_summary` jobs in `ci.yml` and `multi_arch_ci.yml` may need updating to include the new validation jobs in their dependency/result checks

---

## Testing Recommendations

1. Rebase onto main and trigger full CI (ci.yml + multi_arch_ci.yml) to verify:
   - Structure validation passes (0 cross-artifact, 0 within-artifact overlaps)
   - All existing functional tests pass (aqlprofile, rocgdb, rocprofiler_compute, rocrtst)
   - rccl failure is confirmed as pre-existing/flaky
2. Trigger a manual `workflow_dispatch` of `test_artifacts_structure.yml` with `platform: windows` to verify Windows artifact validation works

---

## Conclusion

**Approval Status: ✅ APPROVED**

The branch is well-structured and addresses a real problem (thousands of silent file overlaps) with a clean systemic fix. The descriptor adjustments are individually motivated by CI failures, and the documentation is thorough. Ready for PR after rebasing onto main and confirming CI passes.
