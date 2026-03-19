# PR Review: [rocprofiler-sdk] Update RPATH for rocprofv3-list-avail

* **PR:** [#3996](https://github.com/ROCm/TheRock/pull/3996)
* **Author:** jbonnell-amd (Jason Bonnell)
* **Branch:** `users/jbonnell-amd/rocprofiler-sdk-rpath-updates` → `main`
* **Reviewed:** 2026-03-19
* **Status:** OPEN

---

## Summary

This PR fixes a runtime issue where `rocprofv3-list-avail` (and `librocprofiler-sdk-tool-kokkosp.so`) could not find sysdeps shared libraries without manually setting `LD_LIBRARY_PATH`. The fix adds `THEROCK_INSTALL_RPATH_ORIGIN` properties for these two targets in the post-hook, and adds `therock_test_validate_shared_lib` tests for all shared libraries in the `lib/` and `lib/rocprofiler-sdk/` directories.

**Net changes:** +21 lines, -0 lines across 2 files

---

## Overall Assessment

**✅ APPROVED** - Clean, targeted fix that follows existing patterns exactly.

**Strengths:**

- Correctly identifies the root cause: libraries in `lib/rocprofiler-sdk/` need explicit RPATH origin since they're in a non-standard location
- Follows the established pattern used by the existing `rocprofiler-sdk-tool` entry and other post-hooks (e.g., `post_hook_amdsmi.cmake`, `post_hook_fusilliprovider.cmake`)
- Adds validation tests for both the standard `lib/` and non-standard `lib/rocprofiler-sdk/` directories
- PR body includes clear before/after testing with specific run-ids

**Issues:** None blocking.

---

## Detailed Review

### 1. `profiler/post_hook_rocprofiler-sdk.cmake`

The two new `set_target_properties()` calls follow the exact same pattern as the existing entry for `rocprofiler-sdk-tool`. The `lib/rocprofiler-sdk` origin path is correct — these libraries live in a subdirectory and need the RPATH to resolve back to `lib/` (and `lib/rocm_sysdeps/lib/`) for their dependencies.

No issues.

### 2. `profiler/CMakeLists.txt` — Validate shared lib tests

Two `therock_test_validate_shared_lib()` blocks are added after `therock_cmake_subproject_activate(rocprofiler-sdk)`. This placement is consistent with how other subprojects add validation tests.

The first block validates standard-path libraries:
- `librocprofiler-sdk.so`
- `librocprofiler-sdk-roctx.so`
- `librocprofiler-sdk-rocpd.so`
- `librocprofiler-sdk-rocattach.so`

The second block validates non-standard-path libraries in `lib/rocprofiler-sdk/`:
- `libgotcha.so`
- `librocprofiler-sdk-tool.so`
- `librocprofiler-sdk-tool-kokkosp.so`
- `librocprofv3-list-avail.so`

### 💡 SUGGESTION: Placement of validation tests relative to activate

The test calls are placed after `therock_cmake_subproject_activate()` but before the next section comment block. Other usages in the codebase (e.g., `dctools/CMakeLists.txt`, `debug-tools/CMakeLists.txt`) also place them after activate, so this is consistent. No change needed — just noting the pattern is followed.

### 💡 SUGGESTION: Missing trailing newline in post-hook

The post-hook file doesn't end with a trailing newline after the last `)`. This is minor but some linting tools flag it. The existing file already lacked a trailing newline, so this doesn't introduce a new issue.

---

## Recommendations

### ✅ Recommended:

1. Verify that the CMake target names `rocprofiler-sdk-tool-kokkosp` and `rocprofv3-list-avail` match exactly what the rocprofiler-sdk build produces (the PR author has confirmed these work via CI run 23164830024).

### 💡 Consider:

1. No additional suggestions — the change is minimal and well-targeted.

---

## Testing Recommendations

- Build with `THEROCK_ENABLE_ROCPROFV3=ON` and verify `ctest` passes the new `validate_shared_lib` tests
- Confirm `rocprofv3-avail list` works without `LD_LIBRARY_PATH` set (author reports this was verified)

---

## Conclusion

**Approval Status: ✅ APPROVED**

This is a clean, well-scoped fix. It applies the existing RPATH origin pattern to two additional targets and adds validation tests. The approach is consistent with how other non-standard-path libraries are handled in the build system.
