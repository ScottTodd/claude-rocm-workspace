# PR Review: Split out index file generation from post upload script

* **PR:** [#4168](https://github.com/ROCm/TheRock/pull/4168)
* **Author:** marbre (Marius Brehler)
* **Branch:** `users/marbre/post_build_index` → `main`
* **Reviewed:** 2026-03-27
* **Status:** OPEN

---

## Summary

Removes client-side HTML index generation from `post_build_upload.py` and introduces a standalone `generate_s3_index.py` script designed to be called from an AWS Lambda handler. The script discovers directories under a CI run prefix and generates `index.html` files for each, supporting both S3 and local filesystem backends. The deferred import of `github_actions_api` in `workflow_outputs.py` keeps the Lambda deployment package lean.

**Net changes:** +670 lines, -88 lines across 6 files

---

## Overall Assessment

**✅ APPROVED** — Clean separation of concerns. The new script is well-structured, properly testable with the local backend, and the removal from `post_build_upload.py` is complete (index generation + upload + unused imports all removed). Tests are meaningful and test real behavior via `LocalStorageBackend`.

**Strengths:**

- Good architecture: server-side indexing eliminates CI-time work and is layout-agnostic
- Clean local/S3 backend abstraction — tests don't need S3 mocks
- Proper HTML escaping via `html.escape()` and `urllib.parse.quote()`
- Correct deferred import pattern for Lambda compatibility
- Test mock patch target correctly updated to match deferred import semantics
- `parent_href` parameter with run-root awareness (no parent link for root dirs)

**Issues:**

- Pre-commit (black) is failing — minor formatting issues

---

## Detailed Review

### 1. Pre-commit / Black Formatting Failure

### ❌ BLOCKING: Black formatting failure in CI

CI shows black reformatted two files:

1. **`workflow_outputs.py`**: Missing blank line after the deferred `from` import inside `_retrieve_bucket_info` (black wants a blank line between the import and the call).
2. **`post_build_upload.py`**: Likely extra blank line or trailing whitespace from the removal.

This is the second push that still has this failure, so it's worth running `pre-commit run --all-files` locally.

**Required action:** Run `pre-commit run --all-files` and commit the formatting fixes.

### 2. `generate_s3_index.py` — New Script

**Overall:** Well-organized with clear separation between HTML generation, S3 listing, local listing, and upload orchestration.

### 💡 SUGGESTION: `_pretty_size` rounds down via `int()` truncation

`int(size_bytes / factor)` truncates (e.g., 1536 bytes → `1 KB` rather than `1.5 KB`). This is fine for a directory listing, but worth noting as a conscious choice.

### 💡 SUGGESTION: Variable shadowing in `run()`

In `run()`, the loop variable `dir_prefix` shadows the outer scope:

```python
for dir_prefix in dirs:  # shadows the parameter-derived dir_prefix used above
```

Consider renaming the loop variable to `dir_path` or similar to avoid confusion during maintenance.

### 3. `post_build_upload.py` — Removal

**Overall:** Clean removal. The `index_log_files`, `index_artifact_files`, and `run_command` functions are all gone along with their imports (`shlex`, `subprocess`, `indexer`). The `upload_artifacts` function no longer uploads `index.html` to the artifact index path.

The artifact index URL is still used in the job summary link (line 271 on main via `output_root.artifact_index(artifact_group).https_url`) — this is correct since the Lambda will generate the index at that URL after upload.

### 4. `workflow_outputs.py` — Deferred Import

**Overall:** Correct approach. The module-level docstring addition clearly documents the Lambda packaging boundary. The deferred import inside the `if` guard is clean.

### 5. Test Changes

### `generate_s3_index_test.py`

Good test coverage using `LocalStorageBackend` for integration tests — avoids S3 mocking entirely. Tests cover:
- Immediate listing (files + subdirs, excluding index.html)
- Missing directory handling
- Sorted order
- Directory discovery at various depths
- Single-arch and multi-arch layouts
- Empty directory behavior
- HTML content (entries, parent links, escaping)

### ⚠️ IMPORTANT: No test for `_discover_dirs_with_files_local` excluding `index.html`

`_discover_dirs_with_files_local` skips `index.html` files when discovering directories. This is important behavior (prevents stale index.html from creating phantom directory entries on re-indexing), but there's no test that verifies a directory containing *only* `index.html` is excluded from results.

**Recommendation:** Add a test case where a directory contains only `index.html` and verify it's not in the discovered dirs.

### 💡 SUGGESTION: No test for the S3 listing paths

The S3 listing functions (`_list_files_s3`, `_discover_dirs_with_files_s3`) have no unit tests. The local equivalents are well-tested, and S3 tests would require mocking boto3, so this is understandable — but it's a gap worth noting.

### `post_build_upload_test.py`

Correctly updated: removed `index.html` creation in test setup and flipped the assertion from `assertTrue` to `assertFalse` for the artifact index path.

### `workflow_outputs_test.py`

Mock patch target correctly updated to `github_actions.github_actions_api.gha_query_workflow_run_by_id` (the definition site) since the import is now deferred. Comment explains the reasoning clearly.

### 6. Architecture — Lambda Integration Surface

### 📋 FUTURE WORK: Lambda handler not included

The PR description notes the Lambda handler is not part of this PR. The function signature of `generate_index_for_directory` is clean for Lambda use — `bucket`, `dir_prefix`, `backend`, and `s3_client` can all be provided by the handler.

One note: `_discover_dirs_with_files_s3` lists all objects under the run prefix (full enumeration). For the Lambda (triggered per-object PutObject event), only the parent directory of the uploaded object needs indexing, so `generate_index_for_directory` is the right entry point — `run()` and the discovery functions are CLI-only. This is a clean separation.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Fix black formatting failures (run `pre-commit run --all-files`)

### ✅ Recommended:

1. Add a test case for `_discover_dirs_with_files_local` where a directory contains only `index.html` — verify it's excluded

### 💡 Consider:

1. Rename loop variable `dir_prefix` in `run()` to avoid shadowing

### 📋 Future Follow-up:

1. Lambda handler implementation (noted as out of scope)
2. Removal of third-party `indexer.py` script (noted as out of scope)

---

## Testing Recommendations

Run the tests listed in the PR description:
```bash
python -m pytest build_tools/tests/generate_s3_index_test.py \
                 build_tools/tests/workflow_outputs_test.py \
                 build_tools/github_actions/tests/post_build_upload_test.py
```

Verify pre-commit passes:
```bash
pre-commit run --all-files
```

---

## Conclusion

**Approval Status: ✅ APPROVED** (pending pre-commit fix)

Solid PR that cleanly separates index generation from the upload pipeline. The only blocking issue is the black formatting failure in CI, which is a trivial fix. The architecture is sound for the Lambda integration described in the PR body. The test coverage is good, with one recommended addition for the index.html exclusion behavior.
