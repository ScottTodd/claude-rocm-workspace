# PR Review: Media Libs - Python tests

* **PR:** [#3713](https://github.com/ROCm/TheRock/pull/3713)
* **Author:** kiritigowda
* **Reviewed:** 2026-03-12
* **Status:** OPEN
* **Base:** `main` ← `kg/python-test`

---

## Summary

Adds Python integration tests for media libraries (rocdecode, rocjpeg). A new `media_test.py` checks that `.so` files exist, load via ctypes, and preload correctly. The test module is conditionally registered in `__main__.py` (Linux-only, since rocdecode/rocjpeg have no Windows support).

**Net changes:** +72 lines, -0 lines across 2 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** - The tests work but diverge from established patterns in the test suite and include redundancy with existing tests.

**Strengths:**
- Correctly gates media tests to Linux-only (matches `_dist_info` which has empty Windows DLL patterns)
- Follows the subprocess-isolation pattern for ctypes loading
- Uses `subTest` for per-library granularity

**Issues:**
- 2 of 3 tests are redundant with existing `core_test.py` coverage
- Custom `.so` discovery instead of reusing `utils.get_module_shared_libraries()`
- `.so` filter in `testMediaSharedLibrariesLoad` is redundant with the glob

---

## Detailed Review

### 1. `media_test.py` — Custom `_find_media_so_files` vs existing utility

**⚠️ IMPORTANT: Custom `.so` discovery diverges from test suite patterns**

The test suite has a standard utility `utils.get_module_shared_libraries(mod)` (in `tests/utils.py`) that handles both Linux (`.so`, `.so.*`) and Windows (`.dll`) discovery. This PR creates a bespoke `_find_media_so_files` that globs `**/lib{lib_name}.so*` in the core package path.

The custom function is reasonable since it targets specific libraries by name, but it introduces a parallel discovery mechanism. If the goal is to verify specific libraries exist, the existing `_dist_info.ALL_LIBRARIES` entries already define the expected patterns (`librocdecode.so*`, `librocjpeg.so*`).

**Recommendation:** Consider using `_dist_info.ALL_LIBRARIES[lib_name]` to get the expected `.so` pattern, consistent with how the library metadata is already maintained. Alternatively, use `utils.get_module_shared_libraries()` and filter by library name.

### 2. `media_test.py` — Both `testMediaSharedLibrariesLoad` and `testMediaPreloadLibraries` duplicate existing coverage

**⚠️ IMPORTANT: 2 of 3 tests are redundant with `core_test.py`**

- **`testMediaPreloadLibraries`**: `core_test.py::testPreloadLibraries` already iterates over **all** entries in `di.ALL_LIBRARIES.values()` and calls `rocm_sdk.preload_libraries()` for each one. Since rocdecode and rocjpeg are in `ALL_LIBRARIES`, they're already covered.

- **`testMediaSharedLibrariesLoad`**: `core_test.py::testSharedLibrariesLoad` already globs all `.so` files in the core package and loads each one via ctypes in a subprocess. None of the skip conditions (`amd_smi`, `clang_rt`, `LLVMOffload`, `roctracer`, `rocprofiler-sdk`, `test_linking_lib`, `opencl`) filter out rocdecode or rocjpeg. So media library loading is already tested.

The only **new** coverage is `testMediaSharedLibrariesExist` — which asserts that rocdecode and rocjpeg `.so` files are specifically present by name. `core_test.py` only checks that `so_paths` is non-empty overall, not that specific libraries are included.

**Recommendation:** The whole file could be reduced to just the existence check, or the existence check could be added to `core_test.py` directly. If a separate file is preferred for organizational reasons, remove the two redundant tests and keep only `testMediaSharedLibrariesExist`.

### 3. `media_test.py` — Redundant `.so` suffix filter in `testMediaSharedLibrariesLoad`

**💡 SUGGESTION: Simplify `.so` filter logic**

```python
if so_path.suffix == ".so" or ".so." in so_path.name:
```

This condition is always true for every result from `_find_media_so_files` because the glob `**/lib{lib_name}.so*` only matches files containing `.so` in the name. Every match will satisfy one of these conditions. The filter can be removed, or if the intent is to skip non-loadable symlinks, consider checking `so_path.is_file()` instead.

### 4. `__main__.py` — Platform gating approach

**💡 SUGGESTION: Consider consistency with existing gating pattern**

The existing pattern for optional tests uses:
```python
if di.ALL_PACKAGES["libraries"].has_py_package(target_family):
    ALL_TEST_MODULES.append(...)
```

The media test uses `platform.system() != "Windows"` instead. Since media libs are in the "core" package (not a separate package), there's no separate package to check — so the platform check is a reasonable alternative. However, it assumes media libs are always present on Linux, which may not be true if someone builds core without media support.

**Recommendation:** Consider checking whether the media `.so` files actually exist before adding the test module, or at least make the tests graceful if the libraries aren't present (currently `testMediaSharedLibrariesExist` would fail).

### 5. `media_test.py` — Module-level assertions

**💡 SUGGESTION: Module-level code runs unconditionally on import**

Lines 17-21 execute assertions and imports at module level:
```python
utils.assert_is_physical_package(rocm_sdk)
core_mod_name = di.ALL_PACKAGES["core"].get_py_package_name()
core_mod = importlib.import_module(core_mod_name)
utils.assert_is_physical_package(core_mod)
```

This follows the existing pattern (e.g., `core_test.py` does the same), so it's consistent. Just noting that if the core package isn't installed, this will fail at import time with a potentially confusing error rather than a clean skip.

---

## Recommendations

### ❌ REQUIRED (Blocking):

(None — no correctness or security issues)

### ✅ Recommended:

1. Remove `testMediaSharedLibrariesLoad` and `testMediaPreloadLibraries` — both are already covered by `core_test.py` (which tests all `.so` files in core and all entries in `ALL_LIBRARIES`)
2. Keep `testMediaSharedLibrariesExist` (the only new coverage) or fold it into `core_test.py`
3. Consider using `_dist_info.ALL_LIBRARIES` metadata for library discovery instead of a custom glob function, for consistency with how libraries are defined in the project

### 💡 Consider:

1. Remove the redundant `.so` suffix check in `testMediaSharedLibrariesLoad`
2. Make tests graceful if media libraries aren't present (e.g., `skipTest` instead of assertion failure) — or confirm that media libs are always included in core builds on Linux

### 📋 Future Follow-up:

1. The test suite could benefit from a shared utility for "check that specific named libraries exist and load" since this pattern is repeated across test files

---

## Testing Recommendations

- Run `python -m rocm_sdk test` on a Linux system with media libraries installed to verify the new tests pass
- Run on a Linux system **without** media libraries to verify graceful behavior
- Run on Windows to verify the skip message appears

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The PR adds useful test coverage for media libraries but has redundancy with existing tests (`testMediaPreloadLibraries` duplicates `core_test.py` coverage) and introduces a custom discovery function where existing utilities or metadata could be reused. No blocking issues — the code is correct — but the recommended changes would improve consistency with the rest of the test suite.
