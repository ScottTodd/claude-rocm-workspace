# PR Review: Fully wire kpack-split into multi-arch Python package CI

* **PR:** [#4487](https://github.com/ROCm/TheRock/pull/4487)
* **Author:** marbre (Marius Brehler)
* **Branch:** `users/marbre/multi-arch-python-kpack-support` → `main`
* **Reviewed:** 2026-04-14
* **Status:** OPEN

---

## Summary

This PR adds the missing wiring to produce kpack-split-enabled Python packages in multi-arch CI. In kpack-split mode, packages are laid out flat (no per-family subdirectories), device wheels are per-target (e.g. `device-gfx942`), and the index is a single top-level `index.html`. The changes span:

1. **Index generation**: Auto-detect flat vs per-family layout in `upload_python_packages.py`; new `generate_flat_index()` in `generate_local_index.py`
2. **Device extras**: Per-target `device-gfx{N}` extras in `setup.py` replace the generic `device` extra that needed `offload-arch` at build time
3. **Workflow wiring**: Thread `kpack_split` and `amdgpu_targets` through `multi_arch_ci_linux.yml` → `test_rocm_wheels.yml` / `build_portable_linux_pytorch_wheels_ci.yml`
4. **PyTorch build**: New `--rocm-extras` flag in `build_prod_wheels.py`

**Net changes:** +364 lines, -31 lines across 10 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — Well-structured feature with good backward compatibility design (all new inputs default to empty/false). Tests are solid. A few issues need attention, mainly around inline bash complexity and a duplicated code block.

**Strengths:**

- Clean auto-detection logic — flat vs per-family is determined by presence of subdirectories, no new flags needed
- Good backward compatibility — legacy callers (`ci_linux.yml`, `ci_windows.yml`, `multi_arch_ci_windows.yml`) are unaffected since new inputs all have safe defaults
- Comprehensive test coverage for both `generate_flat_index()` and the three-way `write_gha_upload_summary()` branching
- The `device-gfx{N}` extras approach is a practical fix for the offload-arch bootstrapping problem

**Issues:**

- ⚠️ Duplicated "Compute ROCm device extras" bash blocks
- ⚠️ Inline bash with string manipulation in workflows
- 💡 Minor code quality items

---

## Detailed Review

### 1. Workflows: Duplicated "Compute ROCm device extras" Step

**⚠️ IMPORTANT: Duplicated inline bash block**

The "Compute ROCm device extras" step is copy-pasted identically in both `test_rocm_wheels.yml` and `build_portable_linux_pytorch_wheels_ci.yml`:

```yaml
- name: Compute ROCm device extras
  id: device_extras
  run: |
    if [ "${{ inputs.kpack_split }}" = "true" ] && [ -n "${{ inputs.amdgpu_targets }}" ]; then
      extras=$(echo "${{ inputs.amdgpu_targets }}" | sed 's/\(^\|,\)/\1device-/g')
      echo "value=${extras}" >> "$GITHUB_OUTPUT"
    else
      echo "value=" >> "$GITHUB_OUTPUT"
    fi
```

This has conditionals and `sed` string manipulation — per the [GitHub Actions style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/github_actions_style_guide.md#prefer-python-scripts-over-inline-bash), this logic belongs in a Python script, especially since it's duplicated.

**Recommendation:** Extract to a small Python helper (or add to an existing script). Something like:

```python
def compute_device_extras(targets: str) -> str:
    """Convert 'gfx942,gfx1201' to 'device-gfx942,device-gfx1201'."""
    if not targets:
        return ""
    return ",".join(f"device-{t}" for t in targets.split(","))
```

This also makes the logic unit-testable.

### 2. Workflows: Package String Construction in test_rocm_wheels.yml

**⚠️ IMPORTANT: Inline bash string manipulation**

The `test_rocm_wheels.yml` "Install rocm[libraries]" and "Install rocm[libraries,devel]" steps do bash parameter expansion to append device extras:

```yaml
pkg="rocm[libraries]"
if [ -n "${{ steps.device_extras.outputs.value }}" ]; then
  pkg="${pkg%]},${{ steps.device_extras.outputs.value }}]"
fi
```

The `${pkg%]}` trick (strip trailing `]` then re-add with extras) is clever but fragile — easy to misread or break. This is another case where a Python helper would be clearer:

```python
def build_pip_package_spec(base_extras: list[str], device_extras: str, version: str) -> str:
    ...
```

**Recommendation:** Consider moving the pip install logic into a Python script or at least documenting the parameter expansion pattern with a comment explaining what `${pkg%]}` does.

### 3. upload_python_packages.py: Clean Three-Way Branch

**✅ Good: Well-structured auto-detection**

The `generate_index()` change cleanly auto-detects flat vs per-family layout:

```python
has_subdirs = any(d.is_dir() for d in dist_dir.iterdir())
if has_subdirs:
    generate_multiarch_indexes(dist_dir)
else:
    generate_flat_index(dist_dir)
```

The `run()` function similarly uses `family_subdirs` presence to determine `kpack_split` output. The three-way `families` semantics (`None`/`[]`/`[...]`) is well-documented in the docstring.

One observation: the import at the top was updated to import `generate_flat_index` — good.

### 4. upload_python_packages.py: Output Summary

**✅ Good: Three-way summary with clear install instructions**

The kpack-split summary includes helpful per-target install syntax:

```
pip install rocm[libraries,devel,device-<YOUR_TARGET>] --pre \
    --find-links=...
```

### 5. generate_local_index.py: generate_flat_index()

**✅ Good: Simple, focused implementation**

The function correctly scans only top-level files (`f.is_file()` check excludes dirs) and delegates to the existing `generate_simple_index()`. Tests cover: top-level files, subdir exclusion, custom patterns, and empty dist.

### 6. setup.py: Per-Target Device Extras

**✅ Good: Practical solution to bootstrapping problem**

```python
device_entry = dist_info.ALL_PACKAGES.get("device")
if device_entry and device_entry.is_target_specific:
    EXTRAS_REQUIRE.pop("device", None)
    for _target in dist_info.AVAILABLE_TARGET_FAMILIES:
        EXTRAS_REQUIRE[f"device-{_target}"] = [
            device_entry.get_dist_package_require(target_family=_target)
        ]
```

This replaces the generic `device` extra (which needs `offload-arch` at sdist build time) with explicit `device-gfx{N}` entries. The comment explains the motivation well.

**💡 SUGGESTION: Consider keeping `device` extra as an alias**

When `offload-arch` *is* available (runtime installs, not CI builds), having `device` resolve automatically is convenient. Could keep it as a fallback:

```python
# Keep 'device' if offload-arch is available, otherwise remove it
try:
    target = dist_info.determine_target_family()
    # offload-arch worked, keep the generic 'device' extra
except ...:
    EXTRAS_REQUIRE.pop("device", None)
```

This may be out of scope for this PR though — the current approach is fine for CI.

### 7. build_prod_wheels.py: --rocm-extras Flag

**✅ Good: Clean extension**

```python
extras = "libraries,devel"
if args.rocm_extras:
    extras += f",{args.rocm_extras}"
pip_args.extend([f"rocm[{extras}]{rocm_sdk_version}"])
```

Simple, additive, backward-compatible.

### 8. build_prod_wheels.py: Unrelated Formatting Change

**💡 SUGGESTION: Unrelated textwrap.dedent reformatting**

The `get_rocm_init_contents()` function had its `textwrap.dedent()` call reformatted (removing line breaks around the f-string). This is a style-only change unrelated to the PR's purpose. Not a problem, but worth noting — it could cause merge conflicts with other in-flight PRs touching this function.

### 9. multi_arch_ci_linux.yml: URL Construction

**✅ Good: Conditional URL construction**

The ternary expression for `package_find_links_url` is clear:

```yaml
package_find_links_url: >-
  ${{
    needs.build_python_packages.outputs.kpack_split == 'true'
    && needs.build_python_packages.outputs.package_find_links_url
    || format('{0}/{1}/index.html',
        needs.build_python_packages.outputs.package_find_links_url,
        matrix.family_info.amdgpu_family)
  }}
```

For kpack-split, the URL already includes `/index.html` (set by `upload_python_packages.py`), so it's passed as-is. For legacy, the family path and `/index.html` are appended. This is consistent with the Python-side logic.

### 10. Test Coverage

**✅ Good: Thorough tests**

- `TestGenerateFlatIndex`: 4 tests covering top-level files, subdir exclusion, custom patterns, empty dist
- `TestGenerateIndex`: 4 tests covering flat vs per-family auto-detection and dry-run
- `TestWriteGhaUploadSummary`: 3 tests covering the three-way families branching (None, [], [...])

The tests use real temp directories (not mocks) for file operations — good.

### 11. Caller Impact Analysis

| Caller | Workflow | Updated? | Impact |
|--------|----------|----------|--------|
| `multi_arch_ci_linux.yml` | `test_rocm_wheels.yml` | ✅ Yes | Passes `amdgpu_targets`, `kpack_split` |
| `multi_arch_ci_linux.yml` | `build_portable_linux_pytorch_wheels_ci.yml` | ✅ Yes | Passes `amdgpu_targets`, `kpack_split` |
| `multi_arch_ci_linux.yml` | `build_portable_linux_python_packages.yml` | ✅ Yes | Passes `--expand-family-to-targets` |
| `ci_linux.yml` | `test_rocm_wheels.yml` | Not needed | Single-arch, defaults safe |
| `ci_linux.yml` | `build_portable_linux_pytorch_wheels_ci.yml` | Not needed | Single-arch, defaults safe |
| `ci_windows.yml` | `test_rocm_wheels.yml` | Not needed | Single-arch, defaults safe |
| `multi_arch_ci_windows.yml` | `test_rocm_wheels.yml` | Not needed | Legacy per-family, defaults safe |

All callers are correctly handled.

---

## Recommendations

### ✅ Recommended:

1. Extract the "Compute ROCm device extras" logic from both workflows into a shared Python helper to eliminate duplication and make it testable
2. Add a comment explaining the `${pkg%]}` bash parameter expansion trick, or move the pip package spec construction into a Python helper

### 💡 Consider:

1. Keep the generic `device` extra as a fallback when `offload-arch` is available (may be future work)
2. Split out the unrelated `textwrap.dedent` formatting change to avoid merge conflicts

### 📋 Future Follow-up:

1. The PR description notes sanity checks still fail with kpack-split — track and fix separately
2. Windows multi-arch CI (`multi_arch_ci_windows.yml`) doesn't pass `kpack_split`/`amdgpu_targets` to `test_rocm_wheels` — presumably kpack-split on Windows is a future effort

---

## Testing Recommendations

1. Verify the linked CI run (https://github.com/ROCm/TheRock/actions/runs/24402771972) — the PR notes ROCm packages install successfully but sanity checks fail
2. Confirm legacy (non-kpack-split) CI on this PR branch passes without regression
3. Verify the `sed` in "Compute ROCm device extras" handles edge cases: single target (`gfx942`), multiple targets (`gfx942,gfx1201`), empty string

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The design is sound and backward compatibility is well-handled. The main concerns are the duplicated inline bash blocks (which should be a Python script per the style guide) and the somewhat fragile bash string manipulation for pip package specs. These are style-guide-level issues rather than correctness bugs — the logic itself works. Tests are solid. After addressing the duplication, this should be ready to merge.
