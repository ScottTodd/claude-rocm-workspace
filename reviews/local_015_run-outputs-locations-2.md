# Branch Review: run-outputs-locations-2

* **Branch:** `run-outputs-locations-2`
* **Base:** `main`
* **Reviewed:** 2026-02-24
* **Commits:** 9 commits
* **Previous review:** `local_014_run-outputs-locations-2.md` (5 commits)

---

## Summary

This branch centralizes CI run output path computation into `RunOutputRoot` /
`OutputLocation` (frozen dataclasses), adds `UploadBackend` (ABC + S3/Local
implementations) for file uploads, and migrates `post_build_upload.py`,
`upload_python_packages.py`, and `upload_pytorch_manifest.py` to use both
abstractions. `_retrieve_bucket_info` is moved from `github_actions_utils.py`
into `run_outputs.py`. The `from_workflow_run()` factory now makes GitHub API
lookup opt-in (`lookup_workflow_run=False` by default).

**Net changes:** +2285 lines, -679 lines across 18 files (1 new doc, 3 new
modules, 3 new test files, 11 modified files)

---

## Overall Assessment

**CHANGES REQUESTED** -- Documentation needs updating

**Strengths:**

- Clean three-layer architecture: `run_outputs` (paths), `upload_backend`
  (upload I/O), `artifact_backend` (download I/O)
- `OutputLocation` works well as the bridge between path computation and I/O
- `LocalUploadBackend` enables real filesystem tests without mocking
- `lookup_workflow_run` parameter correctly fixes the BLOCKING issue from review
  014 (unwanted API calls)
- Test isolation for `_retrieve_bucket_info` env vars is properly handled
- 338 tests pass, 1 skipped

**Issues:**

- `run_outputs_layout.md` is stale after the later commits (IMPORTANT)
- Two migrated scripts lack tests (IMPORTANT)
- One upload script not yet migrated (IMPORTANT)
- Input validation gaps carried over from old code (IMPORTANT)

---

## Detailed Review

### 1. Documentation (`run_outputs_layout.md`)

#### IMPORTANT: Consumers table is incomplete

**File:** `docs/development/run_outputs_layout.md:114-122`

The table lists 4 consumers but misses at least 4 introduced by this branch:

| Missing consumer | Usage |
|---|---|
| `upload_python_packages.py` | `RunOutputRoot.from_workflow_run()`, `UploadBackend` |
| `upload_pytorch_manifest.py` | `RunOutputRoot.from_workflow_run()`, `OutputLocation`, `UploadBackend` |
| `fetch_artifacts.py` | `RunOutputRoot.from_workflow_run(lookup_workflow_run=True)` |
| `find_artifacts_for_commit.py` | `RunOutputRoot.from_workflow_run(workflow_run=...)` |

**Required action:** Add all consumers to the table.

#### IMPORTANT: "Calls GitHub API" comment is incorrect

**File:** `docs/development/run_outputs_layout.md:88`

```python
# From CI environment (calls GitHub API for bucket selection)
root = RunOutputRoot.from_workflow_run(run_id="12345", platform="linux")
```

The default behavior (`lookup_workflow_run=False`) does **not** call the GitHub
API. The comment is misleading and will cause callers to avoid the factory
unnecessarily.

**Required action:** Fix the comment. Show both modes (default and with lookup).

#### IMPORTANT: No mention of `UploadBackend` or overall architecture

The doc describes path computation (`run_outputs.py`) but says nothing about
upload I/O (`upload_backend.py`) or download I/O (`artifact_backend.py`). The
three-layer architecture is the key design contribution of this branch:

1. **Path computation** (`run_outputs.py`): `RunOutputRoot` + `OutputLocation`
2. **Upload I/O** (`upload_backend.py`): `UploadBackend` ABC + S3/Local
3. **Download I/O** (`artifact_backend.py`): `ArtifactBackend` ABC + S3/Local

**Required action:** Add an "Architecture" section describing the three layers,
with `OutputLocation` as the bridge between path computation and I/O.

#### IMPORTANT: `lookup_workflow_run` parameter not documented

The `lookup_workflow_run` parameter is the key difference between "running inside
your own CI workflow" (env vars suffice, no API call) vs. "looking up another
repo's workflow run" (`fetch_artifacts.py`). A reader who needs to fetch
artifacts wouldn't know this parameter exists without reading source code.

**Required action:** Document the parameter and when to use it.

#### SUGGESTION: `root()` method missing from the location methods list

`RunOutputRoot.root()` is used by `post_build_upload.py` for artifact uploads
but doesn't appear in the doc's code example (lines 94-103).

#### SUGGESTION: `therock-build-prof/` subdirectory and flattening not shown

The directory tree shows `comp-summary.html` at the log root but doesn't show
the `therock-build-prof/` subdirectory or explain the dual-upload flattening
pattern used in `post_build_upload.py`.

---

### 2. Tests

#### IMPORTANT: No tests for `upload_python_packages.py` or `upload_pytorch_manifest.py`

Both scripts were significantly refactored (removing `UploadPath`, `run_aws_cp`,
`run_local_cp`; replacing with `RunOutputRoot` + `UploadBackend`) but have zero
test coverage. Key untested behaviors:

- `_make_run_root()` with/without `bucket_override`
- `upload_packages()` delegating to `backend.upload_directory()`
- `upload_pytorch_manifest.py`'s manual `OutputLocation` construction
- `normalize_python_version_for_filename()` and `sanitize_ref_for_filename()`
  (pure functions, trivial to test)

**Recommendation:** Add test files using `LocalUploadBackend` with temp dirs,
matching the pattern in `post_build_upload_test.py`.

---

### 3. Incomplete migration

#### IMPORTANT: `upload_test_report_script.py` not migrated to `UploadBackend`

**File:** `github_actions/upload_test_report_script.py:63-81`

This script was updated to use `RunOutputRoot` for path computation but still
uses raw `aws s3 cp` subprocess calls. It lacks `--output-dir` and `--dry-run`
flags, unlike the three fully-migrated scripts. This is the only remaining
upload script that doesn't use `UploadBackend`.

**Recommendation:** Either migrate in this branch or add a TODO comment noting
it's deferred to a follow-up.

---

### 4. Input validation

#### IMPORTANT: `RELEASE_TYPE` used unsanitized in bucket name

**File:** `_therock_utils/run_outputs.py:363`

```python
bucket = f"therock-{release_type}-artifacts"
```

`RELEASE_TYPE` from the environment is interpolated directly into the bucket
name. Expected values are `nightly`, `release`, `dev`. A simple validation
would prevent accidental misconfiguration from producing an invalid bucket name.

**Recommendation:** Add allowlist validation:
```python
_VALID_RELEASE_TYPES = {"nightly", "release", "dev"}
if release_type not in _VALID_RELEASE_TYPES:
    raise ValueError(f"Invalid RELEASE_TYPE={release_type!r}, expected one of {_VALID_RELEASE_TYPES}")
```

#### IMPORTANT: `github_repository.split("/")` lacks validation

**File:** `_therock_utils/run_outputs.py:353`

```python
owner, repo_name = github_repository.split("/")
```

If `github_repository` doesn't contain exactly one `/`, this raises an opaque
`ValueError`. A guard would produce a clear error message.

---

### 5. Code quality

#### SUGGESTION: Broad `except Exception` in S3 retry loop

**File:** `_therock_utils/upload_backend.py:176-186`

The retry loop catches `Exception`, which includes non-retryable errors like
`TypeError`, `ValueError`, or `FileNotFoundError`. Narrowing to
`botocore.exceptions.ClientError` (or `(OSError, BotoCoreError)`) would let
programming errors fail fast.

#### SUGGESTION: Module-level import couples `run_outputs.py` to `github_actions_utils`

**File:** `_therock_utils/run_outputs.py:41-43`

```python
sys.path.insert(0, os.fspath(Path(__file__).parent.parent))
from github_actions.github_actions_utils import gha_query_workflow_run_by_id
```

Any import of `OutputLocation` triggers loading `github_actions_utils` and
`sys.path` mutation. The function is only used in `_retrieve_bucket_info()`.
A lazy import would decouple the dataclasses from the GitHub API module.

#### SUGGESTION: Duplicate `_make_run_root` helper

**Files:** `upload_python_packages.py:64-69`, `upload_pytorch_manifest.py:49-54`

Both scripts define identical `_make_run_root(run_id, bucket_override)` helpers.
Consider a shared factory on `RunOutputRoot` or a utility function.

#### SUGGESTION: Manual `OutputLocation` construction in `upload_pytorch_manifest.py`

**File:** `upload_pytorch_manifest.py:128-132`

```python
manifest_dir_loc = run_root.manifest_dir(args.amdgpu_family)
dest = OutputLocation(
    manifest_dir_loc.bucket,
    f"{manifest_dir_loc.relative_path}/{manifest_name}",
)
```

This bypasses `RunOutputRoot` to construct a path. A `manifest_file(group,
filename)` method (like `log_file()`) would close this gap.

---

### 6. Architecture (positive observations)

- The separation between `run_outputs` (pure path computation), `upload_backend`
  (write I/O), and `artifact_backend` (read I/O) is clean
- `OutputLocation` works consistently as the bridge in both directions
- All three migrated upload scripts follow the same pattern:
  `RunOutputRoot` -> `create_upload_backend()` -> `upload_file()`/`upload_directory()`
- The `lookup_workflow_run` parameter design is sound: opt-in API calls,
  with the `workflow_run` dict taking priority when provided
- `LocalUploadBackend` enables real filesystem tests without mocking

---

## Recommendations

### REQUIRED (Blocking):

None -- no blocking code issues.

### REQUIRED (Documentation):

1. Update `run_outputs_layout.md` consumers table with all actual consumers
2. Fix "calls GitHub API" comment to reflect `lookup_workflow_run=False` default
3. Add architecture section describing the three-layer design
4. Document `lookup_workflow_run` parameter and usage

### Recommended:

5. Add tests for `upload_python_packages.py` and `upload_pytorch_manifest.py`
6. Add input validation for `RELEASE_TYPE` and `github_repository` format
7. Migrate `upload_test_report_script.py` or add TODO

### Consider:

8. Narrow `except Exception` to boto-specific exceptions in S3 retry loop
9. Make `gha_query_workflow_run_by_id` a lazy import
10. Add `manifest_file(group, filename)` method to `RunOutputRoot`
11. Deduplicate `_make_run_root` helper

### Future Follow-up:

12. Deduplicate S3 client initialization between `artifact_backend` and
    `upload_backend`
13. Converge logging approach across modules (`_log()` / `logging` / `print`)
14. `find_artifacts_for_commit.py` still duplicates some path logic from
    `RunOutputRoot`

---

## Testing Recommendations

All 338 tests pass. To strengthen coverage:

- Add `upload_python_packages_test.py` using `LocalUploadBackend` with temp dirs
- Add `upload_pytorch_manifest_test.py` with similar approach
- Add test for `RunOutputRoot.artifact("")` pattern used by `S3Backend.base_uri`
- Consider end-to-end test for `post_build_upload.run()` control flow

---

## Conclusion

**Approval Status: CHANGES REQUESTED**

The code changes are solid -- no blocking issues in the implementation. The
architecture is clean and the migration is well-executed. The documentation
needs updating to reflect the changes made in later commits (consumers table,
API comments, architecture description, `lookup_workflow_run`). Fix the doc,
and this is ready.
