# PR Review: Windows reproducible build & ccache hit rate improvement

* **PR:** [#4419](https://github.com/ROCm/TheRock/pull/4419)
* **Author:** amd-nicknick (Nick Kuo)
* **Branch:** `users/nicknick/win-ccache-repro` → `main`
* **Reviewed:** 2026-04-23
* **Status:** OPEN
* **References:** Fixes #4519, parent issue #4195

---

## Summary

This PR improves Windows ccache hit rates through several complementary changes:
1. Reproducible builds via `/Brepro` linker flag (zeroes timestamps in PE headers)
2. `compiler_check = content` on Windows (static-linked LLVM toolchain makes content hashing sufficient)
3. PCH sloppiness (`pch_defines`, `time_macros`) to support amd-llvm's default precompiled headers on Windows
4. Misc: bump `max_size` to 10G, rename `secondary_storage` → `remote_storage`

**Net changes:** +36 lines, -19 lines across 2 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The ccache changes are well-motivated with strong test results (98.82% hit rate). The `/Brepro` placement has a correctness concern regarding compiler compatibility.

**Strengths:**
- Clear test results demonstrating the improvement
- Good comments explaining each sloppiness flag
- Addresses a real problem (non-deterministic builds defeating caching)

**Issues:**
- `/Brepro` placement applies to all compilers including cases where it may not be appropriate

---

## Detailed Review

### 1. `cmake/therock_subproject.cmake` — `/Brepro` placement

**⚠️ IMPORTANT: `/Brepro` is injected unconditionally for all Windows subprojects regardless of compiler toolchain**

The current placement at line ~838 (after `_compiler_toolchain_init_contents`) means `add_link_options("LINKER:/Brepro")` is emitted into the project init file for every Windows subproject. This works because:
- MSVC `link.exe` supports `/Brepro` natively
- `lld-link` (used by amd-llvm/amd-hip) also supports `/Brepro`

So functionally this is correct for the linkers TheRock actually uses today. However, there are a couple of considerations:

1. **The `LINKER:` prefix and CMake's `CMAKE_LINKER_TYPE`**: Using `add_link_options("LINKER:/Brepro")` relies on CMake translating the flag to the linker's native syntax. For `link.exe` and `lld-link`, `/Brepro` is already native. For a hypothetical GNU ld linker on Windows (unlikely but possible via MinGW), this would be meaningless or error out.

2. **Better placement options:** The existing code already has a three-way branch for linker flags based on toolchain (lines 815-828: `NOT MSVC` vs `amd-llvm`/`amd-hip` vs MSVC). Adding `/Brepro` there — in the MSVC and amd-llvm/amd-hip branches specifically — would be more precise and follow the existing pattern. LLVM's own [`HandleLLVMOptions.cmake`](https://github.com/llvm/llvm-project/blob/main/llvm/cmake/modules/HandleLLVMOptions.cmake) also conditionally adds `/Brepro` only for clang-cl (and checks for `/INCREMENTAL` compatibility).

3. **`/Brepro` as a compiler flag vs. linker flag**: LLVM's approach adds `/Brepro` to `CMAKE_C_FLAGS`/`CMAKE_CXX_FLAGS` (not linker flags), because `/Brepro` also affects the object file timestamps that the compiler emits. The PR only adds it as a linker flag — this means `.obj` files will still contain timestamps, only the final PE headers get zeroed. For ccache purposes (where you're caching compilation, not linking), adding `/Brepro` to compiler flags may also be relevant. However, ccache works at the preprocessor→compilation level, so the linker flag is the important one for deterministic final output. This is probably fine as-is, but worth noting.

**Recommendation:** Move the `/Brepro` injection into the linker-flag branches (lines 815-828) rather than the init file. Something like:

```cmake
elseif(_compiler_toolchain STREQUAL "amd-llvm" OR _compiler_toolchain STREQUAL "amd-hip")
  string(APPEND _init_contents "string(APPEND CMAKE_EXE_LINKER_FLAGS \" -L${_private_link_dir} \")\n")
  string(APPEND _init_contents "string(APPEND CMAKE_SHARED_LINKER_FLAGS \" -L${_private_link_dir} \")\n")
else()
  # The MSVC way.
  string(APPEND _init_contents "string(APPEND CMAKE_EXE_LINKER_FLAGS \" /LIBPATH:${_private_link_dir}\")\n")
  string(APPEND _init_contents "string(APPEND CMAKE_SHARED_LINKER_FLAGS \" /LIBPATH:${_private_link_dir}\")\n")
endif()
```

Actually, that loop is per-link-dir so it's not a great place either. The init contents area (where it currently is) is fine structurally — the question is just whether it needs to be conditional on `_compiler_toolchain`. Since both MSVC and lld-link support `/Brepro`, the unconditional `WIN32` guard is arguably correct and simpler. The existing code works; the risk is low.

**Verdict:** The current placement works for all real-world scenarios in TheRock. Making it conditional on `_compiler_toolchain` would be more principled but isn't strictly necessary. I'd lean toward leaving it as-is or putting it in the toolchain setup function (`_therock_cmake_subproject_setup_toolchain`) alongside the linker flag init settings (lines 1495-1496) where `CMAKE_EXE_LINKER_FLAGS_INIT` and `CMAKE_SHARED_LINKER_FLAGS_INIT` are set. That would keep linker configuration co-located.

### 2. `build_tools/setup_ccache.py` — ccache config changes

**✅ Good: `compiler_check = content` for Windows**

The comment explains the rationale well — statically linked LLVM toolchain means content hashing is sufficient and more reliable than mtime.

**✅ Good: Sloppiness settings**

The expanded sloppiness (`include_file_ctime,pch_defines,time_macros`) is well-documented with clear comments explaining why each flag is needed. The ccache docs link is helpful.

**💡 SUGGESTION: `secondary_storage` → `remote_storage` rename**

This is a ccache 4.8+ config key rename. If any CI runners use ccache < 4.8, this will silently ignore the `remote_storage` key. Presumably the CI runners have modern ccache.

**💡 SUGGESTION: `max_size` bump to 10G**

Per the PR comments, 5G wasn't enough for even one full build. 10G may still be tight for shared remote storage with multiple architectures building simultaneously. The comments on the PR already note this. Worth monitoring.

### 3. `build_tools/setup_ccache.py` — `local` preset max_size

**✅ Good:** Adding `max_size: "10G"` to the `local` preset makes it explicit rather than relying on ccache's default (which was the 5G that caused the author's initial cache pressure issue).

---

## Recommendations

### ✅ Recommended:

1. **Consider where `/Brepro` lives**: The current init-file placement works but could be more precisely co-located with linker flag setup. Two options:
   - **Option A (keep as-is):** The `WIN32` guard is sufficient since all Windows linkers in TheRock support `/Brepro`. Simple and clear.
   - **Option B (move to toolchain setup):** Add `/Brepro` to `CMAKE_EXE_LINKER_FLAGS_INIT` and `CMAKE_SHARED_LINKER_FLAGS_INIT` inside `_therock_cmake_subproject_setup_toolchain` (around line 1495), differentiating between MSVC and clang linker-flag syntax. This co-locates all linker configuration and makes the toolchain-specificity explicit.

### 💡 Consider:

1. Whether `/Brepro` should also be added as a compiler flag (affects `.obj` timestamp metadata), following LLVM's own pattern. Not critical for ccache but improves reproducibility of intermediate outputs.

### 📋 Future Follow-up:

1. Monitor ccache remote storage usage — 10G may still be tight with many architectures sharing it.
2. Verify ccache version on CI runners supports `remote_storage` (vs older `secondary_storage`).

---

## Testing Recommendations

- The PR includes strong local test results (98.82% hit rate on rebuild).
- CI passed for Linux builds. Windows test failures appear to be pre-existing (xfail/known).
- A follow-up CI run after cache warmup would confirm the hit-rate improvement in CI context.

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The ccache configuration changes are well-motivated and well-tested. The main discussion point is where to place `/Brepro` — the current location works functionally for all TheRock compilers, but co-locating it with the linker flag initialization in `_therock_cmake_subproject_setup_toolchain` would be architecturally cleaner. This is more of a design discussion than a hard blocker.
