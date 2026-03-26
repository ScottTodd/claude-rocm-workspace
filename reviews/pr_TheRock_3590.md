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

**⚠️ CHANGES REQUESTED** — The feature direction is correct and straightforward but the test script has several issues that diverge from established patterns in the codebase, including a missing copyright header, `sys.exit()` instead of exceptions, `shell=True` usage, broad `except Exception`, and an unused variable. The CMake change also has an indentation issue.

**Strengths:**
- Clear intent — enabling ocltst is a useful addition to CI coverage
- Configuration entry in `fetch_test_configurations.py` is well-structured and follows existing patterns
- Windows DLL copy approach is reasonable

**Blocking/Important Issues:**
- Missing copyright header
- `sys.exit(1)` instead of exception
- `shell=True` on Windows subprocess call
- Broad `except Exception` swallows errors
- Unused variable `OCL_ICD_DLL`
- CMake indentation

---

## Detailed Review

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

1. Add copyright header to `test_ocltst.py`
2. Replace `sys.exit(1)` with `raise RuntimeError(...)`
3. Remove `shell=True` (or justify with a comment)
4. Remove broad `except Exception` — let DLL copy failures be hard errors
5. Remove or use the `OCL_ICD_DLL` variable

### ✅ Recommended:

1. Fix LD_LIBRARY_PATH handling to follow established pattern
2. Fix CMake indentation for `list(APPEND ...)`

### 💡 Consider:

1. Fix "ocltest" → "ocltst" comment typo
2. Consistent `--cap-add` syntax across test configs
3. Remove redundant `Path()` wrapping

---

## Testing Recommendations

- Verify ocltst runs successfully on both Linux and Windows CI with these fixes
- Confirm `BUILD_TESTS` being enabled on Windows doesn't cause CMake configure failures for ocl-clr

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The PR correctly enables ocltst in CI, but the test script needs cleanup to match established patterns: add copyright header, use exceptions instead of `sys.exit()`, remove `shell=True`, remove the broad exception handler, and fix the unused variable. The CMake indentation should also be corrected. None of these are difficult fixes.
