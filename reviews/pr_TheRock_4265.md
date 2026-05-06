# PR Review: Make artifact archives reproducible

* **PR:** https://github.com/ROCm/TheRock/pull/4265
* **Author:** PeterCDMcLean
* **Branch:** `users/pmclean/normalize_archive_metadata` → `main`
* **Reviewed:** 2026-05-04
* **Issue:** Part of https://github.com/ROCm/TheRock/issues/4202

---

## Summary

Normalizes tar metadata in artifact archives to ensure identical file content produces identical archives. Three changes:
1. Sets mtime to 0 (Unix epoch) for all archive entries
2. Sets uid/gid to 0 and uname/gname to "root" for consistency
3. Sorts files before adding to ensure deterministic ordering

**Net changes:** +30 lines, -3 lines across 1 file (`build_tools/fileset_tool.py`)

---

## Overall Assessment

**✅ APPROVED** - Clean, well-scoped change that solves a real problem correctly.

**Strengths:**

- Minimal, focused diff — only touches what's needed
- Uses the standard Python `tarfile` filter API (idiomatic approach)
- Good docstring on `_normalize_tarinfo` explaining extraction behavior
- Thorough testing: ran CI twice with no changes and documented remaining diffs
- All remaining diffs are in compiled binary content (GPU kernels, static libs), not archive metadata — confirming the fix works

**No blocking or important issues.**

---

## Detailed Review

### 1. `_normalize_tarinfo` function

The implementation is correct and complete. All non-deterministic metadata fields are normalized:
- `mtime = 0` — eliminates timestamp variation
- `uid/gid = 0` — eliminates builder identity variation
- `uname/gname = "root"` — consistent with uid/gid=0

File permissions are intentionally preserved (mode is not touched), which is the right call.

### 2. File ordering

`sorted(pm.all.items())` sorts by dict key (relative path string), providing stable lexicographic ordering. This is correct and sufficient.

### 3. Filter application

The `filter=_normalize_tarinfo` parameter is applied to both `arc.add()` call sites:
- The manifest file (line ~107-111 in the PR)
- Each content file (line ~121-127 in the PR)

This is complete for the `do_artifact_archive` function.

---

## Analysis of Test Results

The artifact comparison file (`artifact_comparison_results.txt`) shows 56 artifacts still differ between builds. Examining the changed files reveals they are **all compiled binaries**:

| Category | Examples |
|----------|----------|
| GPU kernel objects | `.hsaco`, `.co` (Tensile libraries) |
| Binary data | `.dat` (TensileLibrary lazy loading data) |
| Static libraries | `.a` (libbacktrace, libcap) |
| Shared libraries | `.so` (hipsparselt kernel) |
| Build system | `CTestTestfile.cmake`, `.kpack` |

These diffs are due to non-deterministic compilation output (embedded timestamps in object files, parallelism-dependent codegen, etc.) — completely outside the scope of this PR. The PR correctly addresses the "same content, different hash" problem caused by tar metadata.

---

## Recommendations

### 💡 SUGGESTION: Consider the `py_packaging.py` archive path

[`_therock_utils/py_packaging.py:550-556`](https://github.com/ROCm/TheRock/blob/main/build_tools/_therock_utils/py_packaging.py#L550-L556) also creates tar archives (for devel tarballs) without metadata normalization or sorted file ordering (`os.walk` order is filesystem-dependent). If reproducibility matters there too, the same pattern could be applied.

### 📋 FUTURE WORK: Non-deterministic compilation

The 56 remaining non-reproducible artifacts are all due to compiled binary content. Fully reproducible builds would require:
- Deterministic GPU kernel compilation (Tensile/hipBLASLt/hipSPARSELt)
- Deterministic builds of system deps (libbacktrace, libcap)
- Stripping/normalizing timestamps embedded in object files

This is a much larger effort tracked by issue #4202.

---

## Testing Recommendations

The CI-based "build twice and compare" test plan is appropriate for this change. No unit test is strictly necessary — the behavior is straightforward and the integration test (CI comparison) provides stronger validation than a unit test would.

---

## Conclusion

**Approval Status: ✅ APPROVED**

Clean, correct implementation using standard Python APIs. The test results confirm it eliminates archive-metadata-based hash differences while correctly leaving compiled-binary differences alone. Ready to merge.
