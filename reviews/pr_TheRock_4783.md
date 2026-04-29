# PR Review: Build fat PyTorch wheel and kpack-split in multi-arch CI

* **PR:** [#4783](https://github.com/ROCm/TheRock/pull/4783)
* **Author:** marbre (Marius Brehler)
* **Base:** `main` ← `users/marbre/pytorch-fat-wheel-kpack-split`
* **Reviewed:** 2026-04-23
* **Status:** OPEN

---

## Summary

This PR replaces the per-family PyTorch build matrix in multi-arch CI with a
single fat wheel build that covers all gfx targets, followed by a kpack split
into host + per-target device wheels. Key changes:

1. **Workflow consolidation:** `multi_arch_ci_{linux,windows}.yml` no longer
   fan out per-family PyTorch jobs. One job builds a fat wheel for all
   targets, then splits it via `rocm-kpack`.
2. **Input rename:** `amdgpu_targets` → `amdgpu_families` in the PyTorch wheel
   workflows. A new `expand_amdgpu_families.py` script resolves families to
   gfx targets using the CMake source of truth.
3. **Shared library extraction:** `amdgpu_family_map()` and `expand_families()`
   are moved into `_therock_utils.cmake_amdgpu_targets`, replacing the
   duplicate cache in `artifact_manager.py`.
4. **S3 upload:** Both wheel workflows gain upload steps
   (`upload_python_packages.py --multiarch`) and AWS credential configuration.
5. **build_prod_wheels.py:** `--pytorch-rocm-arch` now accepts multi-target
   comma-separated lists, reads `PYTORCH_ROCM_ARCH` env var as a fallback, and
   converts commas to semicolons for CMake consumption.

**Net changes:** +480 lines, -109 lines across 10 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The core approach is sound and well-structured, but
there are unconditional upload steps that change behavior for single-arch
callers, and the mock targets in existing tests need verification.

**Strengths:**

- Eliminates redundant per-family builds — one fat build + split is more
  efficient and consistent with the kpack model
- Clean extraction of `expand_families()` into shared library code with good
  test coverage
- Thorough TODO references (e.g., `#4687`) documenting the migration path
- Well-commented workflow steps explaining the kpack split flow
- Correct comma→semicolon conversion for CMake consumption of `PYTORCH_ROCM_ARCH`

**Issues:**

- Upload and AWS credential steps are unconditional in the reusable workflow,
  affecting single-arch callers that currently don't upload
- Windows kpack split has complex inline bash (setup/shim logic)

---

## Detailed Review

### 1. Reusable Workflow Changes — Caller Impact

#### ⚠️ IMPORTANT: Unconditional upload steps affect single-arch callers

The PR adds "Configure AWS Credentials" and "Upload PyTorch wheels" steps at
the end of both `build_portable_linux_pytorch_wheels_ci.yml` and
`build_windows_pytorch_wheels_ci.yml` **without conditional guards**.

These workflows are called by:
- `ci_linux.yml` / `ci_windows.yml` (single-arch) — currently does NOT upload
- `multi_arch_ci_linux.yml` / `multi_arch_ci_windows.yml` — the intended consumer

For single-arch callers, `release_type` defaults to `""`, which resolves to the
`therock-ci` IAM role. The upload step will proceed with `--multiarch`, which
is semantically wrong for single-arch builds (it omits `artifact_group` from
the upload path).

**Recommendation:** Add `if:` guards to the AWS config and upload steps, e.g.:
```yaml
if: ${{ inputs.kpack_split == 'true' }}
```
Or alternatively:
```yaml
if: ${{ inputs.amdgpu_families != '' }}
```
This restricts uploads to multi-arch callers that actually plumb the new inputs
through.

### 2. expand_amdgpu_families.py — New Helper Script

#### ✅ Well-structured expansion logic

The new script correctly:
- Parses semicolon-separated families
- Expands via the shared `amdgpu_family_map()` / `expand_families()` API
- Fails hard on unknown families (strict mode by default)
- Outputs comma-separated targets for workflow consumption

The data flow is clean:
1. Workflow input: `"gfx94X-dcgpu;gfx120X-all"`
2. Script output: `"gfx942,gfx1200,gfx1201"`
3. `--pytorch-rocm-arch gfx942,gfx1200,gfx1201`
4. `build_prod_wheels.py` converts commas to semicolons for CMake

#### 💡 SUGGESTION: Empty families prints empty line

In `main()`, when families list is empty after filtering, the script prints an
empty string and returns 0. The workflow has `if: ${{ inputs.amdgpu_families != '' }}`
guarding the expand step, so this path shouldn't be hit in practice. However,
printing nothing (no `print()` call) would be slightly cleaner than printing
an empty line. Minor nit.

### 3. _therock_utils/cmake_amdgpu_targets.py — Shared Library

#### ✅ Good extraction of shared code

Moving `amdgpu_family_map()` and `expand_families()` out of
`artifact_manager.py` into the shared `_therock_utils` module eliminates
code duplication. The per-path caching in `_family_to_targets_cache` is
a nice touch for repeated calls.

The `strict` parameter on `expand_families()` is well-designed:
- `strict=True` (default) for the CI script — fail-fast on typos
- `strict=False` for `artifact_manager.py` — preserves existing lenient behavior

### 4. artifact_manager.py — Import/Usage Updates

#### ✅ Clean migration

The `_get_family_to_targets()` helper is correctly removed and replaced with
calls to the shared `amdgpu_family_map()`. The `parse_target_families()`
function now delegates to `expand_families()` for the dedup logic.

### 5. artifact_manager_tool_test.py — Mock Targets

#### ⚠️ IMPORTANT: Verify mock.patch.object targets are correct

The test patches change from:
```python
mock.patch.object(self.am, "_get_family_to_targets", return_value=fake_map)
```
to:
```python
mock.patch.object(self.am, "amdgpu_family_map", return_value=fake_map)
```

Since `artifact_manager.py` uses `from _therock_utils.cmake_amdgpu_targets
import amdgpu_family_map`, patching `self.am.amdgpu_family_map` replaces the
module-level binding, which is correct.

However, `parse_target_families()` now calls `expand_families()` (also
imported at module level). The test does NOT mock `expand_families` — it uses
the real implementation with the mocked family map. This should work correctly
since `expand_families()` is a pure function, but it's worth verifying the
tests still pass. If `expand_families()` were to call `amdgpu_family_map()`
internally (it doesn't — it takes the map as a parameter), the mock chain
would break.

**Recommendation:** Run the existing test suite to confirm:
```bash
python -m pytest build_tools/tests/artifact_manager_tool_test.py -k "family"
```

### 6. build_prod_wheels.py — Multi-arch Support

#### ✅ Correct priority chain for PYTORCH_ROCM_ARCH

The new priority is: `--pytorch-rocm-arch` > `PYTORCH_ROCM_ARCH` env > `rocm-sdk targets`.
The env var fallback is a reasonable addition that aligns with PyTorch's
own convention. The TODO(#4687) documenting why `rocm-sdk targets` is
problematic is helpful context.

#### ✅ Correct comma-to-semicolon conversion

```python
pytorch_rocm_arch = pytorch_rocm_arch.replace(",", ";")
```

CMake list format uses semicolons. This is the right transformation.

#### 💡 SUGGESTION: `--rocm-extras` is now orphaned in multi-arch CI

The old workflow computed `device-gfx*` extras from `amdgpu_targets` and
passed them via `--rocm-extras`. The new flow drops `--rocm-extras` because
kpack-split ROCm packages resolve device dependencies automatically from the
flat index. This is correct for the kpack-split flow.

The `--rocm-extras` argument definition and `do_install_rocm()` usage remain
in `build_prod_wheels.py` (lines 424-425, 1261), which is fine — they're
still used by release workflows and manual invocations. Just noting this is
intentional, not an oversight.

### 7. Workflow Steps — Kpack Split

#### ✅ Linux kpack split is clean and well-commented

The Linux steps correctly:
- Init rocm-systems submodule (depth=1 for speed)
- Install kpack from source (no published wheel yet)
- Relocate fat wheel to temp dir before splitting
- Use `rocm_sdk version` for device wheel requires-dist
- Clean up temp dir after split

#### 💡 SUGGESTION: Windows kpack split has notable complexity

The Windows `Split PyTorch fat wheel` step (~35 lines of bash) includes:
- `cygpath` conversions
- LLVM binary discovery from `rocm-sdk path --root`
- Shim creation (`objcopy.exe`, `readelf.exe` → unprefixed names)
- PATH manipulation

While each piece is necessary, this approaches the complexity threshold where
a Python helper script would be more maintainable and testable. The existing
TODO referencing `tasks/active/kpack-binutils-llvm-fallback.md` suggests the
shim logic is temporary. If the shim logic persists beyond the upstream fix,
consider extracting it.

### 8. multi_arch_ci_{linux,windows}.yml — Caller Changes

#### ✅ Correct consolidation from matrix to single job

The rename from `build_pytorch_wheels_per_family` (matrix) to
`build_pytorch_wheel_fat` (single) is clean. The key input changes:
- `artifact_group`: from per-family to `dist_amdgpu_families` → wait, it
  uses `fromJSON(inputs.build_config).artifact_group` now, not per-family
- `amdgpu_families`: new, from `dist_amdgpu_families` in build_config
- `kpack_split`: hardcoded `"true"` (was dynamic from python packages output)
- `rocm_package_find_links_url`: simplified to flat URL (no per-family subdir logic)
- `release_type`: new, forwarded from inputs

All correct. The `dist_amdgpu_families` field is set by `configure_multi_arch_ci.py`
and contains the semicolon-separated family list.

### 9. Tests

#### ✅ Good unit test coverage for expand_families()

`expand_amdgpu_families_test.py` covers:
- Single family expansion
- Multiple families with order preservation
- Deduplication across overlapping families
- Empty input
- Unknown family in strict mode (raises)
- Unknown family in non-strict mode (skips)
- End-to-end main() against real CMake file

The test structure using a `_SAMPLE_MAP` fixture (not the real CMake data) is
the right approach for the unit tests, while the `ExpandAmdgpuFamiliesMainTest`
class uses the real CMake file for integration coverage.

---

## Recommendations

### ⚠️ IMPORTANT:

1. **Guard upload steps for single-arch callers.** Add `if:` conditions to
   "Configure AWS Credentials" and "Upload PyTorch wheels" steps in both
   `build_portable_linux_pytorch_wheels_ci.yml` and
   `build_windows_pytorch_wheels_ci.yml` to prevent unintended uploads from
   single-arch CI (`ci_linux.yml`, `ci_windows.yml`).

2. **Verify mock targets pass.** Run the `artifact_manager_tool_test.py`
   family-related tests to confirm the patched targets (`amdgpu_family_map`)
   work correctly with the new `expand_families` call chain.

### 💡 Consider:

1. **Extract Windows shim logic** into a Python helper if the kpack-binutils
   upstream fix takes time.
2. **Empty-input print behavior** in `expand_amdgpu_families.py` — `return 0`
   without `print("")` would be slightly cleaner.

### 📋 Future Follow-up:

1. **TODO(#4687):** Remove `get_rocm_sdk_targets()` fallback once all callers
   pass `--pytorch-rocm-arch` explicitly.
2. **Kpack binutils shim:** Drop Windows objcopy/readelf shims once rocm-kpack
   adds `llvm-*` fallbacks.
3. **Single-arch uploads:** When single-arch CI needs pytorch uploads (per
   TODO #3291), add proper upload support without `--multiarch`.

---

## Testing Recommendations

- [ ] Multi-arch CI run with kpack_split=true — verify fat wheel builds, splits
  correctly, and uploads to S3 with proper path structure
- [ ] Single-arch CI run (ci_linux.yml) — verify the new upload/AWS steps don't
  run (once guarded) or at minimum don't cause failures
- [ ] `python -m pytest build_tools/github_actions/tests/expand_amdgpu_families_test.py`
- [ ] `python -m pytest build_tools/tests/artifact_manager_tool_test.py -k "family"`
- [ ] Windows multi-arch CI — verify kpack shim creation and split work on
  Windows runners

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The core architectural change (fat wheel + kpack split replacing per-family
matrix) is well-designed and the shared library extraction is clean. The main
concern is the unconditional upload steps in the reusable workflows that change
behavior for existing single-arch callers. Adding `if:` guards to those steps
would make this ready to merge.
