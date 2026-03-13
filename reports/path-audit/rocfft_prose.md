# Path Discovery Audit: rocfft (rocm-libraries)

Audited: 2026-03-13
Source: `rocm-libraries/projects/rocfft/`

## Config Template — COMPLIANT

- `library/src/rocfft-config.cmake.in`:
  - Uses `@PACKAGE_INIT@`, `@PACKAGE_INCLUDE_INSTALL_DIR@`,
    `@PACKAGE_LIB_INSTALL_DIR@`
  - `include("${CMAKE_CURRENT_LIST_DIR}/rocfft-targets.cmake")` — relative
  - This is a reference example of the correct pattern.

## RPATH — MOSTLY COMPLIANT

**Good (relative):**

- `library/src/CMakeLists.txt:83`:
  `set(APPEND_ROCMLIB_RPATH "\$ORIGIN/../../../lib")` for rocfft_rtc_helper
- `clients/tests/CMakeLists.txt:254,257`:
  `set(INSTALL_RPATH "$ORIGIN/../llvm/lib")` — relative

**Bad (absolute):**

- `CMakeLists.txt:84`:
  `list(APPEND CMAKE_BUILD_RPATH ${ROCM_PATH}/lib)` — absolute, but only
  BUILD_RPATH (not installed), so lower severity
- `install.sh:385`:
  `-Wl,--rpath,/opt/rocm/lib:/opt/rocm/lib64` — fully hardcoded absolute

## Hardcoded Absolute Paths — NON-COMPLIANT

### CMAKE_INSTALL_PREFIX defaults

Repeated in every CMakeLists.txt that can be configured standalone:

- `CMakeLists.txt:34`: `set(CMAKE_INSTALL_PREFIX "/opt/rocm" ...)`
- `clients/tests/CMakeLists.txt:31`: same
- `clients/rider/CMakeLists.txt`: same pattern (not checked, likely same)
- `clients/samples/CMakeLists.txt`: same pattern

### find_package with PATHS /opt/rocm

- `CMakeLists.txt:55`:
  `find_package(ROCmCMakeBuildTools PATHS ${ROCM_PATH} /opt/rocm)`
- `CMakeLists.txt:179`:
  `find_package(hip REQUIRED CONFIG PATHS /opt/rocm/lib/cmake/hip/)`
- `CMakeLists.txt:180`:
  `find_package(hiprtc REQUIRED CONFIG PATHS /opt/rocm/lib/cmake/hiprtc/)`
- `clients/tests/CMakeLists.txt:56`:
  `find_package(hip REQUIRED PATHS /opt/rocm/lib/cmake/hip/)`

### Toolchain files

- `toolchain-linux.cmake:26-27`:
  `set(ROCM_PATH "/opt/rocm" ...)`, `set(rocm_bin "/opt/rocm/bin")`
  (reads `ENV{ROCM_PATH}` first, falls back to hardcoded)
- `toolchain-windows.cmake:30-31`:
  `set(HIP_DIR "C:/hip")`, `set(rocm_bin "C:/hip/bin")`
  (reads `ENV{HIP_PATH}` and `ENV{HIP_DIR}` first)

### find_program with PATHS /opt/rocm

- `clients/tests/CMakeLists.txt:499`:
  `find_program(LLVM_PROFDATA llvm-profdata ... PATHS /opt/rocm/llvm/bin)`
- `clients/tests/CMakeLists.txt:507`:
  `find_program(LLVM_COV llvm-cov ... PATHS /opt/rocm/llvm/bin)`

### Scripts and Python code

- `install.sh:380`: `rocm_path=/opt/rocm`
- `install.sh:385`: absolute RPATH (see RPATH section)
- `install.sh:424`: `export PATH=${PATH}:/opt/rocm/bin`
- `library/src/device/generator.py:71,88`:
  `subprocess.run(['/opt/rocm/llvm/bin/clang-format', ...])` —
  wrapped in try/except, graceful fallback
- `scripts/perf/perflib/specs.py:124-127`:
  `/opt/rocm/.info/version-utils`, `/opt/rocm/.info/version` —
  has TODO comment acknowledging the problem

### Other

- `rtest.xml:2`: `<!DOCTYPE testset SYSTEM "/usr/local/share/rtest.dtd">`

## Environment Variable Reads

**CMake:**

- `toolchain-linux.cmake:23-28`: `ENV{ROCM_PATH}` with `/opt/rocm` fallback
- `toolchain-windows.cmake:23-32`: `ENV{HIP_PATH}`, `ENV{HIP_DIR}` with
  `C:/hip` fallback
- `toolchain-windows.cmake:53`: `ENV{VCPKG_PATH}` with fallback
- `cmake/sqlite.cmake:37`: `ENV{SQLITE_3_50_2_SRC_URL}` — fine, build override
- `clients/tests/cmake/FindFFTW.cmake:32,51,83`: `$ENV{FFTW_ROOT}` — fine,
  external dependency

**Python:**

- `rmake.py:175`: `os.getenv('ROCM_PATH', "/opt/rocm")` — same pattern

**C++:**

- `shared/environment.h:69-73`: `rocfft_getenv()` wrapper — used only for
  rocfft-specific variables (`ROCFFT_*`, `TUNING_*`), not ROCm paths. Clean.

## ROCmCMakeBuildTools

- `CMakeLists.txt:55-73`: fetches from git if not found locally, searches
  `${ROCM_PATH} /opt/rocm`. Includes `ROCMSetupVersion`, `ROCMCreatePackage`,
  `ROCMInstallTargets`, etc. These modules may inject their own path
  assumptions.

## FindFFTW module

- `clients/tests/cmake/FindFFTW.cmake:34-35,54,86`: searches `/usr/include`,
  `/usr/local/include`, `/usr/lib`, `/usr/local/lib`. Acceptable for a system
  dependency (FFTW is external to ROCm).

## Summary

| Area | Status | Notes |
|------|--------|-------|
| Config template | Compliant | Reference example |
| RPATH (installed) | Compliant | $ORIGIN |
| C++ source | Compliant | No ROCm path reads |
| CMAKE_INSTALL_PREFIX | Non-compliant | 4+ files |
| find_package PATHS | Non-compliant | 4+ call sites |
| Toolchain files | Non-compliant | Hardcoded defaults |
| find_program PATHS | Non-compliant | 2 call sites |
| Python scripts | Non-compliant | generator.py, specs.py, rmake.py |
| install.sh / rmake.py | Out of scope | Developer convenience scripts |

rocfft has significantly more violations than rocr-runtime, but the pattern is
the same: config template is clean, build-time discovery is riddled with
scattered `/opt/rocm`. The fix is the same: derive search paths from
`CMAKE_PREFIX_PATH` instead of per-call-site hints.

Note: `install.sh` and `rmake.py` are developer convenience scripts — people
can do what they want in their own build helpers. These are out of scope so
long as none of their hardcoded paths leak into CI/CD systems, generated
configs, or distributed packages.
