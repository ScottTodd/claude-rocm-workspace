# Branch Review: users/scotttodd/pytorch-ci-windows-1

* **Branch:** `users/scotttodd/pytorch-ci-windows-1`
* **Base:** `main`
* **Reviewed:** 2026-02-16
* **Commits:** 1 commit

---

## Summary

Adds a Windows CI workflow for building PyTorch wheels (`build_windows_pytorch_wheels_ci.yml`) and wires it into the CI pipeline through `ci_windows.yml`, `ci.yml`, and `ci_nightly.yml`. This is the Windows counterpart of the existing Linux CI pytorch build workflow, completing Phase 3 of the pytorch-ci task (#3291).

**Net changes:** +176 lines, -1 line across 4 files

---

## Overall Assessment

**✅ APPROVED** - Clean, well-structured change that follows established patterns exactly.

**Strengths:**

- New workflow closely mirrors the Linux CI workflow structure while correctly adapting Windows-specific plumbing (cmd shell, MSVC, `B:/src` checkout, `--enable-pytorch-flash-attention-windows`)
- Job in `ci_windows.yml` is structurally identical to its Linux counterpart in `ci_linux.yml`
- All callers of `ci_windows.yml` (ci.yml, ci_nightly.yml) updated to pass `build_pytorch`
- `configure_ci.py` already computes `build_pytorch` for Windows variants — no script changes needed
- Actions pinned to commit SHAs with version comments
- Permissions are minimal (`contents: read`)
- Good header comments explaining the CI vs release workflow differences

**Blocking Issues:** None

---

## Detailed Review

### 1. `build_windows_pytorch_wheels_ci.yml` (new)

**Structure:** Follows the Linux CI workflow pattern faithfully. Steps are taken from the release workflow (`build_windows_pytorch_wheels.yml`) with appropriate CI adaptations.

**Correctness checks:**
- `runs-on` uses the correct conditional pattern matching the release workflow
- `CHECKOUT_ROOT: B:/src` and `PACKAGE_DIST_DIR` with backslashes match the release workflow
- `shell: cmd` on the build step with the load-bearing comment about issue #827 — correct
- `--find-links` instead of `--index-url` — correct CI adaptation
- `--pytorch-dir` passed explicitly (release workflow does this too for Windows)
- No `--pytorch-audio-dir` / `--pytorch-vision-dir` — correct, torch-only for CI
- `awscli` choco install omitted since no S3 upload — correct

### 💡 SUGGESTION: `workflow_dispatch` default `artifact_group`

The `workflow_dispatch` default is `gfx110X-all`. The Linux CI workflow defaults to `gfx94X-dcgpu`. The Windows default makes sense (gfx110X is more commonly tested on Windows), just noting the intentional difference.

### 2. `ci_windows.yml` changes

The new `build_windows_pytorch_wheels_ci` job is structurally identical to the Linux equivalent in `ci_linux.yml`:
- Same `needs: [build_windows_python_packages]` dependency
- Same `if:` condition pattern (failure/cancelled/prebuilt/build_pytorch)
- Same hardcoded `python_version: "3.12"` and `pytorch_git_ref: "release/2.10"`
- Same input passthrough pattern

New `build_pytorch` input with `default: false` — safe default, matches Linux.

### 3. `ci.yml` and `ci_nightly.yml` changes

Both add the same one-liner:
```yaml
build_pytorch: ${{ matrix.variant.build_pytorch == true }}
```

This matches exactly how the Linux job passes it (ci.yml line 105, ci_nightly.yml line 88).

**Caller inventory:**
- `ci.yml` — updated ✅
- `ci_nightly.yml` — updated ✅
- `multi_arch_ci.yml` — commented out, not active ✅

### 4. Security

- No user-controlled input in `run` blocks beyond workflow inputs (which are controlled by the calling workflow or manual dispatch by repo members)
- `rocm_package_find_links_url` is interpolated in the cmd build step — this is a URL from the python packages upload step, not user-supplied free text. Same pattern as the Linux workflow.
- No secrets exposed
- Permissions are read-only at workflow level

---

## Recommendations

### ❌ REQUIRED Before Human Review (Blocking):

None.

### ✅ Recommended Before Human Review:

None.

### 💡 Consider:

1. The `workflow_dispatch` default `artifact_group` is `gfx110X-all` (vs `gfx94X-dcgpu` on Linux). This is reasonable for Windows but could be noted in the PR description for context.

### 📋 Future Follow-up:

1. Add S3 upload step (noted in TODO comments)
2. Add `test_pytorch_wheels` job (noted in TODO comment)
3. Phase 2: label-based opt-in (`build:pytorch` PR label)

---

## Testing Recommendations

- **workflow_call path:** Push branch and trigger CI on a variant with `build_pytorch: true` (e.g., gfx110X-all or gfx120X-all on Windows). Verify the pytorch build job appears and runs.
- **workflow_dispatch path:** Manually trigger `build_windows_pytorch_wheels_ci.yml` with a known-good `rocm_package_find_links_url` from a recent CI run.
- **Negative test:** Verify that variants with `expect_pytorch_failure: true` (e.g., gfx90X/windows per issue #1927) do NOT trigger the pytorch build job.

---

## Conclusion

**Approval Status: ✅ APPROVED**

The change is clean, follows established patterns, and all callers are updated. Ready for human review and CI testing.
