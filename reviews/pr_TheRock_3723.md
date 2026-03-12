# PR Review: Adding OSS rocprof trace decoder

* **PR:** https://github.com/ROCm/TheRock/pull/3723
* **Title:** Adding OSS rocprof trace decoder
* **Author:** ApoKalipse-V (Giovanni Lenzi Baraldi)
* **Reviewed:** 2026-03-12
* **Commits:** 2 commits

---

## Summary

This PR replaces the closed-source binary-only `rocprof-trace-decoder` submodule with the open-source version that now lives in `rocm-systems/projects/rocprof-trace-decoder/`. The closed-source approach required architecture detection at build time to select the right pre-built `.so`; the OSS version builds from source as a normal CMake subproject.

**Net changes:** +20 lines, -131 lines across 10 files

---

## Overall Assessment

**✅ APPROVED** - Clean removal of the binary-only dependency with a well-structured replacement. CI builds and artifact validation all pass.

**Strengths:**

- Significant simplification: removes architecture detection C code, submodule management, and the `THEROCK_ENABLE_ROCPROF_TRACE_DECODER_BINARY` feature flag
- The trace decoder is now always built when the profiler is enabled, which is the right default (it was previously opt-in)
- Good cleanup across all layers: `.gitmodules`, `BUILD_TOPOLOGY.toml`, build scripts, CMakeLists, artifact descriptors
- CI evidence confirms builds pass on all platforms and artifact structure validation succeeds

**No blocking issues.**

---

## Detailed Review

### 1. `profiler/CMakeLists.txt` — Core change

The key transformation: from a conditional binary-install subproject to an unconditional source-build subproject using the `rocm-systems` source tree.

**Changes are correct:**
- `EXTERNAL_SOURCE_DIR` now points to `${THEROCK_ROCM_SYSTEMS_SOURCE_DIR}/projects/rocprof-trace-decoder` — verified this path exists and contains a proper CMakeLists.txt
- `BINARY_DIR` is explicitly set (good practice for out-of-tree sources)
- `INTERFACE_INCLUDE_DIRS` and `INTERFACE_LINK_DIRS` are set for downstream consumers
- Variable rename from `_rocprofiler_sdk_optional_deps` to `_rocprofiler_sdk_common_deps` correctly reflects the semantic change (no longer optional)

### 2. `BUILD_TOPOLOGY.toml` — Source set removal

Removes the `profiler-extras` source set and simplifies the `profiler-apps` artifact group to depend only on `rocm-systems` (which now contains the trace decoder).

Clean and correct.

### 3. `CMakeLists.txt` — Feature flag removal

Removes the `THEROCK_ROCPROF_TRACE_DECODER_BINARY` feature flag entirely. This is the right approach — the OSS version is always built, so there's no need for an opt-in toggle.

### 4. `profiler/artifact-rocprofiler-sdk.toml` — Descriptor update

Removes `optional = true` from the trace decoder component. Since the decoder is now always built, the component is no longer optional.

**CI evidence:** All `Validate Artifact Structure` jobs pass, confirming the descriptor change is correct.

### 5. Build scripts cleanup

`bump_submodules.py` and `fetch_sources.py` — removes references to the old submodule. Clean.

### 6. Deleted files

`profiler/rocprof-trace-decoder/CMakeLists.txt`, `compute_release_directory.c`, and the `binaries` submodule — all part of the old binary-only approach. Correct removal.

---

### ⚠️ IMPORTANT: Stale references to removed flag in miopen Dockerfile

`rocm-libraries/projects/miopen/Dockerfile` (lines 190, 214) still passes `-DTHEROCK_ENABLE_ROCPROF_TRACE_DECODER_BINARY=ON`. Since this flag no longer exists, CMake will silently ignore it, so it won't break anything. However, it's dead configuration.

**Recommendation:** File a follow-up to clean up the miopen Dockerfile, or coordinate with the miopen team. This is in a submodule so it can't be fixed in this PR.

### 💡 SUGGESTION: Stale comment in artifact descriptor

The TOML comment still says `# rocprof-trace-decoder-binary` — wait, looking at the diff again, the PR *does* update this to `# rocprof-trace-decoder`. Good.

### 💡 SUGGESTION: `CMakePresets.json` sanitizer entries

`CMakePresets.json` has `rocprof-trace-decoder_SANITIZER` entries in multiple presets. These will now pass through to the OSS project's CMake, which does support sanitizers, so this should continue to work correctly. No action needed.

### 📋 FUTURE WORK: rocm-systems submodule bump

The PR body notes "Requirements: rocm-systems commit c8f55d9b86fbafd8c17b40b89fdde64e19303e56". The diff doesn't show a rocm-systems submodule bump, so presumably the required commit is already on the `rocm-systems` branch that `main` tracks (or will be merged before this PR). CI passing confirms the required code is present in the test environment.

---

## Recommendations

### ✅ Recommended:

1. Ensure the required rocm-systems commit is merged/available before this PR lands
2. File a follow-up issue to clean up the stale `THEROCK_ENABLE_ROCPROF_TRACE_DECODER_BINARY` reference in `rocm-libraries/projects/miopen/Dockerfile`

### 📋 Future Follow-up:

1. Some documentation in `rocm-systems` (e.g., `aqlprofile/README.md`, `rocprofiler-sdk` docs) still references the binary release page on GitHub. These should be updated to reflect that the decoder is now built from source, but that's in the `rocm-systems` submodule scope.

---

## Testing Recommendations

- Builds pass on all CI platforms (Linux gfx94X, gfx110X, gfx1151, gfx120X; Windows gfx110X, gfx1151, gfx120X) ✅
- Artifact structure validation passes on all variants ✅
- Recommend verifying that `rocprofv3 --att` works correctly with the OSS decoder on a real GPU (functional test)

---

## Conclusion

**Approval Status: ✅ APPROVED**

This is a clean, well-scoped PR that replaces a closed-source binary blob with an open-source build-from-source approach. The change simplifies the build topology, removes architecture detection hacks, and makes the trace decoder a standard part of the profiler build. CI evidence confirms everything works.
