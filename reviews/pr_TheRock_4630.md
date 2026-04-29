# PR Review: Re-admit hipSOLVER fortran shim in kpack-split devel wheel

* **PR:** [#4630](https://github.com/ROCm/TheRock/pull/4630)
* **Author:** marbre (Marius Brehler)
* **Base:** `main` ← `users/marbre/fix-kpack-split-devel-fortran`
* **Reviewed:** 2026-04-16

---

## Summary

The kpack-split devel wheel excludes the `test` component, which drops `libhipsolver_fortran.so*` — a shared library required by `hipsolver-targets.cmake`'s exported `roc::hipsolver_fortran` target. Downstream consumers (e.g. PyTorch) fail at CMake configure time because the imported location doesn't exist.

This PR adds a `component_include_overrides` mechanism to `populate_devel_files` that selectively re-admits specific file patterns from otherwise-excluded components. It's wired for the hipsolver fortran case: `{"test": ["lib/libhipsolver_fortran.so*"]}`.

**Net changes:** +51 lines, -2 lines across 2 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The problem is real, but there's a question of whether the fix belongs in the packaging layer or the artifact descriptor. The override mechanism adds complexity to work around a mismatch that originates in the artifact descriptors and CMake exports.

**Strengths:**

- Well-motivated: clear problem statement with exact error message
- Thorough testing: end-to-end validation with PyTorch build
- Implementation is correct if this layer is the right place for the fix

**Blocking Issues:**

- The fix should be evaluated against simpler alternatives at the descriptor/CMake level

---

## Detailed Review

### 1. ❌ BLOCKING: Wrong layer for the fix — descriptor vs. packaging workaround

#### Background

[PR #326](https://github.com/ROCm/TheRock/pull/326) (by the same author) originally added `libhipblas_fortran.so` to the artifact system. A reviewer asked if the `lib` exclude was intentional, and marbre explained: *"It is only built if the clients are built. Thus yes, this is intentional."* The fortran shim is a build artifact of the client/test configuration (`BUILD_CLIENTS`), not the core library build. hipSOLVER's descriptor follows the same pattern.

This gives a stronger rationale than the PR description's claim about libgfortran dependencies. The `.so` is genuinely a client-build artifact.

#### The mismatch

The real problem is a **mismatch between `dev` and `lib`**: the `dev` component exports the CMake target `roc::hipsolver_fortran` (via `hipsolver-targets.cmake`) with an `IMPORTED_LOCATION` pointing at the shim, but the `lib` component doesn't include the file. The `dev` component promises something that `lib` doesn't deliver.

This mismatch existed before kpack-split but was masked because the full artifact tree was available. The kpack-split `exclude_components=["test"]` exposed it.

#### Alternatives to consider

| Option | Pros | Cons |
|--------|------|------|
| **A. Move shim to `lib` in descriptor** | 2-line TOML change, no new machinery | Miscategorizes a client-build artifact; may need to do the same for hipBLAS |
| **B. Stop exporting the CMake target in `dev`** | Fixes the mismatch at the source | Breaks downstream consumers who need fortran bindings; requires upstream hipSOLVER patch |
| **C. This PR's override approach** | No descriptor changes needed; precise | 40+ lines of new generic machinery for a single use case; fixes symptom, not cause |
| **D. Move shim to `dev` in descriptor** | Keeps it out of `lib` runtime; available to devel consumers | Semantically odd (it's a `.so`, not a build-time-only file); but `dev` is combined with `lib` in practice |

Option A is the simplest and fixes the root cause. The "miscategorization" concern is mild — `lib` means "files needed to depend on the artifact as a library at runtime," and a shared library that CMake targets reference fits that definition regardless of which build flag gates its compilation. The same fix should apply to hipBLAS's `libhipblas_fortran.so`.

Option C (this PR) adds a generic mechanism (`component_include_overrides`) that currently has exactly one consumer. The complexity isn't justified if a descriptor change resolves the issue.

**Required action:** Evaluate whether moving the shim to `lib` (or `dev`) in `artifact-blas.toml` resolves the problem. If there's a concrete reason that doesn't work (beyond the build-flag provenance), document it and the override approach becomes justified.

### 2. ⚠️ IMPORTANT: Mutable default argument (if the override approach is kept)

```python
component_include_overrides: Mapping[str, Sequence[str]] = {},
```

Mutable dict as default argument. Should be `= None` with a guard in the method body.

### 3. 💡 SUGGESTION: hipBLAS has the same pattern

[`artifact-blas.toml`](https://github.com/ROCm/TheRock/blob/main/math-libs/BLAS/artifact-blas.toml) lines 49-51 exclude `libhipblas_fortran.so` from `lib` and include it in `test` (line 61). If hipBLAS also exports a `roc::hipblas_fortran` CMake target, the same downstream breakage will occur. Whichever fix is chosen should address both.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. **Resolve the `dev`/`lib` mismatch at the source** — Either move the shim to `lib` (or `dev`) in the artifact descriptor, or stop exporting the CMake target. If neither is feasible, document the constraint and the override approach becomes the right fallback.

### ⚠️ Recommended (if override approach is kept):

1. **Mutable default** — Change `= {}` to `= None` with a guard.

### 💡 Consider:

1. **Fix hipBLAS too** — Same `lib`-exclude + `test`-include pattern for `libhipblas_fortran.so`.

---

## Testing Recommendations

If the descriptor fix is applied:
- Rebuild artifacts and verify the fortran shim appears in `blas_lib_*` (or `blas_dev_*`) instead of `blas_test_*`
- Verify the devel wheel includes it without any override
- Re-run the PyTorch build to confirm the CMake import check passes
- Verify consumers not using fortran bindings don't encounter issues

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The downstream breakage is real and well-diagnosed. The core issue is a mismatch: `dev` exports a CMake target for the fortran shim, but the shim lives in `test` (excluded from devel wheels). The simplest fix is moving the shim to `lib` in `artifact-blas.toml` — it's a shared library that CMake targets reference, which fits the `lib` component's purpose. The 40-line override mechanism in `py_packaging.py` is a workaround that should only be adopted if the descriptor fix is concretely infeasible.
