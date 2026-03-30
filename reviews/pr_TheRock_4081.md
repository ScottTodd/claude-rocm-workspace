# PR Review: Update submodule pointer for compiler 7.13 : ww11

* **PR:** [#4081](https://github.com/ROCm/TheRock/pull/4081)
* **Author:** ronlieb
* **Branch:** `amd/dev/rlieberm/SMPbumpWW11-7.13` → `main`
* **Reviewed:** 2026-03-30
* **Status:** OPEN (CI in progress)

---

## Summary

Routine compiler submodule bump to amd-compiler-ww-2026-11 (branch base 2026-03-12), updating three submodules:

- **amd-llvm**: `926d90666f` → `bc4a1dd0d146` (3943 commits — AMDGPU features, GFX1250 fixes, SLP vectorizer fixes, plus 5 cherry-picks)
- **hipify**: `86c76dc618` → `e40c4f7006` (52 commits — O(1) Hash Architecture perf optimization, cuDNN 9.19.1 support)
- **spirv-llvm-translator**: `d575617fd4` → `aa7c842d4e` (56 commits — SPV_AMD_weak_linkage, FP4/FP8 support, ldexp intrinsics)

Also removes `0010-Comgr-Add-COMGR_STATIC_LLVM-option-for-static-LLVM-l.patch` (now upstreamed).

**Net changes:** +3 lines, -57 lines across 4 files

---

## Overall Assessment

**✅ APPROVED** — Standard submodule bump with clean patch removal. No code logic in this repo is changing; risk is limited to the submodule contents themselves, which are validated by CI.

**Strengths:**

- Thorough PR description with per-submodule change summaries, cherry-pick table, and patch removal note
- Foundation stages passing on both Linux and Windows
- Clean patch removal (upstreamed, not just dropped)

---

## Detailed Review

### 1. Submodule Hash Discrepancy in PR Description

### ⚠️ IMPORTANT: PR body "To" hash doesn't match actual submodule pointer

The PR body's submodule table lists amd-llvm "To" as `9edd77d6cd` (the branch base), but the actual submodule pointer in the diff is `bc4a1dd0d146` (the latest cherry-pick, dated 2026-03-27). The cherry-pick table below does document `bc4a1dd0d146`, so the information is present — but someone scanning the summary table alone would see a stale hash.

- **Recommendation:** Update the "To" column in the submodule table to `bc4a1dd0d146` (or note "(+ cherry-picks)" next to the branch base hash) so the table matches the actual pointer.

### 2. Patch Removal

The removed patch (`0010-Comgr-Add-COMGR_STATIC_LLVM-option-for-static-LLVM-l.patch`) adds a `COMGR_STATIC_LLVM` CMake option to `amd/comgr/CMakeLists.txt`. The PR description states this is now upstreamed into the amd-llvm submodule. This is the expected lifecycle for patches in TheRock — carry locally until upstream absorbs the change.

No issues here.

### 3. Cherry-Picks

Five cherry-picks applied after the branch base date (2026-03-12):

| Commit | Date | Description |
|--------|------|-------------|
| `bc4a1dd0d146` | 2026-03-27 | [Driver][HIP] Fix bundled -S emitting bitcode instead of assembly for device |
| `9edd77d6cd3c` | 2026-03-26 | [Driver][HIP] Bundle AMDGPU -S output |
| `307111f14ba9` | 2026-03-19 | Revert "[Clang][CodeGen] Restore isEmptyFieldForLayout" |
| `9d9a04b3ba40` | 2026-03-11 | [Comgr] Fix metadata merge for amdhsa.printf |
| `c8b66c11df56` | 2026-03-19 | Revert "[AMDGPU] Generate more swaps" |

Two reverts and three fixes — reasonable for a stabilization branch. The HIP assembly bundling fix and the Comgr printf metadata fix address specific correctness issues.

### 4. CI Status

At time of review:
- **Passing:** Foundation stages (Linux + Windows), unit tests, pre-commit
- **Pending:** Compiler-runtime stages (Linux + Windows)
- **Skipping:** Single-arch variant builds (expected for multi-arch CI)

Foundation passing is a good early signal. Full validation depends on compiler-runtime and downstream stages completing.

### 5. Build Log Size Comparison (gfx94X-dcgpu)

Compared log file sizes between [before](https://therock-nightly-artifacts.s3.amazonaws.com/23578094439-linux/logs/gfx94X-dcgpu/index.html) (run 23578094439, main) and [after](https://therock-dev-artifacts.s3.amazonaws.com/23655164842-linux/logs/gfx94X-dcgpu/index.html) (run 23655164842, this PR). Top 10 size increases:

```markdown
| File | Before | After | Increase |
|------|--------|-------|----------|
| composable_kernel_build.log | 431 KB | 3 MB | ~2.6 MB |
| rocm_smi_lib_build.log | 8 KB | 15 KB | ~7 KB |
| rocSOLVER_build.log | 58 KB | 62 KB | ~4 KB |
| rocWMMA_build.log | 179 KB | 183 KB | ~4 KB |
| rocRAND_build.log | 81 KB | 83 KB | ~2 KB |
| hipSPARSE_build.log | 414 KB | 416 KB | ~2 KB |
| therock-SuiteSparse_configure.log | 14 KB | 16 KB | ~2 KB |
| rocshmem_configure.log | 6 KB | 8 KB | ~2 KB |
| rocBLAS_build.log | 123 KB | 124 KB | ~1 KB |
| rocThrust_build.log | 91 KB | 92 KB | ~1 KB |
```

**composable_kernel_build.log** is the outlier (~7x increase). The new output is ~60+ `ld.lld` linker warnings, all the same pattern:

```
ld.lld: warning: <unknown>:0:0: failed to meet occupancy target given by
'amdgpu-waves-per-eu' in '<mangled CK kernel>':
desired occupancy was 2, final occupancy is 1
```

These hit grouped convolution backward-data/weight kernels across f16/f32/bf16 data types. Each warning includes a very long mangled template name, which accounts for the size blowup. These are **performance warnings, not correctness issues** — the linker is reporting that certain CK kernels couldn't achieve the requested wave occupancy (got 1 instead of 2). Likely the new `ld.lld` is more aggressive about reporting occupancy misses that the previous linker silently accepted.

The remaining increases (items 2–10) are all small and within normal noise.

Notable decreases: `amd-comgr_build.log` (5 KB → 2 KB), `therock-flatbuffers_build.log` (16 KB → 3 KB), `amd-llvm_build.log` (2 MB → 1 MB) — likely warnings eliminated by upstreamed fixes.

---

## Recommendations

### ✅ Recommended:

1. Update the amd-llvm "To" hash in the PR body to match the actual submodule pointer (`bc4a1dd0d146`) or annotate it with "+ cherry-picks"

### 💡 Consider:

1. Nothing additional — this is a clean, well-documented submodule bump

---

## Testing Recommendations

- Wait for full CI pipeline completion (compiler-runtime and downstream stages)
- No additional manual testing needed beyond CI — this is a submodule pointer update

---

## Conclusion

**Approval Status: ✅ APPROVED**

Straightforward compiler submodule bump with good documentation. The only actionable item is a minor discrepancy in the PR description's hash table. CI should be monitored to completion before merging.
