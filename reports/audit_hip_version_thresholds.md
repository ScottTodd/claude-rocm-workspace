# Audit: HIP_VERSION threshold guards activated by 7.2 -> 7.12 bump

**Date:** 2026-03-20
**Context:** [rocm-systems#4010](https://github.com/ROCm/rocm-systems/pull/4010) bumped `projects/hip/VERSION` from 7.2.0 to 7.12.60611, changing `HIP_VERSION` from 70200000 to 71260611. This audit identifies all `#if HIP_VERSION` preprocessor guards with thresholds in the activation range (70200001 - 71260611) — code paths that were dormant before the bump and are now active.

**Scope:** rocm-systems and rocm-libraries repositories (at TheRock release/therock-7.12 branch).

## Newly activated code paths

Only **2 code paths** become active when crossing from 70200000 to 71260611:

### 1. hipBLASLt/rocisa: expert scheduling mode detection

- **File:** `rocm-libraries/projects/hipblaslt/tensilelite/rocisa/rocisa/include/hardware_caps.hpp:394`
- **Threshold:** `#if HIP_VERSION >= 70353390`
- **Introduced by:** [rocm-libraries#3262](https://github.com/ROCm/rocm-libraries/pull/3262) (commit `c5946cf238`, 2026-02-03)

```cpp
#if HIP_VERSION >= 70353390
    rv["HasSchedMode"] = checkInList(isaVersion[0], {12})
                             ? getDeviceAttribute(hipDeviceAttributeExpertSchedMode, deviceId, 0)
                             : 0;
#else
    rv["HasSchedMode"] = 0;
#endif
```

**What changed:** Enables querying `hipDeviceAttributeExpertSchedMode` for gfx12 GPUs. Calls `hipDeviceGetAttribute()` — a HIP runtime function.

**Impact:** Broke Windows CI builds. `rocisa` is a build-time code generation tool. The new code path creates a link-time dependency on `amdhip64_7.dll` which Python's `LoadLibraryExW` (restricted DLL search in Python 3.8+) cannot resolve on Windows. See [debugging notes](https://gist.github.com/ScottTodd/8505d2b3704c4458e15db9339317cc24) for full analysis.

**Risk level:** High — caused a build failure on the release branch.

### 2. RCCL: cuMem host NUMA-aware allocation

- **File:** `rocm-systems/projects/rccl/src/misc/rocmwrap.cc:79`
- **Threshold:** `#if HIP_VERSION < 71260540` (code in the `#else` branch is newly active)

```cpp
#if HIP_VERSION < 71260540
  return 0;
#else
  // cuMem host allocation support
  int cudaDriverVersion;
  CUDACHECK(cudaDriverGetVersion(&cudaDriverVersion));
  if (cudaDriverVersion < 71260540) return 0;
  // ... NUMA-aware memory management via cuMemCreate/cuMemAddressReserve
#endif
```

**What changed:** Enables NUMA-aware GPU memory management via the cuMem API in `ncclCuMemHostEnable()`.

**Impact:** Lower risk. This is runtime library code (not build-time), and has a secondary runtime gate — `cudaDriverVersion < 71260540` — so even with the compile-time guard active, the new code only runs if the runtime driver also reports a compatible version. Double-gated.

**Risk level:** Low — runtime code with runtime fallback.

## Overall HIP_VERSION guard landscape

| Repository | Total guards | Files with guards |
|---|---|---|
| rocm-systems | 45 | 13 |
| rocm-libraries | 47 | 30 |
| **Total** | **92** | **43** |

### Threshold distribution

All other guards have thresholds well outside the activation range:

**rocm-systems:**
- `50200000` — 8 occurrences (rccl-tests, rocprofiler-systems)
- `50221310` — 22 occurrences (rccl-tests, rocprofiler-systems)
- `60300000` — 8 occurrences (rccl, rccl-tests, rocprofiler-sdk)
- `HIP_VERSION_MAJOR >= 6` — 1 occurrence (rocprofiler-sdk)

**rocm-libraries:**
- `307` — 3 occurrences (hipblaslt, rocsparse, rocprim, hipsparselt) — ancient threshold
- `50220730` — 7 occurrences (tensile, hipblaslt, rocblas)
- `50300000` — 8 occurrences (rocsparse, rocblas, hipsparse)
- `50500000` — 2 occurrences (rocblas clients)
- `HIP_VERSION_MAJOR < 7` — 11 occurrences (rocwmma, rocrand, hipblaslt) — already active at 7.x
- `HIP_VERSION_MAJOR >= 3/4` — 4 occurrences (rocthrust) — always active
- `HIP_VERSION_MAJOR == 6 && ...` — 3 occurrences (composablekernel) — inactive on 7.x

No occurrences of `__HIP_VERSION__` (variant spelling) were found.

## Release stream context

ROCm ran two parallel release streams with overlapping minor versions:
- **Stream 1:** 7.0, 7.1, 7.2, (and possibly 7.3)
- **Stream 2:** 7.9, 7.10, 7.11, 7.12

The version bump in #4010 jumped from 7.2 to 7.12 — crossing the gap between these two streams for the first time. This means any `HIP_VERSION` threshold set for stream 2 features (7.3 through 7.12) would have been dormant on the stream 1 branch and suddenly activated by this jump.

The hipBLASLt guard (`HIP_VERSION >= 70353390`, i.e. version 7.3.53390) is a direct consequence of this: it was likely written against stream 2 where 7.3+ was expected, but stream 1 was still at 7.2. When the branch jumped from 7.2 to 7.12, this guard and anything else targeting the 7.3-7.12 range activated simultaneously.

Some development teams may not have planned for this cross-stream jump, since the two streams had been running independently up to this point.

## Observations

1. **Only 2 out of 92 guards were in the activation range.** The vast majority of guards are for 5.x/6.x era features that have been active for a long time. The cross-stream jump was relatively clean in terms of total code paths activated, but the one that did break was in a critical build-time path.

2. **The RCCL guard (71260540) was designed for this version bump** — the threshold is very close to the new version (71260611), and the runtime double-gate suggests intentional coordination with the driver version. This is the right way to do it.

3. **The hipBLASLt guard (70353390) was NOT designed for this version bump** — the threshold targets version 7.3.53390 (stream 2), and the code was introduced without awareness that it would create a build-time HIP runtime dependency. When the stream 1 branch jumped past 7.3, this guard activated unexpectedly.

4. **`#if HIP_VERSION` guards are a risk multiplier for version bumps, especially cross-stream jumps.** Any version change can silently activate code paths. The person bumping the version has no way to discover what will change without auditing the entire codebase. A version bump that looks like a metadata-only change can activate entirely new code. Cross-stream jumps are particularly dangerous because they can activate guards that were written for a different release context.
