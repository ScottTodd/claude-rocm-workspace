# Branch Review: run-outputs-locations-2

* **Branch:** `run-outputs-locations-2`
* **Base:** `main`
* **Reviewed:** 2026-02-24
* **Commits:** 6 commits

---

## Summary

This branch introduces `RunOutputRoot` and `OutputLocation` as the single source of truth for CI run output path computation, plus an `UploadBackend` abstraction that replaces raw `aws s3 cp` subprocess calls with Python-native boto3 uploads. Three upload scripts (`post_build_upload.py`, `upload_python_packages.py`, `upload_pytorch_manifest.py`) are migrated to use the new abstractions. Bucket selection logic is moved from `github_actions_utils.py` into `run_outputs.py`.

**Net changes:** +2200 lines, -678 lines across 18 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — One behavioral change needs to be addressed before merge.

**Strengths:**

- Clean abstraction layering: path computation (`RunOutputRoot`) is fully separated from I/O (`UploadBackend`)
- Frozen dataclasses with well-designed interfaces
- Good factory pattern (`create_upload_backend()` with explicit args, not env vars)
- Thorough test coverage — 89+ new tests covering path computation, upload mechanics, and file placement
- Tests use `LocalUploadBackend` with real files instead of mocking subprocess calls
- Consistent patterns between download (`artifact_backend.py`) and upload (`upload_backend.py`) sides
- Content-type inference is an improvement over the old hardcoded `text/plain` for all log files

**Issues:**

- 1 blocking: `from_workflow_run` introduces GitHub API calls where old code relied on env vars alone
- Several important: test environment isolation, missing integration tests for two scripts, broad exception catch

---

## Detailed Review

### 1. Correctness

#### ❌ BLOCKING: `from_workflow_run` adds GitHub API calls to two scripts

**Files:** `post_build_upload.py:281`, `upload_python_packages.py:153` (via `_make_run_root`)

The old code called `retrieve_bucket_info()` with **no arguments**, meaning `workflow_run_id` was `None` and no GitHub API call was made. Bucket selection relied entirely on environment variables (`GITHUB_REPOSITORY`, `IS_PR_FROM_FORK`, `RELEASE_TYPE`).

The new code calls `RunOutputRoot.from_workflow_run(run_id=args.run_id, ...)`, which passes the `run_id` to `_retrieve_bucket_info`, triggering `gha_query_workflow_run_by_id()`. This adds:
1. A network dependency that did not exist before
2. A new failure mode if the GitHub API is unreachable or rate-limited
3. Different fork detection behavior (API-based vs env-var `IS_PR_FROM_FORK`)

`upload_pytorch_manifest.py` is NOT affected — the old code already passed `workflow_run_id=run_id`.

**Required action:** Either (a) make `from_workflow_run` accept an option to skip the API call when env vars suffice, (b) pass `workflow_run=None` explicitly to avoid the API call when `run_id` is provided but API-based metadata isn't needed, or (c) document this as an intentional improvement in the PR description with the rationale for the change.

#### ⚠️ IMPORTANT: Upload errors now propagate instead of being swallowed

**File:** `post_build_upload.py` (old `run_aws_cp` → new `S3UploadBackend`)

The old `run_aws_cp` caught `subprocess.CalledProcessError` and only logged the error. The new `S3UploadBackend.upload_file` raises `RuntimeError` after retry exhaustion. This is correct per fail-fast principles but CI runs that previously survived transient S3 failures will now fail. This should be documented as an intentional improvement in the PR description.

### 2. Architecture

#### ⚠️ IMPORTANT: Manual `OutputLocation` construction in `upload_pytorch_manifest.py`

**File:** `upload_pytorch_manifest.py:128-132`

```python
manifest_dir_loc = run_root.manifest_dir(args.amdgpu_family)
dest = OutputLocation(
    manifest_dir_loc.bucket,
    f"{manifest_dir_loc.relative_path}/{manifest_name}",
)
```

This constructs an `OutputLocation` by hand, appending to an existing location's relative path. This is the kind of ad-hoc path assembly that `RunOutputRoot` was designed to eliminate. Consider adding an `OutputLocation.child(name)` method or a `RunOutputRoot.manifest_file(artifact_group, filename)` method that returns the complete location.

#### 💡 SUGGESTION: Duplicate `_make_run_root()` helper in two scripts

**Files:** `upload_python_packages.py:63-68`, `upload_pytorch_manifest.py:52-57`

Both files define identical `_make_run_root()` helpers. This could be a classmethod on `RunOutputRoot` (e.g., `from_workflow_run_or_bucket()`). Only two call sites, so tolerable, but worth extracting if a third consumer appears.

#### 💡 SUGGESTION: `run_outputs.py` imports from `github_actions.github_actions_utils`

**File:** `run_outputs.py:41-43`

The `sys.path.insert(0, ...)` and import of `gha_query_workflow_run_by_id` creates an upward dependency from a utility package (`_therock_utils`) into the `github_actions` package. This means any importer of `_therock_utils.run_outputs` transitively depends on `github_actions_utils`. The coupling works but is structural debt. Consider injecting the API caller into `from_workflow_run()` as a parameter.

### 3. Test Coverage

#### ⚠️ IMPORTANT: `_retrieve_bucket_info` tests not isolated from environment

**File:** `run_outputs_test.py`

Several `TestRetrieveBucketInfo` tests do not use `mock.patch.dict(os.environ, ...)` to isolate from the test runner's environment. If `RELEASE_TYPE`, `IS_PR_FROM_FORK`, or `GITHUB_REPOSITORY` are set in the CI environment, these tests could produce incorrect results.

**Affected tests:** `test_internal_releases_repo`, `test_with_workflow_run_recent`, `test_with_workflow_run_old`, `test_with_workflow_run_from_fork`, `test_workflow_run_id_triggers_api_call`

**Recommendation:** Wrap with `@mock.patch.dict(os.environ, {}, clear=False)` that explicitly removes potentially-interfering variables.

#### ⚠️ IMPORTANT: No integration tests for `upload_python_packages.py` or `upload_pytorch_manifest.py`

These scripts underwent significant migrations but have no script-level integration tests verifying:
- `upload_packages()` produces correct S3 path structure
- `upload_pytorch_manifest.py::main()` uploads to the same path as old code
- The new `--output-dir` and `--dry-run` flags work

The `post_build_upload_test.py` migration has good integration tests — the pattern should be applied to the other two scripts.

#### 💡 SUGGESTION: Missing boundary test for bucket cutover date

**File:** `run_outputs_test.py`

Tests exist for dates well before and well after the `_BUCKET_CUTOVER_DATE` (`2025-11-11T16:18:48Z`), but no test for the exact boundary. A boundary test would verify the `<=` vs `<` semantics.

#### 💡 SUGGESTION: Missing test for external repo + old workflow_run (cutover for external bucket)

The code at `run_outputs.py:359` has a separate cutover path for external repos (`therock-artifacts-external` vs `therock-ci-artifacts-external`). This path is not tested.

### 4. Style

#### ⚠️ IMPORTANT: Broad `except Exception` in S3 retry loop

**File:** `upload_backend.py:187`

The retry loop catches all `Exception` subclasses, including programming errors (`TypeError`, `AttributeError`). The Python style guide says "Catch specific exceptions." Consider catching `botocore.exceptions.ClientError | botocore.exceptions.BotoCoreError | OSError`.

#### ⚠️ IMPORTANT: `upload_packages()` parameter `backend` has no type annotation

**File:** `upload_python_packages.py:102`

```python
def upload_packages(dist_dir: Path, packages_loc: OutputLocation, backend):
```

Should be `backend: UploadBackend`. The `UploadBackend` import is already present as `create_upload_backend` — need to also import `UploadBackend` directly.

#### 💡 SUGGESTION: Inconsistent logging patterns across modules

New modules split between `logging` module (`upload_backend.py`), `_log()` with print+flush (`run_outputs.py`), and per-script `log()` functions (`post_build_upload.py`, `upload_python_packages.py`, `upload_pytorch_manifest.py`). Not blocking but worth being intentional about.

#### 💡 SUGGESTION: `tempfile` imported inline in test methods

**File:** `upload_backend_test.py`

10 inline `import tempfile` statements scattered across test methods. The style guide says imports should be at the top of the file.

#### 💡 SUGGESTION: Unused `PurePosixPath` import in tests

**File:** `run_outputs_test.py:7`

`from pathlib import Path, PurePosixPath` — `PurePosixPath` is never used.

### 5. Security

No security vulnerabilities identified. Specific observations:

- AWS credentials are handled correctly (lazy init, env vars, not logged)
- Path traversal is mitigated by `relative_to()` validation and symlink filtering
- Subprocess calls use list-based construction (no shell injection risk)
- `RELEASE_TYPE` is interpolated into bucket names without validation, but S3 rejects invalid characters

#### 💡 SUGGESTION: Consider `OutputLocation.child()` with traversal guard

`OutputLocation.local_path()` does not validate against `../` in `relative_path`. In practice all paths are constructed from trusted fields, but a defense-in-depth check could be added.

### 6. Documentation

The new `docs/development/run_outputs_layout.md` is a good addition. The consumer table accurately tracks migration status.

### 7. Future Work

#### 📋 FUTURE WORK: `upload_test_report_script.py` still uses raw subprocess + aws s3 cp

Last unmigrated upload consumer. Intentionally excluded from this branch.

#### 📋 FUTURE WORK: `ArtifactRunInfo` in `find_artifacts_for_commit.py` partially duplicates `RunOutputRoot`

Existing TODO comment acknowledges this. Consider composing rather than duplicating.

#### 📋 FUTURE WORK: Download backend (`S3Backend`) lacks retry logic

Upload backend has 3 retries with exponential backoff; download backend does not.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Address the `from_workflow_run` behavioral change — two scripts now make GitHub API calls where they previously did not. Either skip the API call when not needed, or document this as intentional.

### ✅ Recommended:

1. Add type annotation `backend: UploadBackend` in `upload_packages()` signature
2. Narrow `except Exception` to `botocore.exceptions.ClientError | BotoCoreError | OSError` in S3 retry loop
3. Isolate `_retrieve_bucket_info` tests from environment variables
4. Add integration tests for `upload_python_packages.py` and `upload_pytorch_manifest.py` following the `post_build_upload_test.py` pattern
5. Consider adding `OutputLocation.child(name)` to avoid manual path assembly in `upload_pytorch_manifest.py`

### 💡 Consider:

1. Move inline `import tempfile` to top of `upload_backend_test.py`
2. Remove unused `PurePosixPath` import in `run_outputs_test.py`
3. Extract duplicate `_make_run_root()` into a shared factory
4. Add boundary test for bucket cutover date
5. Add test for external repo + old workflow_run cutover path

### 📋 Future Follow-up:

1. Migrate `upload_test_report_script.py` to `UploadBackend`
2. Add retry logic to download backend (`S3Backend`)
3. Simplify `ArtifactRunInfo` to compose `RunOutputRoot` rather than duplicating fields
4. Address import coupling: `run_outputs.py` → `github_actions_utils`

---

## Testing Recommendations

```bash
# Run all build_tools tests
cd /d/projects/TheRock
python -m pytest build_tools/tests/ build_tools/github_actions/tests/ -v

# Verify local output mode works end-to-end
python build_tools/github_actions/post_build_upload.py \
  --artifact-group test-group \
  --build-dir /tmp/fake-build \
  --output-dir /tmp/staging \
  --no-upload

# Verify dry-run mode for new scripts
python build_tools/github_actions/upload_pytorch_manifest.py \
  --dist-dir /tmp/fake-dist \
  --run-id 12345 \
  --amdgpu-family gfx94X-dcgpu \
  --python-version 3.11 \
  --pytorch-git-ref nightly \
  --dry-run
```

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The architecture is sound and the migration is well-executed. The `RunOutputRoot` → `OutputLocation` → `UploadBackend` layering establishes clean separation between path computation and I/O. Test coverage is thorough. The one blocking issue — the behavioral change where `from_workflow_run` now triggers GitHub API calls in two scripts that previously relied only on environment variables — needs to be resolved or explicitly acknowledged before merge.
