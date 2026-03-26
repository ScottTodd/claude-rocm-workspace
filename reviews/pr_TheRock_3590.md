# PR Review: Enable ocltst execution on Rock

* **PR:** [#3590](https://github.com/ROCm/TheRock/pull/3590)
* **Author:** agunashe (Ajay GunaShekar)
* **Branch:** `users/agunashe/run_ocltst_rock` → `main`
* **Reviewed:** 2026-03-26
* **Status:** OPEN

---

## Summary

This PR enables execution of the OpenCL test suite (`ocltst`) in TheRock CI on both Linux and Windows. It adds a test configuration entry in `fetch_test_configurations.py`, a new test runner script `test_ocltst.py`, and moves the `BUILD_TESTS` CMake flag from the Linux-only block to apply on both platforms.

**Net changes:** +115 lines, -3 lines across 3 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The test script carries forward an architectural anti-pattern from earlier test scripts: manually copying DLLs, setting `LD_LIBRARY_PATH`, and constructing `ROCM_PATH` — all things the build system's `dist/` directory already handles. This makes tests CI-only and unrunnable by developers after a local build. There are also several code-level issues (missing copyright header, `sys.exit()`, `shell=True`, etc.).

**Strengths:**
- Clear intent — enabling ocltst is a useful addition to CI coverage
- Configuration entry in `fetch_test_configurations.py` is well-structured and follows existing patterns
- CMake change to enable `BUILD_TESTS` on both platforms is correct

**Blocking/Important Issues:**
- **Architectural:** Script should not need `copy_dlls_exe_path`, manual `LD_LIBRARY_PATH`, or `ROCM_PATH` setup — tests should run from the `dist/` directory
- Missing copyright header
- `sys.exit(1)` instead of exception
- `shell=True` on Windows subprocess call
- Broad `except Exception` swallows errors
- Unused variable `OCL_ICD_DLL`
- CMake indentation

---

## Detailed Review

### 0. `test_ocltst.py` — Architectural: CI-only test wrapper

### ❌ BLOCKING: Script duplicates work the build system already does

This script manually copies DLLs (`copy_dlls_exe_path`), constructs `LD_LIBRARY_PATH` from hardcoded subdirectories, and sets `ROCM_PATH` — all to make the test executable find its runtime dependencies. This is unnecessary and makes the test unrunnable outside of CI.

TheRock's build system already solves this problem. Per [build_system.md § Build Directory Layout](https://github.com/ROCm/TheRock/blob/main/docs/development/build_system.md#build-directory-layout), each subproject's `dist/` directory is populated by hardlinking the full cone of runtime dependencies from all upstream projects. A subproject's `dist/` is designed to be "a self-contained slice that is relocatable and usable (for testing, etc)." If ocltst is installed into the ocl-clr dist directory (or a top-level test dist), the executable should already be able to find `amdocl64.dll`, `amd_comgr.dll`, `OpenCL.dll`, etc. as siblings.

This was raised previously on [PR #2001 (comment)](https://github.com/ROCm/TheRock/pull/2001#discussion_r2578817393) for `test_hiptests.py`, where the same anti-pattern exists. This PR is carrying forward that approach rather than fixing it.

**What the script should look like:** A thin wrapper that:
1. Locates the ocltst executable within the extracted artifacts (or `dist/` directory)
2. Runs it with the appropriate filter flags (`-m liboclruntime.so -A oclruntime.exclude`)
3. No DLL copies, no `LD_LIBRARY_PATH` construction, no `ROCM_PATH`

If the `dist/` directory doesn't contain everything needed, the fix belongs in the CMake install rules for ocl-clr (ensuring ocltst and its dependencies are staged correctly), not in the test runner script.

**Required action:** Remove `copy_dlls_exe_path()`, the `LD_LIBRARY_PATH` construction, and the `ROCM_PATH` setup. If runtime dependencies are missing from the test artifact, fix the CMake install/staging rules instead. At minimum, if this requires more investigation, file an issue to track removing the workarounds and add a `# TODO(issue-url)` so this doesn't become permanent.

---

### 1. `test_ocltst.py` — Missing copyright header

### ❌ BLOCKING: Missing copyright header

All test scripts in this directory have the standard AMD copyright header:
```python
# Copyright Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
```
This file is missing it.

**Required action:** Add the copyright header at the top of the file.

---

### 2. `test_ocltst.py:13-16` — `sys.exit()` for error reporting

### ❌ BLOCKING: Uses `sys.exit()` instead of raising an exception

Per the [Python style guide fail-fast section](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/python_style_guide.md#fail-fast-behavior), error conditions should raise exceptions, not call `sys.exit()`:

```python
# Current:
if THEROCK_BIN_DIR_STR is None:
    logging.info("++ Error: ...")
    sys.exit(1)

# Should be:
if THEROCK_BIN_DIR_STR is None:
    raise RuntimeError("env(THEROCK_BIN_DIR) is not set. Please set it before executing tests.")
```

Also uses `logging.info` for an error message — should use `logging.error` if logging is retained.

**Required action:** Replace `sys.exit(1)` with `raise RuntimeError(...)`.

---

### 3. `test_ocltst.py:87` — `shell=True` on Windows

### ❌ BLOCKING: Uses `shell=True` for subprocess on Windows

```python
shell_var = True  # Windows path
...
subprocess.run(cmd, cwd=OCLTST_PATH, check=True, env=env, shell=shell_var)
```

No other test script in this directory uses `shell=True`. Using `shell=True` is a security concern (command injection) and is unnecessary when the command is passed as a list. If `shell=True` is needed for DLL resolution on Windows, that should be documented. Otherwise, remove it.

**Required action:** Set `shell=False` for both platforms (or remove the `shell` parameter entirely since `False` is the default). If there's a specific reason `shell=True` is needed on Windows, add a comment explaining why.

---

### 4. `test_ocltst.py:33-35` — Broad `except Exception`

### ❌ BLOCKING: Broad exception handler swallows errors

```python
except Exception as e:
    logging.info(f"++ Error copying {dll}: {e}")
```

This catches all exceptions (including `PermissionError`, `OSError`, etc.), logs them as `info`, and continues. If a DLL fails to copy, the test will likely fail in a confusing way later. Per fail-fast principles, let the exception propagate.

**Required action:** Remove the try/except. If `shutil.copy` fails, it should be a hard error. If some DLLs are optional, document which ones and catch only `FileNotFoundError` for those specific cases.

---

### 5. `test_ocltst.py:62` — Unused variable `OCL_ICD_DLL`

### ❌ BLOCKING: Unused variable

```python
OCL_ICD_DLL = Path(THEROCK_BIN_DIR) / "OpenCL.dll"
```

This variable is assigned but never used. It's unclear if it was intended to be used somewhere (perhaps should be set as an env var?) or is leftover from development.

**Required action:** Either remove the variable or use it as intended.

---

### 6. `test_ocltst.py:48-52` — LD_LIBRARY_PATH handling doesn't follow existing pattern

### ⚠️ IMPORTANT: LD_LIBRARY_PATH clobbers existing value

The existing pattern in other scripts (e.g., `test_hiptests.py:124-130`) preserves the existing `LD_LIBRARY_PATH`:

```python
# Existing pattern:
if "LD_LIBRARY_PATH" in env:
    env["LD_LIBRARY_PATH"] = f"{new_path}:{env['LD_LIBRARY_PATH']}"
else:
    env["LD_LIBRARY_PATH"] = new_path
```

This script reads it with `os.getenv`, but then unconditionally overwrites it in a string that may include `None` as a literal string if it wasn't set:

```python
LD_LIBRARY_PATH = os.getenv("LD_LIBRARY_PATH")
if LD_LIBRARY_PATH is not None:
    LD_LIBRARY_PATH = Path(LD_LIBRARY_PATH)  # Path() is wrong for a colon-separated list
env["LD_LIBRARY_PATH"] = f"...:{LD_LIBRARY_PATH}:..."
```

Also, wrapping a colon-separated path list in `Path()` is incorrect — `Path` treats the whole string as a single path.

**Recommendation:** Follow the `test_hiptests.py` pattern for LD_LIBRARY_PATH prepending.

---

### 7. `core/CMakeLists.txt:398-400` — CMake indentation

### ⚠️ IMPORTANT: Incorrect CMake indentation

The moved `list(APPEND ...)` has the argument at the same level as `list(`:

```cmake
  list(APPEND OCL_CLR_CMAKE_ARGS
  "-DBUILD_TESTS=${THEROCK_BUILD_TESTING}"
  )
```

Should be:
```cmake
  list(APPEND OCL_CLR_CMAKE_ARGS
    "-DBUILD_TESTS=${THEROCK_BUILD_TESTING}"
  )
```

Per the [CMake style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/cmake_style_guide.md), arguments should be indented relative to the function call.

**Recommendation:** Indent the argument by 2 spaces.

---

### 8. `fetch_test_configurations.py:73` — Misleading comment

### 💡 SUGGESTION: Comment says "ocltest" but key is "ocltst"

```python
    # ocltest
    "ocltst": {
```

Minor typo — the comment doesn't match the key name.

**Recommendation:** Change comment to `# ocltst` for consistency.

---

### 9. `test_ocltst.py` — `container_options` uses `=` syntax inconsistently

### 💡 SUGGESTION: Inconsistent `--cap-add` syntax

The ocltst entry uses `--cap-add=SYS_PTRACE` (with `=`) while the sanity entry uses `--cap-add SYS_MODULE` (with space). Both work for Docker, but consistency is preferable.

---

### 10. `test_ocltst.py:19` — Redundant `Path()` wrapping

### 💡 SUGGESTION: Redundant Path conversion

```python
THEROCK_DIR = Path(THEROCK_BIN_DIR).parent
```

`THEROCK_BIN_DIR` is already a `Path` (line 17), so `Path(THEROCK_BIN_DIR)` is redundant. Same issue on lines 41-43 where `Path(THEROCK_DIR)` and `Path(ROCK_LIB_PATH)` are used on values that are already `Path` objects.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. **Remove DLL copying, `LD_LIBRARY_PATH` construction, and `ROCM_PATH` setup** — rely on the build system's `dist/` directory to provide runtime dependencies. If something is missing from the artifact, fix the CMake install rules, not the test script.
2. Add copyright header to `test_ocltst.py`
3. Replace `sys.exit(1)` with `raise RuntimeError(...)`
4. Remove `shell=True` (or justify with a comment)
5. Remove broad `except Exception` (moot if `copy_dlls_exe_path` is removed)
6. Remove or use the `OCL_ICD_DLL` variable (moot if DLL workaround is removed)

### ✅ Recommended:

1. Fix LD_LIBRARY_PATH handling — ideally remove it entirely per the architectural finding; if it must stay, follow the `test_hiptests.py` pattern
2. Fix CMake indentation for `list(APPEND ...)`

### 💡 Consider:

1. Fix "ocltest" → "ocltst" comment typo
2. Consistent `--cap-add` syntax across test configs
3. Remove redundant `Path()` wrapping

---

## Testing Recommendations

- Verify ocltst runs successfully on both Linux and Windows CI after simplifying the script to use the `dist/` directory layout
- Confirm `BUILD_TESTS` being enabled on Windows doesn't cause CMake configure failures for ocl-clr
- Verify that the ocl-clr `dist/` directory (or the test artifact) actually contains all needed DLLs — if not, that's a CMake staging fix

### 📋 Future Follow-up:

1. Fix `test_hiptests.py` and other existing test scripts that use the same DLL-copy / `LD_LIBRARY_PATH` anti-pattern (tracked via prior feedback on [PR #2001](https://github.com/ROCm/TheRock/pull/2001#discussion_r2578817393))

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The main issue is architectural: the test script manually copies DLLs, constructs `LD_LIBRARY_PATH`, and sets `ROCM_PATH` — all things the build system's `dist/` directory is designed to provide. This makes the test CI-only and unrunnable by developers. These test wrapper scripts should be thin: locate the test binary, run it with filters, done. If runtime dependencies are missing from the artifact, fix the CMake install rules, not the test script. There are also several code-level issues (missing copyright header, `sys.exit()`, `shell=True`, broad exception handling) that need fixing.
