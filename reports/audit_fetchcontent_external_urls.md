# Audit: External FetchContent_Declare URLs in TheRock Submodules

**Date:** 2026-03-31
**Trigger:** Linux builds broken — `otf2-3.0.3.tar.gz` download from
`perftools.pages.jsc.fz-juelich.de` failing. See
https://github.com/ROCm/rocm-systems/actions/runs/23811724588/job/69400353587

## Background

TheRock's `third-party/` directory uses `therock_subproject_fetch` with URLs
mirrored to `https://rocm-third-party-deps.s3.us-east-2.amazonaws.com/`. This
provides hermetic builds with no dependency on external servers. See
`docs/development/git_chores.md` § "Updating a third-party mirror".

However, code inside git submodules (`rocm-systems/`, `rocm-libraries/`,
`compiler/`, `iree-libs/`) uses raw `FetchContent_Declare` with URLs pointing
to external servers (GitHub, university hosts, etc.). These bypass TheRock's
mirror infrastructure entirely.

## Summary

- **~70+ external FetchContent_Declare calls** across submodules
- **1 non-GitHub URL** (the broken one): `perftools.pages.jsc.fz-juelich.de`
- **~10 dependencies already mirrored** in `third-party/` but re-fetched from
  GitHub by subproject code (googletest, fmt, Catch2, flatbuffers,
  nlohmann-json, yaml-cpp, libdivide, etc.)
- **~14 locations** fetch `rocm-cmake` from GitHub (should be provided by
  super-project)

## Build Breaker

| Dependency | URL | File |
|---|---|---|
| otf2 3.0.3 | `https://perftools.pages.jsc.fz-juelich.de/cicd/otf2/tags/otf2-3.0.3/otf2-3.0.3.tar.gz` | `rocm-systems/projects/rocprofiler-sdk/external/otf2/CMakeLists.txt:32` |

## rocm-systems

| Dependency | URL / Domain | File (relative to `rocm-systems/projects/`) |
|---|---|---|
| otf2 | `perftools.pages.jsc.fz-juelich.de` | `rocprofiler-sdk/external/otf2/CMakeLists.txt` |
| googletest | github.com/google | `rocshmem/tests/unit_tests/CMakeLists.txt` |
| googletest | github.com/google | `rccl/cmake/Dependencies.cmake` |
| googletest | github.com/google | `rocm-smi-lib/tests/rocm_smi_test/CMakeLists.txt` |
| googletest | github.com/google | `rocprofiler-sdk/external/elfio/tests/CMakeLists.txt` |
| googletest | **S3 mirror (ok)** | `amdsmi/tests/amd_smi_test/CMakeLists.txt` |
| benchmark | github.com/google | `rocprofiler-sdk/external/json/tests/benchmarks/CMakeLists.txt` |
| fmt | github.com/fmtlib | `rocprofiler/src/tools/rocprofv2/CMakeLists.txt` |
| fmt | github.com/fmtlib | `rccl/cmake/Dependencies.cmake` |
| nlohmann_json | github.com/nlohmann | `rocprof-trace-decoder/test/CMakeLists.txt` |
| cereal | github.com/jrmadsen (fork) | `rocprofiler-sdk/tests/common/CMakeLists.txt` |
| perfetto | github.com/google | `rocprofiler-sdk/tests/common/CMakeLists.txt` |
| check | github.com/libcheck | `rocprofiler-sdk/external/gotcha/test/unit/CMakeLists.txt` |
| boost | github.com/boostorg | `rocprofiler-systems/cmake/DyninstBoost.cmake` |
| mongoose | github.com/cesanta | `rocprofiler-sdk` (testing dep) |
| curl | github.com/curl | `rocprofiler-sdk` (testing dep) |
| rocm-cmake | github.com/ROCm | `rccl-tests/cmake/Dependencies.cmake` |

## rocm-libraries

| Dependency | URL / Domain | File (relative to `rocm-libraries/projects/`) |
|---|---|---|
| nanobind | github.com/wjakob | `hipblaslt/tensilelite/rocisa/CMakeLists.txt` |
| nanobind | github.com/wjakob | `hipdnn/python/CMakeLists.txt` |
| googletest | github.com/google | `hipcub/cmake/Dependencies.cmake` |
| googletest | github.com/google | `hiprand/cmake/Dependencies.cmake` |
| googletest | github.com/google | `composablekernel/cmake/gtest.cmake` |
| googletest | github.com/google | `rocprim/cmake/Dependencies.cmake` |
| googletest | github.com/google | `miopen/fin/cmake/googletest.cmake` |
| googletest | github.com/google | `hipsparselt/cmake/fetch_google_test.cmake` |
| benchmark | github.com/google | `hipcub/cmake/Dependencies.cmake` |
| flatbuffers | github.com/google | `hipdnn/cmake/Dependencies.cmake` |
| spdlog | github.com/gabime | `hipdnn/cmake/Dependencies.cmake` |
| lapack | github.com/Reference-LAPACK | `hipsparselt/cmake/fetch_lapack.cmake` |
| getopt | github.com/apwojcik | `composablekernel/cmake/getopt.cmake` |
| pybind11 | github.com/pybind | (location TBD — seen in scan) |
| yaml-cpp | github.com/jbeder | (subproject copy, vs. S3-mirrored `third-party/` copy) |
| libdivide | github.com/ridiculousfish | (subproject copy, vs. S3-mirrored `third-party/` copy) |
| rocm-cmake | github.com/ROCm | ~14 locations (hipblas, hipblaslt, hipcub, hipfft, hiprand, hipsolver, hipsparse, rocblas, rocfft, rocprim, rocthrust, etc.) |

## compiler

| Dependency | URL / Domain | File |
|---|---|---|
| spirv-headers | github.com/KhronosGroup | `spirv-llvm-translator/CMakeLists.txt` |

## iree-libs

IREE has its own dependency management. These are lower priority for TheRock
since IREE is somewhat self-contained, but they still affect build hermeticity.

| Dependency | URL / Domain | File (relative to `iree-libs/`) |
|---|---|---|
| nanobind | github.com/wjakob | `iree/CMakeLists.txt` |
| cpuinfo | github.com/pytorch | `iree/CMakeLists.txt` |
| mimalloc | github.com/microsoft | `iree/CMakeLists.txt` |
| spirv-headers | github.com/KhronosGroup | `iree/.../WebGPUSPIRV/spirv-headers/CMakeLists.txt` |
| spirv-tools | github.com/KhronosGroup | `iree/.../WebGPUSPIRV/spirv-tools/CMakeLists.txt` |
| tint | dawn.googlesource.com | `iree/.../WebGPUSPIRV/tint/CMakeLists.txt` |
| fusilli_iree | github.com/iree-org | `fusilli/CMakeLists.txt` |
| libbacktrace | github.com/ianlancetaylor | `iree/build_tools/third_party/libbacktrace/CMakeLists.txt` |
| capstone | github.com/capstone-engine | `iree/build_tools/third_party/tracy/CMakeLists.txt` |
| PPQSort | github.com/GabTux | `iree/build_tools/third_party/tracy/CMakeLists.txt` |
| protobuf | github.com/protocolbuffers | `iree/integrations/pjrt/cmake/protobuf_cc_library.cmake` |
| Catch2 | github.com/catchorg | `fusilli/CMakeLists.txt` |
| CLI11 | github.com/CLIUtils | `fusilli/CMakeLists.txt` |
| onnx | github.com/onnx | `iree/third_party/torch-mlir/.../onnx_c_importer/CMakeLists.txt` |
| oneTBB | github.com/oneapi-src | (seen in scan) |

## Prioritization

### P0 — Build-breaking (fix now)

- **otf2**: Mirror `otf2-3.0.3.tar.gz` to S3, patch
  `rocprofiler-sdk/external/otf2/CMakeLists.txt` to use the mirror URL.

### P1 — Already mirrored in `third-party/` (low-effort wins)

These dependencies are already on S3 via `third-party/`. Subprojects fetch
their own copies from GitHub. Could be fixed systematically with
`FETCHCONTENT_SOURCE_DIR_*` or `FETCHCONTENT_URL_*` overrides at the
super-project level, or by ensuring `find_package` resolves first.

- googletest (~11 locations)
- fmt (2 locations)
- Catch2
- flatbuffers
- nlohmann-json
- yaml-cpp
- libdivide

### P2 — Not yet mirrored (need S3 upload + patch or override)

- nanobind, cereal, perfetto, mongoose, curl, boost, lapack, getopt, spdlog,
  benchmark, check, pybind11

### P3 — rocm-cmake (structural)

~14 subprojects fetch rocm-cmake from GitHub. The super-project should provide
it via `find_package`. These fetches should be no-ops if the super-project
build is used, but they're a problem for standalone subproject builds and add
unnecessary network dependency.

### P4 — IREE ecosystem (lower priority)

IREE manages its own deps. Fixing these requires coordination with the IREE
project. Less likely to affect core ROCm builds unless IREE components are
enabled.

## Fix Strategies

1. **Mirror + patch** (per-dependency): Upload tarball to S3, apply a patch
   via TheRock's `patches/` system to rewrite the URL. Works for any dep but
   doesn't scale well.

2. **CMake overrides** (systematic): Set `FETCHCONTENT_SOURCE_DIR_<name>` or
   use `FetchContent_Declare(<name> OVERRIDE_FIND_PACKAGE)` at the
   super-project level. This redirects subproject fetches to TheRock-provided
   packages without patching submodule code. Requires that TheRock's
   `third-party/` provides the dependency.

3. **Upstream fixes**: For ROCm-owned subprojects (rocm-systems,
   rocm-libraries), contribute patches upstream to use `find_package` with
   fallback to `FetchContent`, so the super-project can inject dependencies.

4. **Network policy**: For CI, could use a caching proxy or firewall rules to
   detect/block unexpected external fetches during build. This is defense in
   depth, not a fix.

Strategy 2 is the best scaling approach for P1 dependencies. Strategy 1 is
needed for P0 (otf2) and P2 dependencies. Strategy 3 is the long-term fix.
