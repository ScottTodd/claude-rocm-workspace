# PR Review: Add multi-arch PyTorch release workflows

* **PR:** [#4875](https://github.com/ROCm/TheRock/pull/4875)
* **Author:** marbre (Marius Brehler)
* **Reviewed:** 2026-04-27
* **Base:** `main`
* **Branch:** `users/marbre/multi-arch-pytorch-release-workflow`

---

## Summary

This PR adds new workflows to build and publish PyTorch wheels as part of the
multi-arch release pipeline. Two new workflow files are added (Linux + Windows),
each dispatched from the existing `multi_arch_release_{linux,windows}.yml`
parent workflows via `benc-uk/workflow-dispatch`. A new Python script
(`publish_pytorch_to_staging.py`) handles uploading the split wheels to S3
staging, with unit tests.

**Net changes:** +800 lines, -2 lines across 6 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** - Code is well-structured and follows established
patterns, but test evidence is missing and there are a few items to address.

**Strengths:**

- Clean separation: new workflows dispatched as independent runs, avoiding
  bloating the parent workflow graph
- Well-documented workflow headers explaining the build shape and trigger model
- `publish_pytorch_to_staging.py` is focused, testable, and has good test
  coverage (bucket routing, error cases, argument validation)
- All dependencies verified: `boto3` is provided by `requirements-ci.txt`,
  `_therock_utils` modules are in-tree, container image is pinned by SHA
- Actions pinned by SHA, runners pinned to specific versions, minimal
  permissions (`id-token: write`, `contents: read`)
- Proper staging path (`v4/whl-staging/`) for the release flow — stage → test →
  promote

**Issues:**

- No test evidence linked (test plan/result are "tbd")
- Inline bash with conditionals in several steps (pre-existing pattern from CI
  workflows but new code)

---

## Detailed Review

### 1. Parent Workflow Dispatch Jobs (`multi_arch_release_{linux,windows}.yml`)

The dispatch wiring looks correct:

- `needs: [build_artifacts, build_python_packages]` ensures ROCm packages exist
  before pytorch builds start
- Input mapping is accurate: `rocm_version` ← `rocm_package_version`,
  `rocm_package_find_links_url` ← `needs.build_python_packages.outputs.package_find_links_url`,
  `release_type` forwarded directly
- `cache_type` intentionally not passed (defaults to `none` for release)
- `ref` handling is correct: `benc-uk/workflow-dispatch` `ref` sets the branch
  the dispatched workflow runs on; the inner checkout defaults to `github.ref`
  when `inputs.ref` is empty

### 💡 SUGGESTION: Job name inconsistency

The Linux parent uses `name: Build PyTorch Wheel` (singular) while the Windows
parent uses `name: Build PyTorch Wheels` (plural). Minor, but worth aligning.

---

### 2. Linux PyTorch Wheels Workflow (`multi_arch_release_linux_pytorch_wheels.yml`)

**Matrix:** 5 Python versions × 5 PyTorch refs (minus py3.14/torch-2.8
exclusion) = 24 jobs. The exclusion comment ("Python 3.14 support was added in
PyTorch 2.9") is helpful.

**Build flow:** Checkout → select Python → install deps → checkout PyTorch →
determine version → (optional sccache) → expand families → build → sanity check
→ kpack split → upload. This matches the existing CI workflow
(`build_portable_linux_pytorch_wheels_ci.yml`) step-for-step.

**kpack split:** Correctly moves the fat wheel out of `PACKAGE_DIST_DIR` before
splitting, handles the filename collision cleanly.

**Upload:** Uses the new `publish_pytorch_to_staging.py` to push to
`s3://therock-{release_type}-python/v4/whl-staging/`. AWS credentials are
configured via `.github/actions/configure_aws_artifacts_credentials` (which
already handles the `release_type` → IAM role mapping).

### ⚠️ IMPORTANT: Inline bash with conditionals

Several `run:` blocks contain `if/elif/else` logic:

1. **"Build PyTorch wheels"** (line ~207-223): cache flag selection
2. **"Report cache stats"** (line ~226-236): conditional sccache/ccache reporting

Per the [GitHub Actions style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/github_actions_style_guide.md#prefer-python-scripts-over-inline-bash),
conditionals belong in Python scripts. These are copied from the existing CI
workflows, and the PR description notes convergence is planned. Since this is
new code being added (not modifying existing files), marking IMPORTANT rather
than BLOCKING.

**Recommendation:** When converging with the CI workflows, extract the
cache-flag logic into the build script itself (e.g., `--cache-type sccache`
instead of bash conditional), or into a thin Python wrapper.

---

### 3. Windows PyTorch Wheels Workflow (`multi_arch_release_windows_pytorch_wheels.yml`)

**Matrix:** 5 Python versions × 4 PyTorch refs = 20 jobs. No torch 2.8 on
Windows (consistent with existing CI).

**Windows-specific handling:**
- `shell: cmd` for the build step (load-bearing — [issue #827](https://github.com/ROCm/TheRock/issues/827))
- `CHECKOUT_ROOT: B:/src` for the Azure Windows runner
- `PACKAGE_DIST_DIR` uses backslashes for `cmd`, bash steps use `cygpath`
- `setup-python` action instead of manylinux container Python
- LLVM shim creation for `objcopy`/`readelf` (needed for kpack on Windows)
- `special-characters-workaround: true` on AWS credentials
- `-j 32` hardcoded (vs `$(nproc)` on Linux)

All of these match the existing CI Windows workflow patterns.

### ⚠️ IMPORTANT: Inline bash with conditionals (Windows)

Same cache-flag and cache-stats patterns as Linux. Additionally, the "Split
PyTorch fat wheel" step (~25 lines) has path manipulation, conditionals, and
filesystem operations. This is more substantial than the Linux variant due to
the LLVM shim creation and `cygpath` conversions.

**Recommendation:** Same as Linux — consolidate when converging with CI
workflows. The kpack split logic is a good candidate for a Python script.

---

### 4. `publish_pytorch_to_staging.py`

Well-structured script:
- `main(argv)` accepts CLI args (testable)
- Uses `get_release_bucket_config` for bucket selection (validates release type)
- Uses `create_storage_backend` → `S3StorageBackend.upload_directory`
  (credentials from ambient AWS session)
- Raises `FileNotFoundError` on missing source dir or zero wheels uploaded
  (fail-fast)
- `--dry-run` flag for manual testing

**Dependencies:** All available in CI:
- `_therock_utils.{s3_buckets,storage_backend,storage_location}` — in-tree
- `boto3` — installed by `pip install -r requirements-ci.txt` before the upload
  step (lazy import in `S3StorageBackend` only fires at upload time)

No issues found.

---

### 5. Tests (`publish_pytorch_to_staging_test.py`)

Tests are well-designed:
- Mock targets are appropriate — `S3StorageBackend.upload_directory` is mocked
  to test routing logic without S3 contact
- Covers all three release types (`dev`, `nightly`, `prerelease`)
- Tests error cases: missing source dir, zero wheels, invalid release type
- Uses real temp directories (not mocked filesystem)

CI confirms tests pass on both Linux and Windows.

No issues found.

---

### 6. Security

- No secrets or credentials committed
- No command injection risks: inputs come from trusted workflow dispatch (not
  user-controlled), and are used as Python script arguments or quoted in bash
- `id-token: write` permission is correctly scoped for OIDC role assumption
- AWS credentials use OIDC federation (no static keys)

No issues found.

---

## Recommendations

### ❌ REQUIRED (Blocking):

None — the code is correct. However, test evidence should be provided before
merge (see below).

### ✅ Recommended:

1. **Provide test evidence.** The test plan and test result are both "tbd". At
   minimum, a dev release dispatch should be run to verify the full pipeline
   (checkout → build → split → upload) works end-to-end. Link the CI run in the
   PR description.

2. **Extract cache-flag logic from inline bash.** The `if/elif/else` for
   `cache_type` selection appears in both Linux and Windows workflows. Consider
   adding a `--cache-type` flag to `build_prod_wheels.py` or a thin wrapper, so
   the workflow `run:` block is a single script invocation.

### 💡 Consider:

1. **Align job names:** "Build PyTorch Wheel" (Linux parent) vs "Build PyTorch
   Wheels" (Windows parent) — use the plural form consistently.

### 📋 Future Follow-up:

1. **Converge with CI workflows.** The PR description notes this is planned.
   The new release workflows are near-copies of
   `build_{portable_linux,windows}_pytorch_wheels_ci.yml`. Sharing the logic via
   reusable workflows or shared scripts would reduce maintenance burden.

2. **Switch to CDN for ROCm packages.** The TODO comment in the parent
   workflows notes this: currently packages are pulled from the artifact bucket,
   but could use the CDN if job ordering allows.

3. **Kpack Windows shims.** The LLVM shim workaround for `objcopy`/`readelf`
   is tracked in [rocm-systems#5506](https://github.com/ROCm/rocm-systems/issues/5506).

---

## Testing Recommendations

1. **End-to-end dev release:** Dispatch `multi_arch_release_linux.yml` with a
   dev config and verify the pytorch wheels job triggers, builds, splits, and
   uploads to `s3://therock-dev-python/v4/whl-staging/`.

2. **Verify split output:** Check that the uploaded artifacts include both the
   host `torch-*.whl` and per-gfx `amd-torch-device-*.whl` files.

3. **Windows parity:** Run the same test for the Windows pipeline.

4. **sccache path (optional):** If sccache will be used in release builds,
   verify the `therock-{release_type}-pytorch-sccache` S3 bucket exists and the
   IAM role has access.

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The implementation is sound — correct input wiring, proper staging upload path,
good Python script with tests, appropriate permissions and pinning. The main gap
is the absence of end-to-end test evidence. The inline bash conditionals are a
pre-existing pattern from the CI workflows but should be addressed during the
planned convergence. Once test evidence is linked in the PR description,
this is ready for human review.
