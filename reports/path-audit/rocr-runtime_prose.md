# Path Discovery Audit: rocr-runtime (rocm-systems)

Audited: 2026-03-13
Source: `rocm-systems/projects/rocr-runtime/`

## Config Templates — COMPLIANT

The generated CMake config files use proper relocatable patterns:

- `libhsakmt/hsakmt-config.cmake.in` — uses `${CMAKE_CURRENT_LIST_DIR}`
- `libhsakmt/rocdxg-config.cmake.in` — uses `${CMAKE_CURRENT_LIST_DIR}`
- `runtime/hsa-runtime/hsa-runtime64-config.cmake.in` — uses
  `${CMAKE_CURRENT_LIST_DIR}` and `@PACKAGE_INIT@`

These are reference examples of the correct pattern.

## RPATH — COMPLIANT

Uses `$ORIGIN` throughout:

- `runtime/hsa-ext-image/CMakeLists.txt:61`:
  `set(CMAKE_INSTALL_RPATH "$ORIGIN;$ORIGIN/../../lib;$ORIGIN/../../lib64;$ORIGIN/../lib64")`
- `runtime/hsa-runtime-tools/CMakeLists.txt:85`: same pattern
- `rocrtst/suites/test_common/CMakeLists.txt:696-697`: `$ORIGIN` with relative paths

## Hardcoded Absolute Paths — NON-COMPLIANT

### CMAKE_INSTALL_PREFIX defaults

- `libhsakmt/CMakeLists.txt:289`: `set(CMAKE_INSTALL_PREFIX "/opt/rocm" ...)`
- `libhsakmt/CMakeLists_wsl.txt:182`: same
- `libhsakmt/tests/kfdtest/CMakeLists.txt:80`: same

### find_path / find_library with PATHS /opt/rocm

- `runtime/hsa-runtime-tools/CMakeLists.txt:59`:
  `find_path(HSAKMT_INC ... PATHS "/opt/rocm/include")`
- `runtime/hsa-runtime-tools/CMakeLists.txt:60`:
  `find_library(HSAKMT_LIB ... PATHS "/opt/rocm/lib")`
- `runtime/hsa-runtime-tools/CMakeLists.txt:65`:
  `find_path(HSA_RUNTIME_INC ... PATHS "/opt/rocm/include")`
- `runtime/hsa-runtime-tools/CMakeLists.txt:66`:
  `find_library(HSA_RUNTIME_LIB ... PATHS "/opt/rocm/lib")`

### LLVM/Clang search paths

- `runtime/hsa-runtime/core/runtime/trap_handler/CMakeLists.txt:46-47`:
  `PATHS /opt/rocm/llvm` for Clang and LLVM
- `runtime/hsa-runtime/core/runtime/blit_shaders/CMakeLists.txt:48-49`:
  same
- `runtime/hsa-runtime/image/blit_src/CMakeLists.txt:46`:
  `PATHS /opt/rocm/llvm` for Clang

### FindLibElf modules

- `runtime/cmake_modules/FindLibElf.cmake:24-27`: `/usr/include`,
  `/usr/local/include`
- `runtime/cmake_modules/FindLibElf.cmake:38-39`: `/usr/lib`, `/usr/local/lib`
- `runtime/hsa-runtime/cmake_modules/FindLibElf.cmake:24-30`: same

Note: system path hints for system libraries (libelf) are less concerning than
`/opt/rocm` hints, since libelf is a system dependency not a ROCm component.

## Environment Variable Reads

- `libhsakmt/tests/rdma/simple/app/CMakeLists.txt:10-11`:
  `ENV{LIBHSAKMT_PATH}` — test-only, low severity
- `libhsakmt/tests/reopen/CMakeLists.txt:5,7`:
  `ENV{ROOT_OF_ROOTS}`, `ENV{LIBHSAKMT_ROOT}` — test-only
- `libhsakmt/tests/kfdtest/CMakeLists.txt:109`:
  sets `ENV{PKG_CONFIG_PATH}` fallback to `/opt/rocm/lib/pkgconfig`
- `libhsakmt/tests/rdma/simple/app/CMakeLists.txt:15-17`:
  falls back to `/opt/rocm/lib/pkgconfig` when `ROCM_INSTALL_PATH` not set

## Scripts

- `libhsakmt/tests/kfdtest/scripts/run_kfdtest.sh:36,51,64,71`:
  multiple `/opt/rocm` fallbacks
- `runtime/packages/rocr_tools_legacy/postinst:6`: `/opt/rocm/hsa/lib`
- `runtime/packages/rocr_tools_legacy/rpm_post:1`: same
- `runtime/packages/hsa-ext-rocr-dev/postinst:6`: same
- `runtime/packages/hsa-ext-rocr-dev/rpm_post:1`: same

## Summary

| Area | Status |
|------|--------|
| Config templates | Compliant (reference examples) |
| RPATH | Compliant ($ORIGIN) |
| CMAKE_INSTALL_PREFIX | Non-compliant (3 files) |
| find_* PATHS hints | Non-compliant (7+ call sites) |
| Post-install scripts | Non-compliant (legacy packaging) |
| Test infrastructure | Non-compliant (low priority) |

The config templates and RPATH are solid. The build-time violations are the
scattered `/opt/rocm` pattern described in the standalone builds section of
`component_path_discovery.md` — they would be addressed by deriving search
paths from `CMAKE_PREFIX_PATH` instead of per-call-site hints.
