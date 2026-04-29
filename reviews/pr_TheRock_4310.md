# PR Review: Streamline multi arch native package workflow

* **PR:** [#4310](https://github.com/ROCm/TheRock/pull/4310)
* **Author:** nunnikri (Nirmal Unnikrishnan)
* **Base:** `main` ← `users/nunnikri/multi-arch-workflow-updates`
* **Reviewed:** 2026-04-23
* **Status:** OPEN

---

## Summary

This PR modernizes the `multi_arch_build_native_linux_packages.yml` workflow with several changes:
1. Switches artifact fetching from `fetch_artifacts.py` to `artifact_manager.py fetch`
2. Removes the `artifact_group` input (no longer needed with `artifact_manager.py`)
3. Adds automatic KPACK detection via a new `detect_kpack.py` script (replaces hardcoded `--enable_kpack=false`)
4. Adds `--platform` parameter plumbing and `package_repository_url` output
5. Updates S3 upload to use `multi_arch_s3_bucket`/`multi_arch_s3_prefix` outputs
6. Adds an `if` guard on the AWS credentials step restricting it to ROCm/TheRock and ROCm/rockrel
7. Adds documentation for S3 configuration and package repository URLs
8. Various style fixes (quoting, `llvm` → `llvm-20`, removing echo noise)

**Net changes:** +334 lines, -41 lines across 4 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The PR has an undeclared dependency on [#4633](https://github.com/ROCm/TheRock/pull/4633) and a stale PR description (already flagged by a reviewer). The new code is generally clean but has a few issues.

**Strengths:**
- Switching to `artifact_manager.py` is the right direction — consistent with multi-arch CI patterns
- KPACK auto-detection from manifest is well-structured and properly tested
- Adding the `if` guard on AWS credentials is good security practice
- Quoting workflow variable expansions is a worthwhile cleanup

**Issues:**
- Hard dependency on unmerged PR #4633 for `get_s3_config.py` changes
- Stale PR description claims `get_s3_config.py` changes that aren't here
- Test uses `sys.path.insert` hack instead of proper imports

---

## Detailed Review

### 1. Workflow: `multi_arch_build_native_linux_packages.yml`

#### ❌ BLOCKING: Undeclared dependency on PR #4633

The workflow passes `--platform linux` to `get_s3_config.py` (line 106) and reads `multi_arch_s3_bucket` / `multi_arch_s3_prefix` outputs (lines 190-191), but neither the `--platform` argument nor those output names exist in the current `get_s3_config.py` on `main`. PR [#4633](https://github.com/ROCm/TheRock/pull/4633) adds them.

- If this PR merges before #4633, the workflow will fail at both the "Determine S3 bucket and prefix" step (unknown `--platform` arg) and the "Upload Package repo to S3" step (empty bucket/prefix).
- **Required action:** Either (a) declare #4633 as a prerequisite and note it in the PR description, or (b) rebase this PR on top of #4633's branch, or (c) merge #4633 first.

#### ❌ BLOCKING: Stale PR description

Already flagged by a reviewer. The PR description describes `get_s3_config.py` changes (`determine_s3_config()` returns 4-tuple, `generate_package_repository_url()`, etc.) that aren't in this PR — they're in #4633. This is misleading for reviewers.

- **Required action:** Update the title and description to reflect what this PR actually contains.

#### ⚠️ IMPORTANT: `artifact_manager.py fetch` missing `--run-github-repo`

The call at line 145-149 doesn't pass `--run-github-repo`. While this defaults to `None` and `create_backend_from_env()` falls back to the `GITHUB_REPOSITORY` env var in CI, the old `fetch_artifacts.py` call explicitly passed `--run-github-repo="${{ github.repository }}"`. Being explicit is safer — if the env var isn't set for some reason, the fetch will fail with a cryptic error.

- **Recommendation:** Add `--run-github-repo="${{ github.repository }}"` to match the explicit style used elsewhere.

#### ⚠️ IMPORTANT: No callers currently wire this workflow

The `multi_arch_build_native_linux_packages.yml` workflow has no callers on `main` — `multi_arch_release_linux.yml` has a TODO for native packages. This means:
- The `artifact_group` input removal is safe (no callers to break)
- But the new `package_repository_url` output won't be consumed until a caller is wired up
- Changes can't be validated end-to-end in CI until a caller exists

This isn't blocking, but worth noting for testing strategy.

#### 💡 SUGGESTION: S3 config comment could be shorter

The multi-line comment (lines 79-83) explaining `get_s3_config.py`'s behavior is helpful but could just point to the script:

```yaml
# See get_s3_config.py for bucket/URL selection based on release type
```

The detailed decision tree is in the script itself and in the new docs.

### 2. New file: `detect_kpack.py`

#### ⚠️ IMPORTANT: `detect_kpack.py` stderr output uses emoji

Lines 87 and 91 use `✓` in stderr messages. While not technically wrong, the [Python style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/python_style_guide.md) doesn't use emojis in CLI output, and this can cause encoding issues in some terminal configurations.

- **Recommendation:** Remove the `✓` prefix from the stderr messages.

#### 💡 SUGGESTION: `find_manifest_files` could use early return

If the artifacts directory has a large number of files, `rglob("therock_manifest.json")` will traverse everything. This is fine for CI but could be noted. No action needed — just a design observation.

### 3. New file: `detect_kpack_test.py`

#### ⚠️ IMPORTANT: Test uses `sys.path.insert` hack

The test file manipulates `sys.path` at import time (line 16):
```python
sys.path.insert(0, str(Path(__file__).parent.parent))
```

This is fragile and goes against the project's approach of using `pytest` with proper discovery. Other test files in `build_tools/packaging/linux/tests/` (like `get_s3_config_test.py`) may use the same pattern, but if they don't, this should be aligned.

- **Recommendation:** Check how other tests in the same directory handle imports and follow the same pattern.

#### 💡 SUGGESTION: Tests are solid but could add a corrupt JSON test

The test coverage is good (enabled, disabled, multiple manifests, no manifests, missing field). Consider adding a test for a corrupt/unparseable JSON file to exercise the `json.JSONDecodeError` catch in `check_kpack_enabled`.

### 4. Documentation: `native_packaging.md`

#### ⚠️ IMPORTANT: Documentation references outputs that don't exist yet

The docs reference `multi_arch_s3_bucket`/`multi_arch_s3_prefix` outputs and `generate_package_repository_url()` — all from #4633. If this PR merges first, the docs will be inaccurate.

- **Recommendation:** Ensure this merges after #4633, or move the documentation to #4633.

#### 💡 SUGGESTION: Table formatting is comprehensive but may get stale

The detailed URL tables are useful reference material, but hardcoded domains and path patterns can drift. Consider whether this belongs in the script's docstring (closer to the code) vs. standalone docs.

### 5. Workflow: AWS credentials guard

The new `if` condition on the "Configure AWS Credentials" step:
```yaml
if: ${{ (github.repository == 'ROCm/TheRock' || github.repository == 'ROCm/rockrel') && !github.event.pull_request.head.repo.fork }}
```

This is good — restricts OIDC role assumption to authorized repos. For non-PR triggers (workflow_call), `github.event.pull_request.head.repo.fork` is null, and `!null` is truthy in GHA expressions, so the condition correctly allows non-PR invocations. However:

#### ⚠️ IMPORTANT: Upload step has no matching guard

The "Upload Package repo to S3" step (line 189) will run even if AWS credentials weren't configured (when the `if` condition is false). This would fail because `aws` commands need credentials. Either add a matching `if` to the upload step, or ensure the upload script handles missing credentials gracefully.

- **Recommendation:** Add the same `if` condition to the upload step, or add a check like `if: steps.aws_credentials.outcome == 'success'` (requires giving the credentials step an `id`).

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Declare dependency on #4633 and ensure merge ordering, or rebase on #4633
2. Update PR title and description to accurately reflect changes (stale content about `get_s3_config.py`)

### ✅ Recommended:

1. Add `--run-github-repo="${{ github.repository }}"` to the `artifact_manager.py fetch` call for explicitness
2. Add an `if` guard on the "Upload Package repo to S3" step to match the AWS credentials guard
3. Remove emoji (`✓`) from `detect_kpack.py` stderr output
4. Align test import pattern with other tests in the same directory (check if `sys.path.insert` is standard there)
5. Ensure documentation additions match what's actually available (or move docs to #4633)

### 💡 Consider:

1. Add a corrupt JSON test case for `detect_kpack_test.py`
2. Shorten the inline comment explaining `get_s3_config.py` behavior

### 📋 Future Follow-up:

1. Wire up a caller for this workflow in `multi_arch_release_linux.yml` to enable end-to-end testing

---

## Testing Recommendations

- Unit tests pass (confirmed via CI: "Unit Tests :: ubuntu-24.04" and "Unit Tests :: windows-2022" both pass)
- Pre-commit passes
- End-to-end validation blocked because no caller workflow exists yet and the foundation stage fails in CI
- **Key verification:** Ensure #4633 merges first, then test a `workflow_dispatch` run to validate the full flow (S3 config → fetch → detect kpack → build → upload)

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The core changes (artifact_manager migration, KPACK detection, credential guard) are well-structured. The main blocker is the undeclared dependency on PR #4633 for `get_s3_config.py` changes — without those, the workflow will fail at runtime. The stale PR description compounds the confusion. Fix the merge ordering and description, address the upload step guard gap, and this should be ready.
