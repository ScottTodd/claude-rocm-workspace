# PR Review: Fix device wheel RPATH for per-arch ELF .so files

* **PR:** [#4584](https://github.com/ROCm/TheRock/pull/4584)
* **Author:** marbre (Marius Brehler)
* **Branch:** `users/marbre/fix-device-wheel-rpath` → `main`
* **Reviewed:** 2026-04-15

---

## Summary

Per-arch MIOpen CK builds produce real ELF shared libraries (e.g.
`libMIOpenCKGroupedConv_gfx1201.so`) that end up in device wheels. These
libraries have dynamic deps on `libamdhip64`, `libamd_comgr`, and
`librocm_sysdeps_sqlite3` from the core wheel, but `populate_device_files()`
was doing a straight copy with no RPATH handling.

This PR:
1. Replaces the inline copy logic in `populate_device_files()` with a call to
   `_populate_file()`, which already handles ELF detection and RPATH patching.
2. Adds `rpath_dep(core, "lib")` and `rpath_dep(core, "lib/rocm_sysdeps/lib")`
   to device packages so patchelf knows which directories to add.

**Net changes:** +14 lines, -18 lines across 2 files

---

## Overall Assessment

**✅ APPROVED** — Clean, well-scoped fix that reuses existing infrastructure.

**Strengths:**

- Eliminates code duplication by delegating to `_populate_file()` instead of
  reimplementing copy logic inline
- The `get_file_type()` function correctly distinguishes `.hsaco`/`.co` files
  (returns `"hsaco"`) from real shared libraries (returns `"so"`), so opaque
  device data passes through without RPATH patching — no risk of corrupting
  non-ELF artifacts
- RPATH deps mirror the `lib` package pattern (lines 96–97 of
  `build_python_packages.py`), keeping the two paths consistent
- Updated docstring accurately describes the new mixed-content behavior

**No blocking or important issues found.**

---

## Detailed Review

### 1. `_therock_utils/py_packaging.py` — `populate_device_files()`

The old code had an inline copy loop (mkdir, symlink resolution, copy2,
mark_populated). The new code calls `self._populate_file(relpath, dest_path,
dir_entry, resolve_src=True)` — the same helper used by
`populate_runtime_files()`.

`_populate_file()` already handles:
- Directory entries (mkdir)
- Symlink resolution (when `resolve_src=True`)
- Existing file removal
- `shutil.copy2`
- `files.mark_populated`
- ELF detection via `get_file_type()` → RPATH patching for `"exe"`/`"so"` only

This is a strict superset of the old behavior, plus RPATH patching for ELF
files. Non-ELF device artifacts (`.kpack`, `.hsaco`, `.co`, `.dat`, MIOpen
DBs) are unaffected because `get_file_type()` classifies them differently.

### 2. `build_python_packages.py` — `_run_kpack_split()`

Two `rpath_dep` calls added before `populate_device_files()`:
```python
dev.rpath_dep(core, "lib")
dev.rpath_dep(core, "lib/rocm_sysdeps/lib")
```

These match the first two rpath_deps on the `lib` package (lines 96–97).
The `lib` package also has `rpath_dep(core, "lib/host-math/lib")` — this is
not added for device, which seems intentional since per-arch MIOpen CK
libraries depend on HIP/comgr/sqlite3, not host-math.

### 💡 SUGGESTION: Missing `lib/host-math/lib` rpath_dep — intentional?

The `lib` (libraries) package has three rpath_deps:
```python
lib.rpath_dep(core, "lib")
lib.rpath_dep(core, "lib/rocm_sysdeps/lib")
lib.rpath_dep(core, "lib/host-math/lib")
```

The device package only gets the first two. If any future per-arch ELF in the
device wheel depends on host-math libraries, this would need updating. Current
MIOpen CK deps (hip, comgr, sqlite3) don't need it, so this is fine as-is.

---

## Recommendations

### ✅ Recommended:

(none)

### 💡 Consider:

1. If additional per-arch ELF libraries appear in device wheels in the future
   with different dep patterns, consider whether `rpath_dep` should be driven
   by inspecting actual ELF NEEDED entries rather than hardcoded.

---

## Testing Recommendations

- Build kpack-split wheels for a target that includes MIOpen CK (e.g.
  gfx1201) and verify that `readelf -d` on
  `libMIOpenCKGroupedConv_gfx1201.so` inside the device wheel shows RPATH
  entries pointing to the core wheel's `lib/` and `lib/rocm_sysdeps/lib/`
- Verify that `.kpack`, `.hsaco`, and `.dat` files in the device wheel are
  unchanged (no patchelf modifications)

---

## Conclusion

**Approval Status: ✅ APPROVED**

Clean bugfix that reuses existing RPATH infrastructure. The ELF/non-ELF
discrimination via `get_file_type()` ensures only actual shared libraries get
patched. No blocking issues.
