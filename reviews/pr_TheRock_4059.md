# PR Review: Extend Python packages and PyTorch wheels to multi-arch Windows CI

* **PR:** [#4059](https://github.com/ROCm/TheRock/pull/4059)
* **Author:** marbre (Marius Brehler)
* **Branch:** `users/marbre/multi-arch-ci-windows` → `main`
* **Reviewed:** 2026-03-19
* **Status:** OPEN

---

## Summary

Brings multi-arch Windows CI to parity with the Linux multi-arch CI by adding Python package and per-family PyTorch wheel build jobs to `multi_arch_ci_windows.yml`, and extending `build_windows_python_packages.yml` to support multi-arch fetching and indexing.

**Net changes:** +79 lines, -6 lines across 2 files

**Files changed:**
| File | Changes | Description |
|------|---------|-------------|
| `.github/workflows/build_windows_python_packages.yml` | +38/-6 | Add `amdgpu_families`/`multiarch_index` inputs; multi-arch fetch path |
| `.github/workflows/multi_arch_ci_windows.yml` | +41/-0 | Add `build_pytorch` input; add python packages + pytorch wheel jobs |

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — Good structural approach that mirrors the Linux multi-arch CI pattern. A few issues need attention before merge.

**Strengths:**
- Clean parity with `multi_arch_ci_linux.yml` — same job structure, same per-family URL slicing
- Proper use of `artifact_manager.py fetch` for multi-arch and backward-compatible `fetch_artifacts.py` for single-family
- `--multiarch` flag on upload correctly wired
- Minimal permissions (`contents: read`, `id-token: write`) at job level

**Issues:**
- Caller not updated to pass `build_pytorch`
- `build_pytorch == false` condition is inverted (matches Linux bug)
- Inline bash conditional in fetch step

---

## Detailed Review

### 1. `multi_arch_ci_windows.yml` — Caller not passing `build_pytorch`

**❌ BLOCKING: `multi_arch_ci.yml` caller not updated to pass `build_pytorch`**

The PR adds `build_pytorch` as an input to `multi_arch_ci_windows.yml` (default: `false`), but the caller in `multi_arch_ci.yml` (line 113-127) does not pass it. Compare with the Linux call at line 96:

```yaml
# Linux call passes build_pytorch:
build_pytorch: ${{ matrix.variant.build_pytorch == true }}

# Windows call (lines 113-127) does NOT pass build_pytorch
```

This means `build_pytorch` will always be `false` (the default), so the pytorch job's `if` condition will always evaluate to `true` — pytorch wheels will build unconditionally regardless of what `configure_ci.py` decides for the variant.

**Required action:** Update `multi_arch_ci.yml` to pass `build_pytorch` to the Windows workflow, matching the Linux pattern.

---

### 2. `multi_arch_ci_windows.yml` — Inverted `build_pytorch` condition

**⚠️ IMPORTANT: `build_pytorch == false` condition appears inverted**

```yaml
# Line in PR:
if: ${{ !failure() && !cancelled() && inputs.build_pytorch == false }}
```

This runs the pytorch job when `build_pytorch` is `false` and skips it when `true` — the opposite of what the name suggests. The same pattern exists in `multi_arch_ci_linux.yml:183`.

The caller passes `build_pytorch: ${{ matrix.variant.build_pytorch == true }}`, where `build_pytorch == true` means "this variant should build pytorch" (from `configure_ci.py`). So the condition inverts the intent.

Currently this is masked because the caller doesn't pass the input (see blocking issue above), so it's always `false` (always builds). But once the caller is wired up, this inversion will cause pytorch to be skipped for variants that should build it.

**Recommendation:** Fix both Linux and Windows to use `inputs.build_pytorch == true` (or just `inputs.build_pytorch`). If this is intentional for some reason I'm not seeing, add a comment explaining the inversion.

---

### 3. `build_windows_python_packages.yml` — Inline bash conditional

**⚠️ IMPORTANT: Fetch step uses if/else conditional in bash**

The modified "Fetch artifacts" step has an `if/else` branch selecting between `artifact_manager.py` and `fetch_artifacts.py`. Per the [GitHub Actions style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/github_actions_style_guide.md#prefer-python-scripts-over-inline-bash), conditionals in `run:` blocks should be Python scripts.

That said, this is a simple two-branch conditional with one command per branch, not a complex decision tree. And it parallels how other workflows handle the single-arch vs multi-arch split.

**Recommendation:** Either:
- Accept as-is given the simplicity, or
- Split into two separate steps with `if:` conditions at the step level:
  ```yaml
  - name: Fetch artifacts (multi-arch)
    if: ${{ inputs.amdgpu_families != '' }}
    run: python ./build_tools/artifact_manager.py fetch ...

  - name: Fetch artifacts (single-family)
    if: ${{ inputs.amdgpu_families == '' }}
    run: python ./build_tools/fetch_artifacts.py ...
  ```
  This avoids bash conditionals entirely and is more idiomatic for GitHub Actions.

---

### 4. `build_windows_python_packages.yml` — Comment placement in run block

**💡 SUGGESTION: Move explanatory comment above the command**

```yaml
python ./build_tools/artifact_manager.py fetch \
  ...
  --output-dir="${{ github.workspace }}"
  # NOTE: artifact_manager.py appends /artifacts to --output-dir
  # in non-flatten mode, so pass workspace root here so that
  # artifacts land in ARTIFACTS_DIR ($workspace/artifacts).
```

The comment after the command is valid bash (no-op), but it's easy to misread as a continuation of the command arguments. Moving it before the `python` invocation or into a `# Explanation:` block before the `run:` would be clearer.

---

### 5. `multi_arch_ci_windows.yml` — `expect_failure` guard on python packages

**💡 SUGGESTION: Consider `expect_failure` semantics for python packages job**

```yaml
build_python_packages:
  if: ${{ !failure() && !cancelled() && inputs.expect_failure == false }}
```

This skips python packages when the build is expected to fail, which is reasonable. Note that `build_pytorch_wheels_per_family` depends on `build_python_packages` via `needs:`, so pytorch is implicitly also skipped when `expect_failure` is true. This is correct behavior.

---

### 6. `multi_arch_ci_windows.yml` — `amdgpu_targets` addition

**💡 SUGGESTION: Confirm `multi_arch_build_windows.yml` accepts `amdgpu_targets`**

The PR adds `amdgpu_targets: ${{ matrix.family_info.amdgpu_targets }}` to the build job. This looks correct for passing per-family target lists, but verify that the called workflow (`multi_arch_build_windows.yml`) declares this input.

---

### 7. `multi_arch_ci_windows.yml` — Hardcoded pytorch parameters

**📋 FUTURE WORK: Parameterize pytorch version and git ref**

```yaml
python_version: "3.12"
pytorch_git_ref: "release/2.10"
```

These are hardcoded, matching the current Linux multi-arch CI. Eventually these should be inputs or derived from a configuration source to avoid drift between Linux and Windows.

---

### 8. PR description

**⚠️ IMPORTANT: Empty PR body**

The PR body is empty. For workflow changes, it's helpful to include:
- What this enables (multi-arch Windows python/pytorch builds)
- Link to the Linux equivalent for context
- Testing evidence (link to a successful CI run)

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Update `multi_arch_ci.yml` to pass `build_pytorch` to the Windows workflow call (matching the Linux call pattern)

### ✅ Recommended:

1. Fix the `build_pytorch == false` condition to `build_pytorch == true` (affects Linux too — may want a separate PR)
2. Split the fetch step into two conditional steps instead of inline bash if/else
3. Add PR description with context and test links

### 💡 Consider:

1. Move the `--output-dir` comment before the command
2. Verify `amdgpu_targets` is accepted by `multi_arch_build_windows.yml`

### 📋 Future Follow-up:

1. Parameterize pytorch version/ref instead of hardcoding
2. Add `gfx950-dcgpu` exclude list (Linux has it, Windows may need it too once those runners exist)

---

## Testing Recommendations

- Run multi-arch Windows CI end-to-end with a variant that has `build_pytorch: true` to verify the full chain
- Verify `artifact_manager.py fetch` correctly places artifacts in `$ARTIFACTS_DIR` when `--output-dir` is the workspace root
- Confirm `upload_python_packages.py --multiarch` generates per-family indexes correctly on Windows

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The structural approach is sound and correctly mirrors the Linux multi-arch CI pattern. The blocking issue is the missing `build_pytorch` pass-through from the caller in `multi_arch_ci.yml`. The inverted `build_pytorch == false` condition is a pre-existing issue from the Linux workflow that should also be addressed (either here or in a follow-up).
