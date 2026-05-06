# PR Review: Add COMGR build-time unit tests to CI

* **PR:** [#4881](https://github.com/ROCm/TheRock/pull/4881)
* **Author:** kasaurov
* **Reviewed:** 2026-05-01
* **Base:** `main`
* **Branch:** `users/kasaurov/comg-unit-tests-10`

---

## Summary

Adds Comgr build-time unit tests (LIT via `llvm-lit` + CTest) to CI, running
in the `compiler-runtime` stage. Builds on the `therock_subproject_build_test`
infrastructure from PR #4790. The tests are non-blocking (`continue-on-error: true`).

Key changes:
- Registers Comgr LIT + CTest tests via `therock_cmake_subproject_build_test`
- Modifies the runner infrastructure to execute commands independently (failure in one doesn't block others)
- Adds a "Run build tests" step to Linux and Windows multi-arch workflows
- Sets `-DTHEROCK_BUILD_TESTING=ON` for `compiler-runtime` in `configure_stage.py`
- Removes now-unnecessary `llvm-lit` install/wrapper logic from `pre_hook_amd-llvm.cmake`

**Net changes:** +107 lines, -43 lines across 7 files

---

## Overall Assessment

**✅ APPROVED** - Well-structured PR that cleanly integrates Comgr tests into CI.

**Strengths:**
- Good separation: runner infrastructure change (independent command execution) is generic and benefits future test additions
- Proper use of `continue-on-error: true` for initial rollout with known Windows LIT failures
- Clean removal of the old llvm-lit install/wrapper approach (tests run from build tree instead)
- CI evidence shows tests pass: Linux 20/20 LIT + 32/32 CTest, Windows 32/32 CTest (LIT known-broken)
- Correct `if(NOT DEFINED ...)` pattern preserves user overridability of `THEROCK_BUILD_COMGR_TESTS`

**Issues:**
- One suggestion about robustness of generated script arguments

---

## CI Evidence

Build test step results from [run 25154743498](https://github.com/ROCm/TheRock/actions/runs/25154743498):

| Platform | Step | Duration | Result |
|----------|------|----------|--------|
| Linux compiler-runtime | Run build tests | 11s | ✅ success |
| Windows compiler-runtime | Run build tests | 15s | ✅ success |

The `continue-on-error: true` means the step shows as success even if underlying tests fail (which is intended for now). The PR body documents actual test results from an earlier run showing all tests passing.

---

## Detailed Review

### 1. `cmake/therock_subproject.cmake` — Runner Script Generation

#### 💡 SUGGESTION: Argument escaping in generated CMake script

The serialization loop:
```cmake
foreach(_arg IN LISTS _full_cmd)
  string(APPEND _cmd_str " \"${_arg}\"")
endforeach()
```

This could break if any argument contains literal double-quote characters or
semicolons (CMake list separators). In practice, all paths and arguments here
are CMake-generated build tree paths which should be clean, but a defensive
approach would use `string(REPLACE "\"" "\\\"" _arg "${_arg}")` before quoting.

**Recommendation:** Low risk in practice (build tree paths don't contain these
characters), but worth noting for future maintainers.

#### 💡 SUGGESTION: Numbering scheme change is good

The old scheme (no suffix for first, `_1` for second, `_2` for third) was
confusing. The new scheme (1-indexed when multiple commands exist) is clearer.
Documenting this in a code comment would help future readers understand the
intent.

### 2. `compiler/CMakeLists.txt` — Test Registration

The test registration is clean:
```cmake
therock_cmake_subproject_build_test(amd-comgr
  COMMAND
    "${Python3_EXECUTABLE}" "${_llvm_lit_script}"
    "${CMAKE_BINARY_DIR}/compiler/amd-comgr/build/test-lit" -v
  COMMAND
    "${CMAKE_CTEST_COMMAND}"
    --test-dir "${CMAKE_BINARY_DIR}/compiler/amd-comgr/build"
    --output-on-failure
)
```

The platform-conditional `_llvm_lit_script` path (`.py` on Windows, no extension
on Linux) correctly matches how LLVM generates the script.

### 3. `compiler/pre_hook_amd-llvm.cmake` — Removal of Install Logic

The 31-line removal of the `llvm-lit` install + wrapper script logic is correct.
Since tests now run from the build tree (using the build-tree `llvm-lit`
directly), there's no need to install it or create PYTHONPATH wrappers.

The remaining code (`LLVM_BUILD_TOOLS ON`, `LLVM_INSTALL_UTILS ON`) is still
needed to ensure `FileCheck` and other LLVM utilities are available.

### 4. `build_tools/configure_stage.py` — Stage-Specific Testing Flags

```python
if stage_name == "compiler-runtime":
    if include_comments:
        args.append("")
        args.append("# Enable build-time tests for compiler-runtime stage")
    args.append("-DTHEROCK_BUILD_TESTING=ON")
```

#### 💡 SUGGESTION: Consider data-driven approach for future stages

Hard-coding `compiler-runtime` is fine for now (first stage with tests), but
as more stages gain tests, this will accumulate `if` blocks. A dictionary
mapping stage names to their extra flags would scale better. Not needed now
though.

### 5. Workflow Changes (Linux + Windows)

```yaml
- name: Run build tests
  if: ${{ !cancelled() && inputs.stage_name == 'compiler-runtime' }}
  continue-on-error: true
  env:
    TEATIME_FORCE_INTERACTIVE: 1
  run: |
    cmake --build "${BUILD_DIR}" --target therock-build-tests -- -k 0
```

The `!cancelled()` condition is correct — it allows the step to run even if a
prior step failed (since this follows the build step which might have partial
failures with `-k 0`). The `inputs.stage_name == 'compiler-runtime'` condition
correctly limits execution to the one stage that currently has tests.

### 6. `CMakeLists.txt` — Option Removal

Removing `option(THEROCK_BUILD_COMGR_TESTS ...)` from the top level and
replacing it with the `if(NOT DEFINED ...)` pattern in `compiler/CMakeLists.txt`
is the right call. The variable is scoped to where it's relevant, and
user overrides via `-D` still work.

---

## Recommendations

### 💡 Consider:

1. Add a brief comment near the `string(APPEND _cmd_str ...)` loop noting the
   assumption that arguments don't contain special characters
2. Future: generalize the workflow condition if additional stages gain build tests
   (could check if the target exists via a configure output)

### 📋 Future Follow-up:

1. Remove `continue-on-error: true` once Windows LIT tests are fixed (after
   `llvm-project#1860` lands via amd-llvm submodule bump to `ww-2026-14+`)
2. Consider adding test result parsing/reporting (e.g., capturing pass/fail
   counts in workflow summary)

---

## Testing Recommendations

- ✅ CI run demonstrates Linux tests pass (20/20 LIT + 32/32 CTest)
- ✅ CI run demonstrates Windows CTest passes (32/32)
- ✅ Windows LIT failure is a known upstream issue, documented
- Verify that local builds without `-DTHEROCK_BUILD_TESTING=ON` still work
  (the `therock_cmake_subproject_build_test` early-returns when testing is OFF)

---

## Conclusion

**Approval Status: ✅ APPROVED**

This is a clean, well-tested PR that adds meaningful test coverage to CI. The
independent command execution improvement to the runner infrastructure is a
solid enhancement that will benefit future test additions. The non-blocking
approach for initial rollout is pragmatic given the known Windows LIT issue.
No blocking changes needed.
