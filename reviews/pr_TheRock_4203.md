# PR Review: Add SHA256 conflict detection to artifact uploads

* **PR:** [#4203](https://github.com/ROCm/TheRock/pull/4203)
* **Author:** PeterCDMcLean
* **Reviewed:** 2026-03-30
* **Fixes:** [#4202](https://github.com/ROCm/TheRock/issues/4202)

---

## Summary

Adds conflict detection to artifact uploads: before uploading, check if the
artifact already exists and compare SHA256 hashes. If identical, skip the
upload; if different, raise `ArtifactConflictError`. Also makes tar archives
reproducible (normalized timestamps/ownership, sorted file order) and sets
`ROCM_BUILD_ID` in all workflow configure steps.

**Net changes:** +1060 lines, -93 lines across 13 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The core idea is sound and needed, but there are
architectural issues that should be addressed before merge.

**Strengths:**

- Correct diagnosis of the problem (silent overwrites of generic artifacts)
- Reproducible archives (`fileset_tool.py`) are essential for SHA comparison
  to work and well-implemented
- Good test coverage for the new conflict detection paths

**Issues:**

- `ArtifactConflictError` is retried as a transient failure (bug)
- Conflict detection is implemented at two independent layers with different
  mechanisms and different error types
- `storage_backend.py` changes download full artifacts from S3 for every
  upload — expensive and arguably out of scope

---

## Detailed Review

### 1. `artifact_manager.py` — ArtifactConflictError is retried

### ❌ BLOCKING: Conflict errors must not be retried

The `upload_artifact()` function catches all `Exception` and retries up to 3
times. `ArtifactConflictError` inherits from `Exception`, so a conflict will
be retried 3 times with exponential backoff before finally being logged as a
generic upload failure.

A SHA conflict means the build system produced different output for the same
artifact — retrying will never fix this. It should be re-raised immediately.

```python
for attempt in range(MAX_RETRIES):
    try:
        ...
        request.backend.upload_artifact(...)
        return True
    except Exception as e:  # ← catches ArtifactConflictError too
        if attempt < MAX_RETRIES - 1:
            ...  # retries a non-transient error
```

**Required action:** Add an early `except ArtifactConflictError: raise` before
the generic `except Exception` handler, or restructure to only retry on
transient errors.

---

### 2. `storage_backend.py` — Dual-layer conflict detection

### ⚠️ IMPORTANT: Conflict detection at two independent layers is confusing and expensive

The PR adds conflict detection in both:

- **`artifact_backend.py`** — SHA-based, understands `.sha256sum` companion
  files, raises `ArtifactConflictError`
- **`storage_backend.py`** — `filecmp.cmp` byte comparison, raises `ValueError`

These are independent code paths for different callers:

- `artifact_backend.py` is used by `artifact_manager.py push` (the per-stage
  artifact upload flow)
- `storage_backend.py` is used by log uploads, index generation, and other
  non-artifact file uploads

The `storage_backend.py` conflict check **downloads the full remote file from
S3** for every upload to compare with `filecmp.cmp`. For artifacts this could
mean downloading hundreds of MB just to check. For log uploads, it means every
log file upload now does a HEAD + potential full download.

**Recommendation:** Consider whether `storage_backend.py` changes are needed at
all for this PR. The issue (#4202) is specifically about artifact uploads, which
are handled by `artifact_backend.py`. If `storage_backend.py` conflict
detection is desirable for non-artifact uploads (log files, indices), it should
be:

1. Opt-in (parameter or subclass), not default behavior for all uploads
2. A separate PR with its own justification
3. Using a consistent error type (not `ValueError`)

---

### 3. `storage_backend.py` — 404 detection by string matching

### ⚠️ IMPORTANT: Fragile 404 detection

```python
except Exception as exc:
    exc_str = str(exc).lower()
    if "404" in exc_str or "not found" in exc_str:
        file_exists = False
    else:
        raise
```

boto3 raises `botocore.exceptions.ClientError` for S3 errors, with a
structured response code accessible via `exc.response['Error']['Code']`.
String-matching against the exception message is fragile — it depends on the
error message format, which could change across boto3 versions or differ
across S3-compatible backends.

**Recommendation:** Use the standard boto3 pattern:

```python
from botocore.exceptions import ClientError

try:
    self.s3_client.head_object(Bucket=..., Key=...)
    file_exists = True
except ClientError as e:
    if e.response["Error"]["Code"] == "404":
        file_exists = False
    else:
        raise
```

Note: `artifact_backend.py`'s `artifact_exists()` method may already handle
this correctly — check if it can be reused.

---

### 4. `fileset_tool.py` — Reproducible archives

### ✅ Good: Reproducible archives are essential

The `_normalize_tarinfo` filter and sorted file iteration are necessary for
SHA-based conflict detection to be meaningful. Without these, two jobs
building the same source would produce different tar archives (different
timestamps, different file ordering), so SHA256 would always differ.

The implementation is clean. One minor note: `mtime = 0` means epoch
(1970-01-01), which is fine for reproducibility but could look odd in `tar -t`
output. Not blocking.

---

### 5. `ROCM_BUILD_ID` — Set to `github.sha` in all workflows

### ⚠️ IMPORTANT: ROCM_BUILD_ID embeds into binaries, changing artifact content

`ROCM_BUILD_ID` is consumed by multiple subprojects to embed version/build
info into binaries:

- `ROCMSetupVersion.cmake` appends it to version info
- `rocr-runtime`, `rocdbgapi`, `rocr-debug-agent` embed it as build info
- `rocm-smi-lib`, `amdsmi`, `rocminfo` embed it as version ID

Setting this to `github.sha` means **all artifacts that embed this value will
now have different content than they did before** (when ROCM_BUILD_ID was
unset). This is a behavioral change that goes beyond conflict detection.

Two subprojects (`rocblas`, `rocsolver`) explicitly `unset(ENV{ROCM_BUILD_ID})`
and won't be affected. But others will have new embedded metadata.

**Recommendation:** This change is arguably desirable (consistent build IDs
across jobs), but it has side effects beyond this PR's scope. Consider:

1. Documenting this as a deliberate change, not just a supporting detail
2. Whether this should be a separate PR that stands on its own

---

### 6. Tests

### ❌ BLOCKING: Tautological test

`test_backwards_compat_alias` tests:

```python
def test_backwards_compat_alias(self):
    """Test that ArtifactConflictError is an alias for ArtifactConflictError."""
    self.assertIs(ArtifactConflictError, ArtifactConflictError)
```

This asserts that a class is itself. It can never fail and tests nothing.
Remove it.

### 💡 SUGGESTION: S3Backend conflict tests are heavily mocked

The S3Backend conflict detection tests mock `head_object`, `download_fileobj`,
and `download_file` with custom side effects. This means they test the
*orchestration logic* (which methods get called in which order) rather than the
*conflict detection behavior*. The LocalDirectoryBackend tests are better
because they use real files.

Consider whether the S3 tests could use `moto` (S3 mock server) for more
realistic testing, or at minimum ensure the mock setup is testing behavior
rather than call sequences.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Don't retry `ArtifactConflictError` in `artifact_manager.py` — re-raise immediately
2. Remove tautological `test_backwards_compat_alias`

### ✅ Recommended:

3. Remove or defer `storage_backend.py` conflict detection — it's expensive
   (full file download for every upload), uses a different error type
   (`ValueError` vs `ArtifactConflictError`), and is out of scope for the
   artifact overwrite issue
4. Use structured boto3 error handling (`ClientError.response['Error']['Code']`)
   instead of string matching for 404 detection
5. Consider splitting `ROCM_BUILD_ID` and reproducible archives into a separate
   PR — they're prerequisite work with their own behavioral implications

### 💡 Consider:

6. Whether `_compute_remote_sha256` (downloading full artifact from S3 to
   compute hash) should have a size guard or warning for very large artifacts

### 📋 Future Follow-up:

7. Long-term, the real fix for duplicate generic uploads is either:
   - A designated-uploader mechanism in the push command, or
   - Moving generic artifacts out of per-arch stages where dependency structure allows
8. Conflict detection is defense-in-depth, not the primary solution

---

## Testing Recommendations

```bash
# Run the artifact backend tests
python -m pytest build_tools/tests/artifact_backend_test.py -v

# Run the storage backend tests
python -m pytest build_tools/tests/storage_backend_test.py -v

# Verify reproducible archives: build the same artifact twice, compare hashes
# (requires a local build setup)
```

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The conflict detection approach is the right direction — we discussed this and
agreed that SHA-based dedup at upload time is preferable to filtering or
stage-splitting. The two blocking issues (retry bug, dead test) are
straightforward fixes. The `storage_backend.py` dual-layer question is the
main design decision to resolve.
