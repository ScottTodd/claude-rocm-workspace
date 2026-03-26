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

**⚠️ CHANGES REQUESTED** — Tests pass in CI, and the CMake change and test config are correct. The test script has concrete simplification opportunities (Windows DLL copy → PATH append, Linux LD_LIBRARY_PATH simplification) plus standard code-level fixes needed.

**Strengths:**
- Enabling ocltst is a useful addition to CI coverage — tests pass on Linux (gfx94X) and Windows (gfx110X, gfx1151)
- Configuration entry in `fetch_test_configurations.py` is well-structured and follows existing patterns
- CMake change to enable `BUILD_TESTS` on both platforms is correct

**Blocking/Important Issues:**
- Windows: `copy_dlls_exe_path()` can be replaced with a 2-line PATH append (see finding #0)
- Linux: `LD_LIBRARY_PATH` setup is verbose and clobbers existing value (see finding #0b)
- Missing copyright header
- `sys.exit(1)` instead of exception
- `shell=True` on Windows subprocess call
- Broad `except Exception` swallows errors
- Unused variable `OCL_ICD_DLL`
- CMake indentation

---

## Detailed Review

### 0. `test_ocltst.py` — Install to `bin/` to eliminate DLL copy and LD_LIBRARY_PATH workarounds

### ⚠️ IMPORTANT: Changing the install destination would simplify the entire script

**The problem:** ocltst installs to `tests/ocltst/` (Windows) and `share/opencl/ocltst/` (Linux), which are away from the runtime dependencies in `bin/` and `lib/`. The test script then works around this mismatch by copying DLLs (Windows) and constructing `LD_LIBRARY_PATH` with 4 hardcoded subdirectories (Linux).

**Evidence from CI logs** (Windows gfx110X job `68660213071`):
```
INFO:root:++ Copied: ...\build\bin\amdocl64.dll to ...\build\tests\ocltst
INFO:root:++ Copied: ...\build\bin\amd_comgr0702.dll to ...\build\tests\ocltst
INFO:root:++ Copied: ...\build\bin\OpenCL.dll to ...\build\tests\ocltst
```

**Evidence from CI logs** (Linux gfx94X job `68660411582`):
```
INFO:root:++ Setting LD_LIBRARY_PATH=.../build/lib:.../build/lib/opencl:
  .../build/lib/llvm/lib:.../build/lib/rocm_sysdeps/lib:...:
  .../build/share/opencl/ocltst
```

**Other test executables install to `bin/` and don't need any of this.** In a local build's `dist/` directory:
```
dist/rocm/bin/hipblaslt_plugin_tests.exe
dist/rocm/bin/hipdnn_backend_tests.exe
dist/rocm/bin/miopen_plugin_integration_tests.exe
... (many more)
```

These work out of the box because the DLLs (`.dll`/`.so`) are already siblings in `bin/` / reachable via RPATH from `bin/`.

**Root cause in CMake** (`rocm-systems/projects/clr/opencl/tests/ocltst/CMakeLists.txt`):
```cmake
if (WIN32)
    set(OCLTST_INSTALL_DIR "tests/ocltst")    # <-- problem
else()
    set(OCLTST_INSTALL_DIR "share/opencl/ocltst")  # <-- problem
endif()
```

Note that the binary already sets `INSTALL_RPATH "$ORIGIN"` (env/CMakeLists.txt:52), so if it's installed to `bin/`, RPATH will resolve `libOpenCL.so` etc. from the same directory.

**Suggested fix:** Change the install destination to `bin/` and install the test modules (`liboclruntime.so`/`oclruntime.dll`) and `.exclude` files alongside. This is a subproject (rocm-systems) change, but it would let the test script collapse to:

```python
# Both platforms: ocltst is in bin/ next to its dependencies
OCLTST_PATH = THEROCK_BIN_DIR
cmd = ["./ocltst", "-m", "liboclruntime.so", "-A", "oclruntime.exclude"]  # Linux
# or  ["ocltst.exe", "-m", "oclruntime.dll", "-A", "oclruntime.exclude"]  # Windows
```

No `copy_dlls_exe_path()`, no `LD_LIBRARY_PATH`, no `ROCM_PATH`, no platform-branching for env setup — just locate and run.

The `OCL_ICD_FILENAMES` env var (Windows) would still be needed — the existing CMake custom target `test.ocltst.oclruntime` (runtime/CMakeLists.txt:94-102) already does this:
```cmake
COMMAND ${CMAKE_COMMAND} -E env "OCL_ICD_FILENAMES=$<TARGET_FILE:amdocl>"
        $<TARGET_FILE:ocltst> -p 0 -m $<TARGET_FILE:oclruntime> -A oclruntime.exclude
```

On Linux, `OCL_ICD_VENDORS` pointing to `etc/OpenCL/vendors/` may still be needed depending on whether the system ICD loader finds the TheRock vendor config automatically.

The artifact TOML (`core/artifact-core-ocl.toml`) would need updating too — the `test` component currently matches `tests/**` and `share/opencl/**`. If the binaries move to `bin/`, they'd be captured by the `run` component instead. You could add a `test` include for the `.exclude` files specifically, or install those to `bin/` as well.

**Recommendation:** Change `OCLTST_INSTALL_DIR` to `bin/` (both platforms), update the artifact TOML accordingly, then simplify the test script to ~15 lines. If changing the subproject install path is out of scope for this PR, the PATH-based workaround is a good interim fix:

```python
# Interim: add bin dir to PATH so Windows finds DLLs without copying
if is_windows:
    env["PATH"] = f"{THEROCK_BIN_DIR};{env.get('PATH', '')}"
```

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

No other test script in this directory uses `shell=True`. This was likely added so Windows would search PATH for the .exe, but `subprocess.run` with a list already does that when `cwd` is set. The proper fix is the PATH manipulation from finding #0 above, then `shell=True` becomes unnecessary.

**Required action:** Remove `shell=True` (set `shell_var = False` for both platforms, or remove the parameter entirely).

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
3. Remove `shell=True` (see finding #3)
4. Remove broad `except Exception` — let DLL copy failures be hard errors (or moot if `copy_dlls_exe_path` is removed per finding #0)
5. Remove or use the `OCL_ICD_DLL` variable

### ⚠️ IMPORTANT:

1. **Install ocltst to `bin/` instead of `tests/ocltst/` / `share/opencl/ocltst/`** — change `OCLTST_INSTALL_DIR` in `rocm-systems/projects/clr/opencl/tests/ocltst/CMakeLists.txt` to `bin/` (both platforms). This matches how `hipblaslt_plugin_tests.exe`, `hipdnn_backend_tests.exe`, etc. are installed and eliminates the need for DLL copying, `LD_LIBRARY_PATH`, and `ROCM_PATH` entirely. Update `artifact-core-ocl.toml` accordingly. (See finding #0 for full details.)
   - If this subproject change is out of scope, the interim PATH workaround (`env["PATH"] = f"{THEROCK_BIN_DIR};{env.get('PATH', '')}"`) works for Windows.
2. **Linux: If install path stays in `share/`, simplify LD_LIBRARY_PATH** — drop `ROCM_PATH`, use check-then-prepend pattern, verify which `lib/` subdirectories are actually needed at runtime
3. Fix CMake indentation for `list(APPEND ...)`

### 💡 Consider:

1. Fix "ocltest" → "ocltst" comment typo
2. Consistent `--cap-add` syntax across test configs
3. Remove redundant `Path()` wrapping

### 📋 Future Follow-up:

1. Simplify `test_hiptests.py` and other existing test scripts that use the same DLL-copy / `LD_LIBRARY_PATH` pattern (prior feedback on [PR #2001](https://github.com/ROCm/TheRock/pull/2001#discussion_r2578817393))

---

## Testing Recommendations

- If install path changes to `bin/`, verify the test executable and modules (`liboclruntime.so`/`oclruntime.dll`, `.exclude` files) all end up in the right place in the artifact
- If using the interim PATH workaround, verify ocltst still passes on Windows CI
- On Linux, try with just `lib/` in LD_LIBRARY_PATH (without `lib/opencl`, `lib/llvm/lib`, `lib/rocm_sysdeps/lib`) to see which subdirectories are actually needed
- Confirm `BUILD_TESTS` being enabled on Windows doesn't cause CMake configure failures for ocl-clr

---

## CI Evidence

Evidence gathered from successful CI runs on this PR (run `23565450720`):

| Job | ID | Platform | Result |
|-----|-----|----------|--------|
| ocltst (gfx94X-dcgpu) | `68660411582` | Linux (container) | ✅ PASSED |
| ocltst (gfx110X-all) | `68660213071` | Windows | ✅ PASSED |
| ocltst (gfx1151) | `68660213199` | Windows | ✅ PASSED |

**Linux artifact layout** (209 artifacts fetched with `--tests --flatten`):
- `build/share/opencl/ocltst/ocltst` — test binary
- `build/lib/`, `build/lib/opencl/`, `build/lib/llvm/lib/`, `build/lib/rocm_sysdeps/lib/` — shared libraries
- `build/etc/OpenCL/vendors/` — ICD vendor configs

**Windows artifact layout:**
- `build/tests/ocltst/ocltst.exe` — test binary
- `build/bin/amdocl64.dll`, `build/bin/amd_comgr0702.dll`, `build/bin/OpenCL.dll` — DLLs (copied to test dir by script)

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The CMake change to enable `BUILD_TESTS` on both platforms is correct. The test configuration entry is well-structured. The biggest simplification opportunity is changing `OCLTST_INSTALL_DIR` to `bin/` (matching `hipblaslt_plugin_tests.exe` and other test executables), which would eliminate `copy_dlls_exe_path()`, `LD_LIBRARY_PATH` construction, and `ROCM_PATH` — collapsing the script from ~96 lines to ~15. The clr CMake already has a `test.ocltst.oclruntime` custom target (runtime/CMakeLists.txt:94-102) that shows the minimal env needed to run ocltst, confirming only `OCL_ICD_FILENAMES` is required beyond standard library resolution. There are also standard code-level issues (missing copyright header, `sys.exit()`, `shell=True`, broad exception handling) that need fixing.
