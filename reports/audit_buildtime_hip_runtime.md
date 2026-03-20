# Audit: Build-time code using HIP runtime APIs

**Date:** 2026-03-20
**Context:** The [rocm-systems#4010](https://github.com/ROCm/rocm-systems/pull/4010) Windows build failure revealed that `rocisa`, a build-time code generation tool, was calling HIP runtime APIs. This audit searches for other instances of build-time tools depending on the HIP runtime. Build-time tools run on CPU-only CI machines — they should not depend on GPU runtime libraries.

**Scope:** rocm-systems and rocm-libraries repositories (at TheRock release/therock-7.12 branch).
**Prior art:** [rocm-libraries#966 comment](https://github.com/ROCm/rocm-libraries/pull/966#discussion_r2257527703) flagged a similar pattern previously.

## Definition of "build-time code"

Code that executes during `cmake --build` on the build host:
- Python modules invoked by `add_custom_command` (e.g. TensileCreateLibrary)
- C++ executables invoked by `add_custom_command` (e.g. GPUArchitectureGenerator)
- Code generation tools that produce source files, assembly, or data files

This does NOT include: runtime libraries, test executables, benchmarks, or samples — even if they use HIP APIs, those are expected to run on GPU-capable machines.

## Findings

### rocm-systems

**No findings.** Build-time tools in rocm-systems (blit shader assembly in rocr-runtime, trap handlers) use `clang` as an assembler, not HIP runtime APIs.

### rocm-libraries

#### Finding 1: rocisa — `hipDeviceGetAttribute` (ACTIVE at build time)

**Severity:** Active — this code runs during every build and caused the Windows CI failure.

| | |
|---|---|
| **Tool** | `rocisa.pyd` / `rocisa.so` (nanobind Python C extension) |
| **HIP APIs** | `hipDeviceGetAttribute()` |
| **CMake target** | `rocisa` in `hipblaslt/tensilelite/rocisa/CMakeLists.txt` |
| **Link dep** | `target_link_libraries(rocisa PRIVATE hip::host)` (line 69) |
| **Invoked by** | `add_custom_command` in `hipblaslt/.../device-library/CMakeLists.txt` via `python -m Tensile.TensileCreateLibrary` |

**Files:**
- `projects/hipblaslt/tensilelite/rocisa/rocisa/include/helper.hpp:26` — `#include <hip/hip_runtime.h>`
- `projects/hipblaslt/tensilelite/rocisa/rocisa/include/helper.hpp:65-73` — `getDeviceAttribute()` wrapper calling `hipDeviceGetAttribute()`
- `projects/hipblaslt/tensilelite/rocisa/rocisa/include/hardware_caps.hpp:394-400` — `#if HIP_VERSION >= 70353390` guard calling `getDeviceAttribute()`
- `projects/hipblaslt/tensilelite/rocisa/rocisa/include/base.hpp:97` — `rocIsa::init()` calls `initArchCaps()` which triggers the above

**Call chain:** `TensileCreateLibrary` (custom command) -> `import rocisa` -> `rocIsa.init()` -> `initArchCaps()` -> `getDeviceAttribute(hipDeviceAttributeExpertSchedMode, deviceId, 0)`

**Behavior on CPU-only machines:** `hipDeviceGetAttribute` fails, `getDeviceAttribute()` catches the error and returns the default value (0). The build succeeds but produces an incorrect `HasSchedMode=0` for gfx12 targets. This is a silent correctness issue — the generated code may miss scheduling optimizations.

**Introduced by:** [rocm-libraries#3262](https://github.com/ROCm/rocm-libraries/pull/3262) (commit `c5946cf238`, 2026-02-03).

---

#### Finding 2: origami — `hipGetDeviceProperties` (LATENT, compiled but not called)

**Severity:** Latent — the HIP runtime call exists in compiled code but is not reached during build. The `hip::host` link dependency is still pulled into `rocisa.pyd` transitively.

| | |
|---|---|
| **Tool** | origami library, linked into `rocisa.pyd` |
| **HIP APIs** | `hipGetDeviceProperties()`, `hipGetErrorString()` |
| **CMake target** | `roc::origami` in `shared/origami/CMakeLists.txt` |
| **Link dep** | `target_link_libraries(origami ... hip::host)` (line 85) |
| **Linked into build tools** | `rocisa` links `roc::origami` (PUBLIC, line 68 of rocisa CMakeLists.txt) |

**Files:**
- `shared/origami/include/origami/hardware.hpp:36` — `#include <hip/hip_runtime.h>`
- `shared/origami/src/origami/hardware.cpp:93-98` — `get_hardware_for_device(int deviceId)` calls `hipGetDeviceProperties(&prop, deviceId)`
- `shared/origami/src/origami/hardware.cpp:120-124` — `is_hardware_supported()` takes `hipDeviceProp_t`

**Why it doesn't fail now:** The `get_hardware_for_device()` function is not called in the rocisa/TensileCreateLibrary code path. The origami hardware query functions are used by `tensilelite-host` (runtime code), not by the code generation path. However, the `hip::host` link dependency propagates through origami into `rocisa.pyd`, contributing to the DLL load issue on Windows.

**Risk:** One refactor that calls `get_hardware_for_device()` from a build-time path would trigger the same class of failure. The `hip::host` link is already causing the Windows DLL problem transitively.

---

#### Finding 3: GPUArchitectureGenerator — `hipGetDeviceCount`, `hipGetDeviceProperties`, `hipGetDevice` (LATENT)

**Severity:** Latent — HIP runtime calls are compiled in but not reached during the build-time code generation path.

| | |
|---|---|
| **Tool** | `GPUArchitectureGenerator` (C++ executable) |
| **HIP APIs** | `hipGetDeviceCount()`, `hipGetDeviceProperties()`, `hipGetDevice()` |
| **CMake target** | `GPUArchitectureGenerator` in `shared/rocroller/GPUArchitectureGenerator/CMakeLists.txt` |
| **Link dep** | `target_link_libraries(GPUArchitectureGenerator PRIVATE hip::host)` (line 58) |
| **Invoked by** | `add_custom_command` (lines 86-130) to generate `GPUArchitecture_def.yaml` and `.msgpack` |

**Files:**
- `shared/rocroller/lib/source/GPUArchitectureLibrary.cpp:22-46` — `GetCurrentDevices()` calls `hipGetDeviceCount()`, `hipGetDeviceProperties()`
- `shared/rocroller/lib/source/GPUArchitectureLibrary.cpp:59-77` — `GetHipDeviceArch()` calls `hipGetDevice()`, `hipGetDeviceProperties()`
- All guarded by `#ifdef ROCROLLER_USE_HIP` — and `ROCROLLER_USE_HIP` IS defined for the generator (line 64)

**Why it doesn't fail now:** The generator's `main()` uses assembler probing (`CheckAssembler`, `TryAssembler`) to discover architecture capabilities, not HIP device queries. The `GetCurrentDevices` and `GetHipDeviceArch` functions are compiled in but not called during generation.

**Risk:** Similar to finding 2. The code is compiled with `ROCROLLER_USE_HIP` and linked against `hip::host`, but the runtime code paths aren't hit. A refactor could activate them. The `hip::host` link also means the executable depends on `amdhip64` at link time, which could cause issues if the HIP SDK layout changes.

---

#### Finding 4: Tensile.py — `hipDeviceGetAttribute` via Python hip bindings (NOT build-time)

**Severity:** Not a build-time issue. Included for completeness.

| | |
|---|---|
| **Tool** | `Tensile.py` (Python benchmarking entry point) |
| **HIP APIs** | `hip.hipDeviceGetAttribute()` via Python `hip` package |
| **File** | `projects/hipblaslt/tensilelite/Tensile/Tensile.py:303-327` |

This function (`get_gpu_max_frequency`) is only called during the tuning/benchmarking flow (`LibraryLogic` config with `UseEffLike`), NOT during `TensileCreateLibrary` (the build-time path). No action needed.

## Summary

| # | Tool | HIP API | Build-time status | Fails on CPU-only? | Repo |
|---|------|---------|-------------------|---------------------|------|
| 1 | rocisa | `hipDeviceGetAttribute` | **Active** | No (silent fallback), but wrong results | rocm-libraries |
| 2 | origami (in rocisa) | `hipGetDeviceProperties` | **Latent** (compiled, not called) | Link-time dep on hip::host | rocm-libraries |
| 3 | GPUArchitectureGenerator | `hipGetDeviceCount/Properties/Device` | **Latent** (compiled, not called) | Link-time dep on hip::host | rocm-libraries |
| 4 | Tensile.py | `hipDeviceGetAttribute` (Python) | **Not build-time** | N/A | rocm-libraries |

## Recommendations

1. **Finding 1 (rocisa):** Remove the `hipDeviceGetAttribute` call from `initArchCaps`. `HasSchedMode` is a static property of the ISA — determine it from the target architecture version, not from a live device query. Remove the `hip::host` link dependency from `rocisa` if no other code paths need it.

2. **Finding 2 (origami):** Consider splitting origami into a header-only "architecture description" component (for build tools) and a "device query" component (for runtime). At minimum, the `hip::host` link should not propagate to build-time consumers.

3. **Finding 3 (GPUArchitectureGenerator):** Guard the `hip::host` link and `ROCROLLER_USE_HIP` definition behind an option that is OFF for the generator build. The generator already works via assembler probing — it doesn't need the HIP runtime compiled in.

4. **General principle:** Build-time tools should never link `hip::host` or `hip::device`. If a tool needs architecture information, it should use static tables or assembler probing, not device queries. Consider adding a CI check or CMake lint that flags `target_link_libraries(<build_tool> ... hip::host)` patterns.
