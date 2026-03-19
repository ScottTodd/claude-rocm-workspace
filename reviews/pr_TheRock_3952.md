# PR Review: Extract hipdnn into new ml-libs-generic artifact group

* **PR:** [#3952](https://github.com/ROCm/TheRock/pull/3952)
* **Author:** marbre (Marius Brehler)
* **Reviewed:** 2026-03-16
* **Base:** `main`
* **Branch:** `users/marbre/multi-arch-hipdnn-generic`

---

## Summary

Moves the `hipdnn` artifact from the per-arch `ml-libs` group (built once per GPU family in the `math-libs` stage) into a new generic `ml-libs-generic` group with its own CI stage. This correctly reflects that hipdnn is architecture-independent — its dependencies (core-runtime, core-hip, spdlog) are all available after the compiler-runtime stage.

**Net changes:** +66 lines, -16 lines across 3 files

---

## Overall Assessment

**✅ APPROVED** — Clean, well-motivated change that correctly models the dependency graph.

**Strengths:**

- Accurately reflects hipdnn's architecture-independent nature
- Eliminates redundant per-arch builds of hipdnn (previously built once per GPU family for no reason)
- Dependency chains verified: `ml-libs-generic` deps (`hip-runtime`, `third-party-libs`) cover all CMake build/runtime deps (fmt, spdlog, flatbuffers, nlohmann-json via third-party-libs; hip-clr via hip-runtime)
- fusilli-libs `needs:` correctly narrowed from `math-libs` to `ml-libs-generic` (fusilliprovider only needs hipdnn, not math-libs)
- `ml-libs` group correctly updated with `ml-libs-generic` in `artifact_group_deps` so miopenprovider, hipblasltprovider, and hipdnn-samples can still find hipdnn
- CI run passes on both Linux and Windows with all stages green

**Issues:**

- ⚠️ IMPORTANT: Workflow header comments say ml-libs-generic is "parallel to math-libs", but math-libs actually depends on it.

---

## Detailed Review

### 1. BUILD_TOPOLOGY.toml

**Changes are correct and consistent:**

- New `build_stages.ml-libs-generic` with `artifact_groups = ["ml-libs-generic"]`
- New `artifact_groups.ml-libs-generic` with `type = "generic"`, `artifact_group_deps = ["hip-runtime", "third-party-libs"]`
- `artifacts.hipdnn` moved from `artifact_group = "ml-libs"` to `artifact_group = "ml-libs-generic"`
- `artifact_groups.ml-libs` gains `"ml-libs-generic"` in deps — needed for miopenprovider/hipblasltprovider/hipdnn-samples
- `artifact_groups.fusilli-libs` gains `"ml-libs-generic"` in deps — needed for fusilliprovider
- `build_stages.fusilli-libs` description updated

**Verified:** The `third-party-libs` dependency covers all of hipdnn's CMake deps not already in `hip-runtime`: `therock-fmt`, `therock-spdlog`, `therock-flatbuffers`, `therock-nlohmann-json` are all in the `third-party-libs` artifact group.

**Verified:** `ml-libs/CMakeLists.txt` uses `if(THEROCK_ENABLE_HIPDNN)` guards, so when `configure_stage.py` enables only HIPDNN for the `ml-libs-generic` stage, only hipdnn builds — the other ml-libs artifacts are correctly skipped.

### 2. multi_arch_build_portable_linux.yml

- New `ml-libs-generic` job added with `needs: compiler-runtime` — correct
- `math-libs` updated to `needs: [compiler-runtime, ml-libs-generic]` — needed because ml-libs (still in math-libs stage) depends on hipdnn from ml-libs-generic
- `fusilli-libs` narrowed from `needs: [compiler-runtime, math-libs, iree-compiler]` to `needs: [compiler-runtime, ml-libs-generic, iree-compiler]` — correct; fusilliprovider depends on hipdnn (now in ml-libs-generic), not on math-libs
- Permissions block included (`contents: read`, `id-token: write`)

### ⚠️ IMPORTANT: Misleading "parallel to math-libs" comments

Both workflow header comments describe ml-libs-generic as "parallel to math-libs":

```
# 3. ml-libs-generic (generic) - hipdnn (parallel to math-libs)
# 4. math-libs (per-arch) - BLAS, FFT, etc. (needs ml-libs-generic for ml-libs group)
```

Line 4 correctly says math-libs needs ml-libs-generic, but line 3 contradicts this by saying they're parallel. ml-libs-generic is a *prerequisite* of math-libs, not parallel to it. Same issue in the Windows workflow.

**Recommendation:** Change the comment to something like:
```
# 3. ml-libs-generic (generic) - hipdnn (prerequisite of math-libs)
```

### 3. multi_arch_build_windows.yml

- Same structural changes as Linux: new `ml-libs-generic` job, updated `math-libs` needs
- No fusilli-libs changes needed (Windows has no fusilli-libs stage) — correct
- Includes `build_variant_cmake_preset` input (Windows-specific) — correct

### 💡 SUGGESTION: Timeout for ml-libs-generic

The new stage uses `timeout_minutes: 60`. hipdnn is a relatively small build, so this is likely generous — not a problem, just noting it's conservative.

### 📋 FUTURE WORK: Stage ordering in BUILD_TOPOLOGY.toml

The new `build_stages.ml-libs-generic` is inserted between `compiler-runtime` and `math-libs`, which makes sense for readability since it runs after compiler-runtime and before math-libs. The artifact group `ml-libs-generic` is placed right before `ml-libs`. Both are reasonable positions. No action needed.

---

## Recommendations

### ❌ REQUIRED (Blocking):

None.

### ✅ Recommended:

1. Fix the "parallel to math-libs" comments in both workflow files — ml-libs-generic is a prerequisite of math-libs, not parallel to it.

### 💡 Consider:

1. The 60-minute timeout for ml-libs-generic is generous for just hipdnn. Could be tightened to 30 minutes, but this isn't important.

### 📋 Future Follow-up:

1. If more architecture-neutral ML libraries emerge, they can be added to `ml-libs-generic` without further workflow changes.

---

## CI Evidence

The linked multi-arch CI run ([#23029434143](https://github.com/ROCm/TheRock/actions/runs/23029434143)) passed all jobs:

- `ml-libs-generic` completed successfully on both Linux and Windows
- `math-libs` completed for all arch variants (gfx1151, gfx94X-dcgpu on Linux; gfx120X-all, gfx1151 on Windows)
- `fusilli-libs` completed successfully on Linux
- Artifact validation passed on both platforms
- Tests passed (hipdnn, hipdnn-samples) on gfx94X-dcgpu and gfx1151

---

## Conclusion

**Approval Status: ✅ APPROVED**

Well-motivated, correctly implemented. The dependency graph changes are sound, the CI validates the change end-to-end, and the workflow structure matches the topology. Ready for merge.
