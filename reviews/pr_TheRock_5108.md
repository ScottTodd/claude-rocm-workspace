# PR Review: #5108 - [rocprofiler-compute] Fix RPATH for test binary in non-default install location

**URL:** https://github.com/ROCm/TheRock/pull/5108
**Author:** vedithal-amd (with Claude co-authoring)
**Status:** OPEN
**Branch:** `users/vedithal-amd/rocprofiler-compute-fix-native-tool-tests`

## Summary

Fixes RPATH for `test-rocprofiler-compute-tool`, which installs to
`libexec/rocprofiler-compute/tests/` instead of `bin/`. TheRock's global
post-subproject RPATH hook assumes executables go to `bin/`, so the relative
RPATH was wrong and the binary couldn't find `librocprofiler-compute-tool.so`
at runtime.

Two changes:
1. `INSTALL_RPATH_DIRS "lib/rocprofiler-compute"` on the subproject declaration
2. New `post_hook_rocprofiler-compute.cmake` setting `THEROCK_INSTALL_RPATH_ORIGIN`

## Assessment

The changes are correct and follow the established pattern. No issues found.

### What's good

- Mirrors the adjacent `post_hook_rocprofiler-sdk.cmake` pattern
- `if(TARGET ...)` guard handles `THEROCK_BUILD_TESTING=OFF` cleanly (better
  than `post_hook_rocprofiler-sdk.cmake` which lacks this guard)
- Clean separation: `INSTALL_RPATH_DIRS` for the lib search path,
  `THEROCK_INSTALL_RPATH_ORIGIN` for the binary's actual location

### Minor observations

- 💡 SUGGESTION: `post_hook_rocprofiler-sdk.cmake` doesn't use `if(TARGET ...)`
  guards on its three targets. If those targets are conditionally built (e.g.,
  gated on testing flags), the same pattern from this PR should be backported.
  Low priority since those targets currently always exist when the subproject
  is enabled.

## Broader analysis: other targets that may be affected

### RPATH machinery recap

TheRock's `therock_global_post_subproject.cmake` overwrites per-target
`INSTALL_RPATH` for all executables and shared libraries. It computes RPATH
relative to an assumed origin:
- Executables: `THEROCK_INSTALL_RPATH_EXECUTABLE_DIR` (defaults to `bin/`)
- Shared libs: `THEROCK_INSTALL_RPATH_LIBRARY_DIR` (defaults to `lib/`)

If a target installs to a different location, it needs
`THEROCK_INSTALL_RPATH_ORIGIN` set via a post hook.

### Currently handled (have post hooks)

| Post hook | Target(s) | Origin |
|-----------|-----------|--------|
| `post_hook_rocprofiler-sdk.cmake` | `rocprofiler-sdk-tool`, `rocprofiler-sdk-tool-kokkosp`, `rocprofv3-list-avail` | `lib/rocprofiler-sdk` |
| `post_hook_amdsmi.cmake` | `amdsmitst` | `share/amd_smi/tests` |
| `post_hook_hrx.cmake` | `hrx_cts_*` | `lib/hrx/share/hrx-cts` |
| `post_hook_fusilliprovider.cmake` | `fusilli_plugin` | `lib/hipdnn_plugins/engines` |
| `post_hook_hipblasltprovider.cmake` | `hipblaslt_plugin` | `lib/hipdnn_plugins/engines` |
| `post_hook_rocr-debug-agent-tests.cmake` | `rocm-debug-agent-test` | transitional (raw INSTALL_RPATH) |
| **This PR** | `test-rocprofiler-compute-tool` | `libexec/rocprofiler-compute/tests` |

### Potentially missing

These targets install to non-standard locations but lack post hooks:

| Subproject | Target(s) | Install destination | Risk |
|------------|-----------|-------------------|------|
| roctracer | `codeobj_test` (shared lib), all test executables | `share/roctracer/test` | ⚠️ IMPORTANT if tests are built. Executables assumed at `bin/`, actually at `share/roctracer/test/`. |
| aqlprofile | test executables | `share/aqlprofile` | ⚠️ IMPORTANT if tests are built (`-DAQLPROFILE_BUILD_TESTS=${THEROCK_BUILD_TESTING}`). |
| rocprofiler (v1) | `ctrl` (libexec), `rocprofiler_tool` (lib/rocprofiler) | `libexec/rocprofiler`, `lib/rocprofiler` | 📋 FUTURE WORK — v1 rocprofiler is not currently a TheRock subproject (it lives in rocm-systems but isn't declared in TheRock's CMakeLists). Would matter if it's ever integrated. |

The roctracer and aqlprofile cases would produce incorrect RPATH for test
binaries when `THEROCK_BUILD_TESTING=ON`. Whether these cause actual runtime
failures depends on whether CI runs these tests from the installed location
(vs. directly from the build directory).

## Unit test coverage for RPATH correctness

### Current state

There is no automated validation of RPATH correctness. The existing
`therock_test_validate_shared_lib` / `validate_shared_library.py` only checks
that a `.so` can be dlopen'd — it doesn't verify executable RPATH entries.

### Proposed: RPATH validation script

A post-build validation script could catch these issues at CI time rather than
waiting for runtime failures. Approach:

```python
# build_tools/validate_rpath.py
# Walk dist/<subproject>/stage/, find all ELF executables/shared libs,
# read RUNPATH via readelf/pyelftools, verify each $ORIGIN-relative
# path resolves to a directory that actually exists in the stage tree.
```

This could be wired up similar to `therock_test_validate_shared_lib`:

```cmake
# cmake/therock_testing.cmake
function(therock_test_validate_rpath)
  # For each ELF binary in the dist tree, verify RPATH entries resolve
  add_test(
    NAME therock-validate-rpath-${subproject}
    COMMAND "${Python3_EXECUTABLE}"
      "${THEROCK_SOURCE_DIR}/build_tools/validate_rpath.py"
      "${dist_path}"
  )
endfunction()
```

### Alternative: CMake-time validation

A lighter approach: add validation in `therock_global_post_subproject.cmake`
that compares the target's actual install destination (from `RUNTIME_OUTPUT_DIRECTORY`
or the `install()` command) against the computed origin. This is tricky because
CMake doesn't reliably expose the install destination as a target property at
configure time — it's set in the `install()` command, which is a separate
code path.

### Recommendation

The script approach is more practical. It could run as a CTest after
`ninja install` and would catch:
1. Missing `THEROCK_INSTALL_RPATH_ORIGIN` for non-standard install locations
2. Missing `INSTALL_RPATH_DIRS` for non-standard lib directories
3. Stale RPATH entries pointing to nonexistent directories

This would be a meaningful follow-up issue/PR separate from this fix.
