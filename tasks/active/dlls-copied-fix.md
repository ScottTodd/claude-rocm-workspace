# Fix DLLS_COPIED Guard Bug in rocm-libraries

## Problem

Multiple projects in rocm-libraries use a `DLLS_COPIED` guard variable with
`PARENT_SCOPE` inside a CMake `function()` to ensure DLL/file copying happens
only once. When the function is called from **another function** (2+ depth),
the `PARENT_SCOPE` only reaches the intermediate function's scope — not the
directory scope where subsequent calls originate. The variable is lost when the
intermediate function returns, so the guard never fires and **every test target
gets duplicate POST_BUILD copy commands**.

When multiple test targets link in parallel, their POST_BUILD commands race to
write the same files to the same destination, causing intermittent
`Error copying file (if different)` failures on Windows CI (#763, PR #3483).

## Evidence

### Minimal reproduction (dlls_copied_repro/)
Proves the scoping bug in isolation — all 6 targets enter the guard block.

### Actual rocPRIM configure log
```
[DLLS_COPY_DEBUG test/rocprim] POST_BUILD copy added to target: test_internal_merge_path
[DLLS_COPY_DEBUG test/rocprim] POST_BUILD copy added to target: test_basic
[DLLS_COPY_DEBUG test/rocprim] POST_BUILD copy added to target: test_arg_index_iterator
... (66 total — every single test target)
```

Compared to `test/` where the guard works (1 function depth):
```
[DLLS_COPY_DEBUG test/] POST_BUILD copy added to target: test_hip_api
[DLLS_COPY_DEBUG test/] DLLS_COPIED already defined, skipping target: test_hip_async_copy
[DLLS_COPY_DEBUG test/] DLLS_COPIED already defined, skipping target: test_ordered_block_id
```

## Affected Files

### BROKEN — guard doesn't work (nested function calls)

| File | Guard var | Call chain | Targets |
|------|-----------|------------|---------|
| rocprim/test/rocprim/CMakeLists.txt | DLLS_COPIED_2 | add_rocprim_test → add_rocprim_test_internal | ~66 |
| hipcub/test/hipcub/CMakeLists.txt | DLLS_COPIED | add_hipcub_test → add_hipcub_test_internal | ~48 |

### WORKS — guard functions correctly (single function depth from file scope)

| File | Guard var | Call pattern | Targets |
|------|-----------|-------------|---------|
| rocprim/test/CMakeLists.txt | DLLS_COPIED | add_hip_test (1 depth) | ~5 |
| rocprim/example/CMakeLists.txt | DLLS_COPIED | add_example (1 depth) | 3 |
| rocprim/benchmark/CMakeLists.txt | DLLS_COPIED | add_rocprim_benchmark (1 depth) | 53 |
| rocthrust/test/CMakeLists.txt | DLLS_COPIED | add_rocthrust_test (1 depth) | ~170 |
| rocthrust/test/hipstdpar/CMakeLists.txt | DLLS_COPIED | add_hipstdpar_test (1 depth) | 2 |
| hipcub/benchmark/CMakeLists.txt | DLLS_COPIED | add_hipcub_benchmark (1 depth) | 36 |
| rocrand/test/CMakeLists.txt | DLLS_COPIED_TESTS | add_test_target (1 depth) | foreach |
| rocrand/benchmark/CMakeLists.txt | DLLS_COPIED_BENCHMARKS | add_rocrand_benchmark (1 depth) | foreach |
| rocrand/test/package/CMakeLists.txt | DLLS_COPIED | file-scope foreach | foreach |
| hiprand/test/CMakeLists.txt | DLLS_COPIED | file-scope foreach | foreach |
| hiprand/test/package/CMakeLists.txt | DLLS_COPIED | file-scope foreach | foreach |

### SEPARATE BUG — guard permanently disabled

| File | Issue |
|------|-------|
| rocthrust/examples/CMakeLists.txt | `set(DLLS_COPIED OFF)` at file scope makes the variable DEFINED, so `NOT DEFINED DLLS_COPIED` is always FALSE. Copies never happen. Harmless but wrong. |

## Fix Strategy

The files being copied are:
- `${CMAKE_SOURCE_DIR}/rtest.*` — static source-tree files (always available)
- `${HIP_DIR}/bin/*.dll` — pre-built HIP DLLs (available at configure time in
  standalone builds; glob returns empty in TheRock builds)

Both are available at configure time. There is no reason to use POST_BUILD.

### Fix for the 2 broken files (rocprim, hipcub)

1. Remove the `DLLS_COPIED` / `DLLS_COPIED_2` block from the inner function
2. Add a `file(COPY)` at file scope (outside any function), before the test
   registrations:

```cmake
# Copy test support files at configure time.
# Previously this was a POST_BUILD command inside a function, but the
# PARENT_SCOPE guard didn't propagate through nested function calls,
# causing every test target to get duplicate copy commands that raced
# on parallel builds (see TheRock#763).
if(WIN32)
  file(GLOB _test_support_files
    ${HIP_DIR}/bin/*.dll
    ${CMAKE_SOURCE_DIR}/rtest.*
  )
  if(_test_support_files)
    file(COPY ${_test_support_files} DESTINATION ${PROJECT_BINARY_DIR}/test/rocprim)
  endif()
endif()
```

### Fix for the "works but fragile" files

For the single-depth cases that currently work, apply the same `file(COPY)`
pattern. This is optional but makes the code consistent and removes the
fragile guard pattern entirely. Lower priority.

### Fix for rocthrust/examples

Change `set(DLLS_COPIED OFF)` to just remove the line, and apply the same
`file(COPY)` pattern. Or leave as-is since examples probably don't need the
copied files. Low priority.

## Files to Change

### Must fix (broken guards causing CI flakes)

1. `rocprim/test/rocprim/CMakeLists.txt`
   - Remove DLLS_COPIED_2 block from `add_rocprim_test_internal()` (lines 126-139)
   - Add `file(COPY)` block at file scope (after function defs, before test registrations)

2. `hipcub/test/hipcub/CMakeLists.txt`
   - Remove DLLS_COPIED block from `add_hipcub_test_internal()` (lines 94-107)
   - Add `file(COPY)` block at file scope (after function defs, before test registrations)

### Should fix (working but fragile, same pattern)

3. `rocprim/test/CMakeLists.txt` — remove from function, add at file scope
4. `rocprim/example/CMakeLists.txt` — same
5. `rocprim/benchmark/CMakeLists.txt` — same
6. `rocthrust/test/CMakeLists.txt` — same
7. `rocthrust/test/hipstdpar/CMakeLists.txt` — same
8. `hipcub/examples/CMakeLists.txt` — same
9. `hipcub/benchmark/CMakeLists.txt` — same
10. `rocrand/test/CMakeLists.txt` — same
11. `rocrand/benchmark/CMakeLists.txt` — same
12. `rocrand/test/package/CMakeLists.txt` — same
13. `hiprand/test/CMakeLists.txt` — same
14. `hiprand/test/package/CMakeLists.txt` — same
15. `rocthrust/examples/CMakeLists.txt` — remove `set(DLLS_COPIED OFF)`, add file(COPY)

## Testing

- Configure on Windows and verify no `[DLLS_COPY_DEBUG]` "POST_BUILD copy added" messages
- Build with parallel link steps and verify no "Error copying file" failures
- Verify rtest.py/rtest.xml are present in build output directories

## Upstream

This is a change to rocm-libraries (upstream). Will need a PR there.

## References

- TheRock #763 — CI-Windows-Build: `[rocPRIM] Error copying file`
- TheRock PR #3483 — where this was observed most recently
- Original commit: rocm-libraries 5ddc9ae8 (2021)
