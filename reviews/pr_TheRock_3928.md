# PR Review: Split amd-llvm into base/flang/offload sub-projects and re-layer build order

* **PR:** [#3928](https://github.com/ROCm/TheRock/pull/3928)
* **Author:** stellaraccident (Stella Laurenzo)
* **Base:** `main`
* **Reviewed:** 2026-03-12
* **Status:** OPEN

---

## Summary

Splits the monolithic `amd-llvm` build into three sub-projects with distinct artifacts (`amd-llvm-base`, `amd-llvm-flang`, `amd-llvm-offload`), re-layers the `add_subdirectory` order so that dependencies are satisfied, moves ROCR-Runtime and rocminfo declarations from `core/` to `compiler/`, adds Fortran infrastructure (flag, toolchain keywords, math-lib gating), and patches LLVM's `openmpTargets.cmake` to fix a GCC 14 `-isystem` incompatibility.

**Net changes:** +749 lines, -305 lines across 19 files

---

## Overall Assessment

**✅ APPROVED** — Well-designed decomposition that achieves multiple goals (bootstrappable base compiler, independent Fortran gating, shorter critical path for non-mathlibs). The layering changes are consistent across BUILD_TOPOLOGY.toml, CMakeLists.txt files, and artifact descriptors. The split is clean and the PR description is thorough.

**Strengths:**
- Thorough PR description with clear motivation for each change
- Artifact descriptors properly split — each sub-project's stage directory is unique and consistently referenced
- BUILD_TOPOLOGY.toml changes are correct: dependency chain `sysdeps → amd-llvm-base → amd-llvm`, ordering adjusted, core-runtime deps updated
- The OpenMP `-isystem` patch is well-justified and narrowly scoped
- Fortran gating is properly done via the flag system (`GLOBAL_CMAKE_VARS` + `FORTRAN_REQUIRED`/`FORTRAN_OPTIONAL` keywords)
- `OPENMP_ENABLE_LIBOMPTARGET` left ON in base build with clear explanation of the dlsym fallback mechanism

**Issues:**
- 1 important, 4 suggestions, 1 future work

---

## Detailed Review

### 1. BUILD_TOPOLOGY.toml

**Artifact dependency chain:**

- `amd-llvm-base` (base stage) → depends on `sysdeps`
- `amd-llvm` (compiler-runtime stage) → depends on `amd-llvm-base`
- `amd-llvm-flang` (compiler-runtime stage) → depends on `amd-llvm`
- `amd-llvm-offload` (compiler-runtime stage) → depends on `amd-llvm`, `core-runtime`
- `core-runtime` (compiler-runtime stage) → depends on `base`, `sysdeps`, `amd-llvm-base`

Feature names resolve correctly via auto-generation:
- `amd-llvm-base` → `THEROCK_ENABLE_AMD_LLVM_BASE` (no explicit feature_name)
- `amd-llvm-flang` → `THEROCK_ENABLE_FLANG` (explicit `feature_name = "FLANG"`)
- `amd-llvm-offload` → `THEROCK_ENABLE_AMD_LLVM_OFFLOAD` (no explicit feature_name)

### 💡 SUGGESTION: amd-llvm-flang artifact_deps could be more precise

```toml
[artifacts.amd-llvm-flang]
artifact_deps = ["amd-llvm"]
```

Flang needs the base LLVM libraries and headers (`amd-llvm-base`), not comgr/hipcc (`amd-llvm`). This is a within-stage dependency so it doesn't affect artifact fetching, but `artifact_deps = ["amd-llvm-base"]` would be more semantically accurate. The transitive closure still reaches `amd-llvm-base` through `amd-llvm`, so this is functionally correct as-is.

### 💡 SUGGESTION: amd-llvm-offload has no feature_group

```toml
[artifacts.amd-llvm-offload]
artifact_group = "compiler"
type = "target-neutral"
artifact_deps = ["amd-llvm", "core-runtime"]
disable_platforms = ["windows"]
# no feature_group
```

`amd-llvm-base` has `feature_group = "ALL"`, `amd-llvm-flang` has `feature_group = "ALL"`, but `amd-llvm-offload` has none. Missing `feature_group` means it's always enabled (the `configure_stage.py` check `if artifact.feature_group and ...` passes through None). This achieves the right behavior (offload always enabled on Linux), but adding `feature_group = "ALL"` would be consistent with the other split artifacts.

---

### 2. Build Re-layering (CMakeLists.txt / add_subdirectory order)

The new order `sysdeps → base → third-party → compiler → core` is correct:
- `base/` declares `amd-llvm` (base compiler) — no deps on third-party
- `third-party/` can now depend on the base compiler if needed
- `compiler/` declares ROCR-Runtime (needs `therock-simde` from third-party), amd-llvm-flang, amd-llvm-offload, comgr, hipcc
- `core/` is now lighter (ROCR-Runtime/rocminfo moved out)

The `compiler-runtime` stage artifact_group reordering (`core-runtime` before `compiler`) is correct since `amd-llvm-offload` depends on `core-runtime` within the same stage.

---

### 3. ROCR-Runtime/rocminfo move from core/ to compiler/

Clean move. The artifact descriptor `compiler/artifact-core-runtime.toml` correctly updates stage paths from `core/ROCR-Runtime/stage` → `compiler/ROCR-Runtime/stage` and `core/rocminfo/stage` → `compiler/rocminfo/stage`. The old `core/artifact-core-runtime.toml` is deleted.

---

### 4. Artifact Descriptors

**base/artifact-amd-llvm-base.toml** — Correctly mirrors the old `compiler/artifact-amd-llvm.toml` LLVM sections with updated stage path `base/amd-llvm/stage`. The `force_include` for `lib/llvm/lib/clang/**` in the lib component is preserved.

**compiler/artifact-amd-llvm.toml** — Stripped down to just comgr and hipcc stage references. The old LLVM-specific components are removed. Clean.

**compiler/artifact-amd-llvm-flang.toml** — Minimal: `run` (binaries) and `dbg` components. Appropriate for a compiler frontend.

**compiler/artifact-amd-llvm-offload.toml** — `lib` (with `force_include` for `lib/llvm/lib/clang/**`), `run`, `dbg`. The `force_include` for `clang/**` captures device runtime files installed by offload — distinct from base's compiler-rt files since they're in separate stage dirs.

**compiler/artifact-core-runtime.toml** — Properly updated stage paths.

No duplicate file ownership across descriptors — each references its own stage directory.

---

### 5. Fortran Infrastructure

### ⚠️ IMPORTANT: FORTRAN_REQUIRED error message claims it checks for system compiler but doesn't

```cmake
if(ARG_FORTRAN_REQUIRED)
  message(FATAL_ERROR
    "Sub-project ${target_name} requires Fortran (FORTRAN_REQUIRED) "
    "but THEROCK_ENABLE_FLANG is OFF and no system Fortran compiler is available on Linux.")
endif()
```

The error message says "no system Fortran compiler is available" but no check for a system Fortran compiler (e.g., `find_program(gfortran)`) is performed. The condition is purely "Linux + THEROCK_ENABLE_FLANG is OFF". If a system gfortran is installed, this would still error.

**Recommendation:** Either:
1. Add a fallback to system gfortran when flang is not available (like the Windows path does), or
2. Change the error message to accurately say "but THEROCK_ENABLE_FLANG is OFF. Enable THEROCK_ENABLE_FLANG or set CMAKE_Fortran_COMPILER manually."

---

### 6. cmake/therock_subproject.cmake

The Fortran toolchain resolution at declare time and activation time is well-structured. The `THEROCK_FORTRAN_TOOLCHAIN_SUBPROJECT` property bridges the two phases cleanly.

The new `amd-llvm-offload` compiler toolchain type in `_therock_cmake_subproject_setup_toolchain` is correctly integrated alongside `amd-llvm` and `amd-hip`.

### 💡 SUGGESTION: Fortran compiler path assumption

```cmake
set(_fortran_compiler "${_fortran_dist_dir}/lib/llvm/bin/flang${CMAKE_EXECUTABLE_SUFFIX}")
```

This hardcodes the path within the dist tree. This is fine given the `INSTALL_DESTINATION "lib/llvm"` on the flang/offload sub-projects, but a comment noting why this specific path is expected (and which sub-project produces it) would help future readers.

---

### 7. amd-llvm-flang/CMakeLists.txt (New File)

This is the most complex new file — an out-of-tree Flang build against pre-built LLVM. The approach of using `find_package(LLVM)` + `find_package(Clang)` then manually setting up variables for `add_subdirectory(flang)` is reasonable.

### 💡 SUGGESTION: MLIR dependency hack fragility

```cmake
add_dependencies(FortranSupport MLIRBuiltinTypeInterfacesIncGen)
add_dependencies(FIRSupport MLIRLinalgOpsIncGen)
```

These dependency fixes are annotated as "hacks" for tablegen not propagating across `add_subdirectory` boundaries. This is fragile — if MLIR/Flang internal targets change names, these break silently. The comment explains the issue well, but this is the most maintenance-sensitive part of the change.

---

### 8. amd-llvm-offload/CMakeLists.txt (New File)

Clean, well-commented standalone runtimes build. The `CMAKE_DISABLE_FIND_PACKAGE_FFI` workaround is well-documented with a TODO.

The conditional flang-rt inclusion when `THEROCK_ENABLE_FLANG` is ON is cleanly handled.

---

### 9. Pre-hook Changes (base/pre_hook_amd-llvm.cmake)

The stripping of offload/flang configuration is appropriate — those are now in their own CMakeLists.txt. The `CLANG_LINK_FLANG OFF` addition prevents the base build from creating a dangling symlink. The comment about `OPENMP_ENABLE_LIBOMPTARGET` staying ON is thorough and accurate.

---

### 10. OpenMP -isystem Patch (0011)

```
Subject: [PATCH] [openmp] Remove clang resource dir from OpenMP::omp
 INTERFACE_INCLUDE_DIRECTORIES
```

No existing 0011 patch on main. The fix removes `target_include_directories(omp PUBLIC ...)` that injected the clang resource dir, breaking `#include_next` chains with GCC 14. The `-fopenmp` flag already makes clang find `omp.h`. Narrowly scoped and correct.

---

### 11. Math-libs Fortran Gating

The `if(ROCM_BUILD_FORTRAN_LIBS)` guards in `math-libs/CMakeLists.txt` and `math-libs/BLAS/CMakeLists.txt` are clean. The variable is propagated via `GLOBAL_CMAKE_VARS` when the `BUILD_FORTRAN_LIBS` flag is ON, and unset (falsy) when OFF.

---

## Recommendations

### ❌ REQUIRED (Blocking):

None.

### ✅ Recommended:

1. Fix the `FORTRAN_REQUIRED` error message to accurately reflect what is checked (THEROCK_ENABLE_FLANG is OFF), not claim a system compiler check that doesn't happen.

### 💡 Consider:

1. `amd-llvm-flang` artifact_deps could be `["amd-llvm-base"]` for semantic accuracy
2. `amd-llvm-offload` could have `feature_group = "ALL"` for consistency with sibling artifacts
3. Add a brief comment on the Fortran compiler path explaining which sub-project produces it
4. The MLIR dependency hacks in `amd-llvm-flang/CMakeLists.txt` are fragile — consider adding a comment about how to diagnose when they go stale

### 📋 Future Follow-up:

1. Collapse compiler and core directories (mentioned in PR description as future refactor)
2. Upstream the FFI find_package fix to `LibomptargetGetDependencies.cmake`
3. Upstream the MLIR tablegen dependency propagation fix

---

## Testing Recommendations

- Full clean build on Linux with `gfx1201` (author reports this passes)
- Windows build (flang/offload disabled via `disable_platforms`)
- Verify `THEROCK_ENABLE_FLANG=OFF` properly skips flang and offload doesn't error
- Verify the OpenMP patch: `openmpTargets.cmake` in install tree should not contain `INTERFACE_INCLUDE_DIRECTORIES` pointing to the clang resource dir
- Build a math-lib (rocFFT/rocBLAS) and verify no `cstdint` errors
- Multi-arch CI: confirm `configure_stage.py` auto-generates correct features for the new artifacts

---

## Conclusion

**Approval Status: ✅ APPROVED**

This is a well-structured decomposition of the LLVM monolith that achieves clear goals (bootstrappable compiler, independent Fortran gating, shorter critical path). The only recommended change is making the Fortran error message accurate. The suggestions are minor improvements that don't block merging. The main risk area is the MLIR dependency hacks in the flang CMakeLists.txt, but those are inherent to the out-of-tree build approach and are properly documented.
