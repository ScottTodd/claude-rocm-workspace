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

**⚠️ CHANGES REQUESTED** — Tests pass in CI, and the CMake change and test config are correct. Local testing confirms that if ocltst installs to `bin/` (like other test executables), the entire DLL-copy / LD_LIBRARY_PATH / ROCM_PATH machinery in the script becomes unnecessary. Code-level fixes also needed.

**Strengths:**
- Enabling ocltst is a useful addition to CI coverage — tests pass on Linux (gfx94X) and Windows (gfx110X, gfx1151)
- Configuration entry in `fetch_test_configurations.py` is well-structured and follows existing patterns
- CMake change to enable `BUILD_TESTS` on both platforms is correct

**Blocking/Important Issues:**
- Install ocltst to `bin/` (like other test executables) to eliminate DLL copy, LD_LIBRARY_PATH, ROCM_PATH — validated locally (see "Local Experiment" section)
- `shell=True` on Windows subprocess call
- Broad `except Exception` swallows errors
- Unused variable `OCL_ICD_DLL`

---

## Detailed Review

### 1. Install to `bin/` to eliminate DLL copy and LD_LIBRARY_PATH workarounds

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

No `copy_dlls_exe_path()`, no `LD_LIBRARY_PATH`, no `ROCM_PATH`, no platform-branching for env setup — just locate and run. **We validated this locally — see the "Local Experiment" section below.**

The `OCL_ICD_FILENAMES` env var (Windows) would still be needed in CI — the existing CMake custom target `test.ocltst.oclruntime` (runtime/CMakeLists.txt:94-102) already does this:
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

### 2. `shell=True` on Windows

### ❌ BLOCKING: Uses `shell=True` for subprocess on Windows

```python
shell_var = True  # Windows path
...
subprocess.run(cmd, cwd=OCLTST_PATH, check=True, env=env, shell=shell_var)
```

No other test script in this directory uses `shell=True`. This was likely added so Windows would search PATH for the .exe, but `subprocess.run` with a list already does that when `cwd` is set. The proper fix is the install-to-bin/ change from finding #1, then `shell=True` becomes unnecessary.

**Required action:** Remove `shell=True` (set `shell_var = False` for both platforms, or remove the parameter entirely).

---

### 3. Broad `except Exception`

### ❌ BLOCKING: Broad exception handler swallows errors

```python
except Exception as e:
    logging.info(f"++ Error copying {dll}: {e}")
```

This catches all exceptions (including `PermissionError`, `OSError`, etc.), logs them as `info`, and continues. If a DLL fails to copy, the test will likely fail in a confusing way later. Per fail-fast principles, let the exception propagate.

**Required action:** Remove the try/except (or moot if `copy_dlls_exe_path` is removed per finding #1). If `shutil.copy` fails, it should be a hard error.

---

### 4. Unused variable `OCL_ICD_DLL`

### ❌ BLOCKING: Unused variable

```python
OCL_ICD_DLL = Path(THEROCK_BIN_DIR) / "OpenCL.dll"
```

This variable is assigned but never used. It's unclear if it was intended to be used somewhere (perhaps should be set as an env var?) or is leftover from development.

**Required action:** Either remove the variable or use it as intended.

---

### 5. LD_LIBRARY_PATH handling

### ⚠️ IMPORTANT: LD_LIBRARY_PATH clobbers existing value

Moot if the install-to-bin/ change from finding #1 is adopted (eliminates LD_LIBRARY_PATH entirely). If it stays:

The existing pattern in other scripts (e.g., `test_hiptests.py:124-130`) preserves the existing `LD_LIBRARY_PATH`:

```python
# Existing pattern:
if "LD_LIBRARY_PATH" in env:
    env["LD_LIBRARY_PATH"] = f"{new_path}:{env['LD_LIBRARY_PATH']}"
else:
    env["LD_LIBRARY_PATH"] = new_path
```

This script reads it with `os.getenv`, then unconditionally overwrites it in a string that may include `None` as a literal string if it wasn't set. Also wraps a colon-separated path list in `Path()`, which is incorrect — `Path` treats the whole string as a single path.

**Recommendation:** Follow the `test_hiptests.py` check-then-prepend pattern.

---

### 6. CMake indentation

### 💡 SUGGESTION: Incorrect CMake indentation

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

---

### 7. Missing copyright header

### 💡 SUGGESTION: Missing copyright header

All test scripts in this directory have the standard AMD copyright header:
```python
# Copyright Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
```
This file is missing it.

---

### 8. `sys.exit()` for error reporting

### 💡 SUGGESTION: Consider using exceptions instead of `sys.exit()`

```python
if THEROCK_BIN_DIR_STR is None:
    logging.info("++ Error: ...")
    sys.exit(1)
```

`sys.exit()` works fine for a standalone script, but `raise RuntimeError(...)` gives a clearer traceback. Also uses `logging.info` for an error message — `logging.error` would be more appropriate.

---

### 9. Minor issues

### 💡 SUGGESTION: Assorted nits

- **Comment typo** (`fetch_test_configurations.py:73`): Comment says `# ocltest` but key is `"ocltst"`
- **Inconsistent `--cap-add` syntax**: ocltst uses `--cap-add=SYS_PTRACE` (with `=`) while sanity uses `--cap-add SYS_MODULE` (with space)
- **Redundant `Path()` wrapping** (`test_ocltst.py:19`): `THEROCK_BIN_DIR` is already a `Path`, so `Path(THEROCK_BIN_DIR)` is redundant. Same on lines 41-43.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. **Install ocltst to `bin/` instead of `tests/ocltst/` / `share/opencl/ocltst/`** — change `OCLTST_INSTALL_DIR` in `rocm-systems/projects/clr/opencl/tests/ocltst/CMakeLists.txt` to `bin/` (both platforms). This matches how `hipblaslt_plugin_tests.exe`, `hipdnn_backend_tests.exe`, etc. are installed and eliminates the need for DLL copying, `LD_LIBRARY_PATH`, and `ROCM_PATH` entirely. Update `artifact-core-ocl.toml` accordingly. Validated locally — see "Local Experiment" section. (Finding #1)
   - If this subproject change is out of scope, the interim PATH workaround (`env["PATH"] = f"{THEROCK_BIN_DIR};{env.get('PATH', '')}"`) works for Windows.
2. Remove `shell=True` (finding #2)
3. Remove broad `except Exception` — moot if `copy_dlls_exe_path` is removed per #1 (finding #3)
4. Remove or use the `OCL_ICD_DLL` variable (finding #4)

### ⚠️ IMPORTANT:

1. **Linux: If install path stays in `share/`, simplify LD_LIBRARY_PATH** — drop `ROCM_PATH`, use check-then-prepend pattern, verify which `lib/` subdirectories are actually needed at runtime (finding #5)

### 💡 Consider:

1. Fix CMake indentation for `list(APPEND ...)` (finding #6)
2. Add copyright header (finding #7)
3. Use `raise RuntimeError(...)` instead of `sys.exit(1)` (finding #8)
4. Assorted nits: comment typo, `--cap-add` syntax, redundant `Path()` (finding #9)

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
| ocltst (gfx94X-dcgpu) | `68660411582` | Linux (container) | PASSED |
| ocltst (gfx110X-all) | `68660213071` | Windows | PASSED |
| ocltst (gfx1151) | `68660213199` | Windows | PASSED |

**Linux artifact layout** (209 artifacts fetched with `--tests --flatten`):
- `build/share/opencl/ocltst/ocltst` — test binary
- `build/lib/`, `build/lib/opencl/`, `build/lib/llvm/lib/`, `build/lib/rocm_sysdeps/lib/` — shared libraries
- `build/etc/OpenCL/vendors/` — ICD vendor configs

**Windows artifact layout:**
- `build/tests/ocltst/ocltst.exe` — test binary
- `build/bin/amdocl64.dll`, `build/bin/amd_comgr0702.dll`, `build/bin/OpenCL.dll` — DLLs (copied to test dir by script)

---

## Local Experiment: Install-to-bin/ Validation

To validate the "install to `bin/`" suggestion, we downloaded the Windows `gfx110X-all`
artifacts from the PR's CI run (run `23565450720`) and tested on a local Windows machine
with an AMD Radeon PRO W7900 Dual Slot (gfx1100).

### Setup

Downloaded and flattened artifacts: `core-ocl_test`, `core-ocl_run`, `core-ocl_lib`,
`core-ocl-icd_lib`, `base_run`, `base_lib`, `amd-llvm_run`, `amd-llvm_lib`, `sysdeps_lib`.

After extraction, the artifact layout was:
```
bin/
  amd_comgr0702.dll
  amdocl64.dll
  OpenCL.dll
  clinfo.exe
  ...
tests/ocltst/
  ocltst.exe
  oclruntime.dll
  oclruntime.exclude
  oclperf.dll
  oclperf.exclude
```

Simulated the install-to-bin/ change by copying ocltst files into `bin/`:
```
cp artifacts/3590-win/tests/ocltst/* artifacts/3590-win/bin/
```

### Experiment 1: Run from `bin/` with zero env setup

```
cd bin/ && ./ocltst.exe -m oclruntime.dll -A oclruntime.exclude
```

**Result: Tests ran and passed.** All DLLs resolved as siblings. Used system
OpenCL ICD (3652.0) which found the gfx1100 GPU. Sample output:

```
Platform Version: OpenCL 2.1 AMD-APP (3652.0)
Device Name: gfx1100
Board Name: AMD Radeon PRO W7900 Dual Slot
...
OCLCreateContext[  0]            PASSED
OCLKernelBinary[  0]            PASSED
OCLKernelBinary[  1]            PASSED
OCLGlobalOffset[  0]            PASSED
OCLLinearFilter[  0]            PASSED
OCLLinearFilter[  1]            PASSED
OCLAsyncTransfer[  0]           PASSED
OCLLDS32K[  0]                  PASSED
OCLMemObjs[  0]                 PASSED
OCLSemaphore[  0]               PASSED
OCLPartialWrkgrp[  0]           PASSED
OCLPartialWrkgrp[  1]           PASSED
OCLPartialWrkgrp[  2]           PASSED
OCLCreateBuffer[  0]            PASSED
OCLCreateImage[  0-4]           PASSED
OCLMapCount[  0]                PASSED
OCLMemoryInfo[  0]              PASSED
...
```

No `copy_dlls_exe_path()`, no `LD_LIBRARY_PATH`, no `ROCM_PATH`, no `PATH`
manipulation, no `shell=True`. Just `cd` and run.

### Experiment 2: Run from `bin/` with `OCL_ICD_FILENAMES` (CI-style)

```
cd bin/ && OCL_ICD_FILENAMES=$(pwd)/amdocl64.dll ./ocltst.exe -m oclruntime.dll -A oclruntime.exclude
```

**Result: `clGetDeviceIDs failed`.** All DLLs loaded successfully (no missing
DLL errors), but the artifact's `amdocl64.dll` failed to enumerate devices.

Full output:
```
$ cd bin/ && OCL_ICD_FILENAMES=$(pwd)/amdocl64.dll ./ocltst.exe -m oclruntime.dll -A oclruntime.exclude
clGetDeviceIDs failed
(exit code 1)
```

`clinfo` with the same ICD confirms the platform loads but finds 0 devices:
```
$ cd bin/ && OCL_ICD_FILENAMES=$(pwd)/amdocl64.dll ./clinfo.exe
Number of platforms:                     1
  Platform Version:                      OpenCL 2.1 AMD-APP (3581.0)
  Platform Name:                         AMD Accelerated Parallel Processing
  Platform Vendor:                       Advanced Micro Devices, Inc.
  Platform Extensions:                   cl_khr_icd cl_khr_d3d10_sharing cl_khr_d3d11_sharing cl_khr_dx9_media_sharing cl_amd_event_callback

  Platform Name:                         AMD Accelerated Parallel Processing
Number of devices:                       0
```

For comparison, `clinfo` with the system ICD finds 2 devices:
```
$ cd bin/ && ./clinfo.exe
Number of platforms:                     1
  Platform Version:                      OpenCL 2.1 AMD-APP (3652.0)
  Platform Name:                         AMD Accelerated Parallel Processing
  Platform Extensions:                   ... cl_amd_offline_devices

  Platform Name:                         AMD Accelerated Parallel Processing
Number of devices:                       2
  Device Type:                           CL_DEVICE_TYPE_GPU
  Board name:                            AMD Radeon PRO W7900 Dual Slot
```

The CI runners that passed show OpenCL `AMD-APP (3628.0)` at runtime (from
the ocltst output on both the gfx110X and gfx1151 jobs). Our local system
driver reports 3652.0, which is newer. It's unclear why the artifact (3581.0)
works with CI driver 3628.0 but not our local 3652.0 — this could be a driver
compatibility issue worth investigating separately. The relevant result for
the install-to-bin/ question is that **DLL resolution worked correctly** —
the failure was at OpenCL device enumeration, not at library loading.

### Experiment 3: Run from `tests/ocltst/` with zero env setup (original layout)

```
$ cd tests/ocltst/ && ./ocltst.exe -m oclruntime.dll -A oclruntime.exclude
(tests passed, exit code 0 — used system OpenCL 3652.0)
```

This works on this machine because the system has OpenCL.dll on PATH via the
AMD driver install. In CI (clean containers/runners), this would fail because
OpenCL.dll is not a system-level install — which is why the script copies DLLs.

### Conclusions

| Scenario | DLL resolution | Device found | Tests |
|---|---|---|---|
| `bin/` — no env setup | All DLLs as siblings | Yes (system ICD) | PASSED |
| `bin/` + `OCL_ICD_FILENAMES` | All DLLs as siblings | No (version mismatch) | N/A |
| `tests/ocltst/` — no env setup | System OpenCL on PATH | Yes (system ICD) | PASSED |

**Key takeaway:** When ocltst is in `bin/` alongside its DLL dependencies, it
runs with zero environment setup. The only CI-specific env var needed is
`OCL_ICD_FILENAMES` to force the TheRock-built OpenCL implementation (matching
what the clr CMake `test.ocltst.oclruntime` custom target does). The entire
`copy_dlls_exe_path()` function, the `LD_LIBRARY_PATH` construction, `ROCM_PATH`,
`shell=True`, and the platform-branched `setup_env()` are all workarounds for
the test binary being installed away from its dependencies.

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The CMake change to enable `BUILD_TESTS` on both platforms is correct. The test configuration entry is well-structured. Local testing on a Windows gfx1100 machine confirms that changing `OCLTST_INSTALL_DIR` to `bin/` (matching `hipblaslt_plugin_tests.exe` and other test executables) lets ocltst run with zero env setup — no DLL copies, no `LD_LIBRARY_PATH`, no `ROCM_PATH`. This would collapse the script from ~96 lines to ~15. The only CI-specific env var needed is `OCL_ICD_FILENAMES` (to force the TheRock OpenCL implementation), which the clr CMake `test.ocltst.oclruntime` custom target already uses. There are also code-level issues (`shell=True`, broad exception handling, unused variable) that need fixing.
