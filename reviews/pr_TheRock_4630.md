# PR Review: Re-admit hipSOLVER fortran shim in kpack-split devel wheel

* **PR:** [#4630](https://github.com/ROCm/TheRock/pull/4630)
* **Author:** marbre (Marius Brehler)
* **Base:** `main` ← `users/marbre/fix-kpack-split-devel-fortran`
* **Reviewed:** 2026-04-16

---

## Summary

The kpack-split devel wheel excludes the `test` component, which inadvertently drops `libhipsolver_fortran.so*` — a shared library required by `hipsolver-targets.cmake`'s exported `roc::hipsolver_fortran` target. Downstream consumers (e.g. PyTorch) fail at CMake configure time because the imported location doesn't exist.

This PR adds a `component_include_overrides` mechanism to `populate_devel_files` that selectively re-admits specific file patterns from otherwise-excluded components. It's wired for the hipsolver fortran case: `{"test": ["lib/libhipsolver_fortran.so*"]}`.

**Net changes:** +51 lines, -2 lines across 2 files

---

## Overall Assessment

**✅ APPROVED** — Clean, well-scoped fix for a real downstream breakage. The override mechanism is appropriately narrow and the implementation correctly reuses existing infrastructure (`filter_artifacts`, `_populate_devel_file`).

**Strengths:**

- Well-motivated: clear problem statement with exact error message
- Narrow scope: override only admits the specific files needed
- Thorough testing: end-to-end validation with PyTorch build
- Good documentation: docstring explains the rationale and gives a concrete example
- Correct reuse of existing `filter_artifacts` + `_populate_devel_file` path

**Issues:**

- One mutable default argument (important)

---

## Detailed Review

### 1. `py_packaging.py` — `populate_devel_files`

#### ⚠️ IMPORTANT: Mutable default argument

```python
component_include_overrides: Mapping[str, Sequence[str]] = {},
```

The default value `{}` is a mutable dict. While `Mapping` is an abstract type that signals read-only intent, the actual default object is still a mutable `dict` shared across all calls. This is a well-known Python footgun. In this specific case it's safe because the code never mutates the argument, but it violates the standard Python convention and will trigger linting warnings.

**Recommendation:** Use `None` with a docstring-level default, or use `types.MappingProxyType({})`:

```python
component_include_overrides: Mapping[str, Sequence[str]] | None = None,
```

Then at the top of the method body:
```python
if component_include_overrides is None:
    component_include_overrides = {}
```

#### 💡 SUGGESTION: Closure variable capture

The inner function `_override_filter` captures `component` via the default argument trick `_c=component`:

```python
def _override_filter(an: ArtifactName, _c=component) -> bool:
```

This is correct and avoids the classic late-binding closure bug. The pattern is idiomatic Python, though some style guides prefer `functools.partial`. No action needed — just noting it's done correctly.

### 2. `build_python_packages.py` — `_run_kpack_split`

The wiring is clean. The comment explains why the override is needed and the glob pattern `lib/libhipsolver_fortran.so*` is appropriately narrow — it matches the `.so`, `.so.1`, and `.so.1.0` symlink chain and nothing else from the test component.

No issues found.

---

## Recommendations

### ✅ Recommended:

1. **Mutable default argument** — Change `= {}` to `= None` with a guard, per standard Python convention.

### 💡 Consider:

1. No additional suggestions — the implementation is clean.

### 📋 Future Follow-up:

1. If more overrides accumulate over time, consider whether the root cause (fortran shim landing in `test` component) should be fixed upstream in the artifact descriptor instead. For now, a single override is the right pragmatic fix.

---

## Testing Recommendations

The author has already validated:
- Repackaged locally against kpack-split artifacts (gfx1200/gfx1201)
- Confirmed devel wheel contains `libhipsolver_fortran.so{,.1,.1.0}` but not test/bench binaries
- End-to-end PyTorch release/2.10 build passes the hipsolver import check

No additional testing recommended.

---

## Conclusion

**Approval Status: ✅ APPROVED**

Well-scoped fix for a real downstream breakage. The mutable default is a minor style issue worth fixing but not blocking. The override mechanism is appropriately narrow and well-documented.
