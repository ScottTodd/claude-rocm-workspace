# PR Review: Add HTTPBackend for read-only artifact downloads from workflow summary index.html

* **PR:** https://github.com/ROCm/TheRock/pull/4088
* **Author:** PeterCDMcLean
* **Reviewed:** 2026-03-24
* **Status:** OPEN
* **Base:** `main` ← `users/pmclean/workflow_summary_artifact_backend`

---

## Summary

Adds a new `HTTPBackend` class to `artifact_backend.py` that provides read-only access to artifacts hosted on an HTTP server (S3-fronted HTML index pages). The backend parses `index-{gfx_family}.html` files to discover artifacts, downloads them via `urllib.request`, and optionally verifies SHA256 checksums. Also updates `create_backend_from_env()` with a 4-tier priority system: local → S3 w/ credentials → HTTP → S3 w/o credentials.

**Net changes:** +731 lines, -8 lines across 3 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The feature design is sound and fills a real need (HTTP-based read-only artifact access without requiring S3 credentials). However, there are error-handling issues that silently mask failures and could lead to downloading unverified artifacts, plus a docstring/env-var mismatch.

**Strengths:**
- Clean read-only backend with appropriate `NotImplementedError` for write operations
- SHA256 checksum verification is a good security practice
- Artifact list caching avoids redundant HTTP requests
- Priority-based backend selection in `create_backend_from_env()` is well-structured
- Test coverage is thorough with good edge case coverage

**Issues:**
- Error masking in `_download_file` converts all exceptions to `FileNotFoundError`, which causes `download_artifact` to silently skip checksum verification on network errors
- Module docstring references wrong environment variable name
- Manual URL construction duplicates `WorkflowOutputRoot` path logic and breaks for fork repos
- Silent exception swallowing in `_fetch_index` hides real HTTP errors
- AWS credential check requires `AWS_SESSION_TOKEN` which isn't always needed

---

## Detailed Review

### 1. artifact_backend.py — Error handling in `_download_file` / `download_artifact`

#### ❌ BLOCKING: Error type masking causes silent checksum bypass

`_download_file` converts ALL exceptions to `FileNotFoundError`:

```python
def _download_file(self, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception as e:
        raise FileNotFoundError(f"Failed to download {url}: {e}")
```

Then `download_artifact` catches `FileNotFoundError` to allow missing checksums:

```python
try:
    self._download_file(checksum_url, checksum_path)
    if not self._verify_checksum(dest_path):
        ...
        raise ValueError(...)
except FileNotFoundError:
    # Artifacts are allowed to be downloaded without checksums
    pass
```

If downloading the checksum fails for **any** reason (HTTP 500, timeout, connection refused, DNS failure), it's treated as "checksum doesn't exist" and verification is silently skipped. This defeats the purpose of checksum verification.

**Required action:** Either:
1. Don't convert exception types in `_download_file` — let the caller distinguish HTTP 404 (no checksum) from other failures, or
2. Have `_download_file` raise distinct exceptions: one for "resource not found" (404) and another for "download failed" (other HTTP errors, timeouts, etc.), and only catch the "not found" case in `download_artifact`.

Example approach:
```python
def _download_file(self, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(url, dest)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FileNotFoundError(f"Not found: {url}") from e
        raise  # Re-raise other HTTP errors (500, 403, etc.)
    except urllib.error.URLError as e:
        raise ConnectionError(f"Failed to download {url}: {e}") from e
```

Then in `download_artifact`, only catch `FileNotFoundError` (which now genuinely means "doesn't exist").

---

#### ❌ BLOCKING: Module docstring references wrong environment variable

The module docstring says:
```python
- THEROCK_HTTP_RUN_ID set → use HTTPBackend (read-only)
```

But the actual env var used in `create_backend_from_env()` is `THEROCK_HTTP_BASE_URL`.

**Required action:** Update the docstring to match the actual implementation: `THEROCK_HTTP_BASE_URL set → use HTTPBackend (read-only)`.

---

### 2. artifact_backend.py — `_fetch_index` and `list_artifacts` error handling

#### ⚠️ IMPORTANT: Silent exception swallowing hides real errors

`_fetch_index` catches all exceptions and returns empty list:
```python
def _fetch_index(self, gfx_family: str) -> List[str]:
    ...
    except Exception:
        # Index doesn't exist for this target
        return []
```

And `list_artifacts` has another catch around the same call:
```python
for family in self.gfx_families:
    try:
        artifacts = self._fetch_index(family)
        ...
    except Exception:
        continue
```

This double-catch silently swallows all errors. If the server is down, returns malformed HTML, or there's a DNS issue, the user gets an empty artifact list with no indication of why.

**Recommendation:** At minimum, log a warning when `_fetch_index` fails. Better: only catch `urllib.error.HTTPError` with 404 status in `_fetch_index`, and let other errors propagate. Remove the redundant `try/except` in `list_artifacts` since `_fetch_index` already handles the expected case.

---

### 3. artifact_backend.py — HTTPBackend should use WorkflowOutputRoot for path construction

#### ❌ BLOCKING: Manual URL construction duplicates path logic and breaks for forks

HTTPBackend constructs URLs manually:

```python
@property
def base_uri(self) -> str:
    return f"{self.base_url}/{self.run_id}-{self.platform}"

def _fetch_index(self, gfx_family: str) -> List[str]:
    index_url = f"{self.base_uri}/index-{gfx_family}.html"
```

The other two backends (`S3Backend`, `LocalDirectoryBackend`) delegate path construction to `WorkflowOutputRoot`, which is the single source of truth for the CI output layout (see `docs/development/workflow_outputs.md`). HTTPBackend should do the same.

**Problems with the manual approach:**

1. **Fork support is broken.** `WorkflowOutputRoot.prefix` includes `external_repo` for forks (e.g., `owner-repo/12345-linux`). The manual `{run_id}-{platform}` construction produces `12345-linux`, missing the fork prefix entirely.
2. **Index path is duplicated.** `WorkflowOutputRoot.artifact_index(group)` already knows the `index-{group}.html` pattern. If the pattern ever changes, HTTPBackend would need a manual update.
3. **Artifact path is duplicated.** `WorkflowOutputRoot.artifact(filename)` already computes `{prefix}/{filename}`.
4. **HTTPS URLs exist already.** `StorageLocation.https_url` produces `https://{bucket}.s3.amazonaws.com/{relative_path}` for the public S3 case.

**Required action:** Refactor HTTPBackend to take a `WorkflowOutputRoot` (like the other backends) plus an optional base URL override for non-S3 hosts. Use a `_url_for()` helper to resolve `StorageLocation` → URL, supporting both modes:

```python
class HTTPBackend(ArtifactBackend):
    def __init__(
        self,
        output_root: WorkflowOutputRoot,
        gfx_families: List[str],
        base_url: Optional[str] = None,
    ):
        self.output_root = output_root
        self.gfx_families = gfx_families
        # None → use StorageLocation.https_url (public S3)
        # Set → use {base_url}/{relative_path} (internal/custom server)
        self._base_url = base_url
        self._artifact_cache: Optional[List[str]] = None

    def _url_for(self, location: StorageLocation) -> str:
        """Resolve a StorageLocation to an HTTP URL.

        When base_url is set, constructs {base_url}/{location.relative_path}.
        Otherwise falls back to StorageLocation.https_url (the public S3 URL).
        """
        if self._base_url:
            return f"{self._base_url}/{location.relative_path}"
        return location.https_url

    @property
    def base_uri(self) -> str:
        return self._url_for(self.output_root.root())

    def _fetch_index(self, gfx_family: str) -> List[str]:
        index_url = self._url_for(self.output_root.artifact_index(gfx_family))
        # ... same fetch logic ...

    def download_artifact(self, artifact_key: str, dest_path: Path) -> None:
        artifact_url = self._url_for(self.output_root.artifact(artifact_key))
        checksum_url = self._url_for(
            self.output_root.artifact(f"{artifact_key}.sha256sum")
        )
        # ... same download logic ...

    def artifact_exists(self, artifact_key: str) -> bool:
        # ... cache check same as now ...
        artifact_url = self._url_for(self.output_root.artifact(artifact_key))
        # ... HEAD request same as now ...
```

And in `create_backend_from_env()`, construct the `WorkflowOutputRoot` the same way as for S3:

```python
# Priority 3: HTTP backend
http_base_url = os.getenv("THEROCK_HTTP_BASE_URL")
if http_base_url:
    output_root = WorkflowOutputRoot.from_workflow_run(
        run_id=run_id, platform=platform_name
    )
    return HTTPBackend(
        output_root=output_root,
        gfx_families=targets,
        base_url=http_base_url,
    )
```

This supports both use cases:
- **Public S3 artifacts** (no `base_url`): Uses `StorageLocation.https_url` → `https://therock-ci-artifacts.s3.amazonaws.com/12345-linux/blas_lib_gfx94X.tar.zst`
- **Internal/custom servers** (`base_url` set): Uses `{base_url}/{relative_path}` → `https://internal.example.com/artifacts/12345-linux/blas_lib_gfx94X.tar.zst`

Both modes get fork prefixes, bucket selection, and all path logic for free via `WorkflowOutputRoot`.

---

### 4. artifact_backend.py — `create_backend_from_env()` credential check

#### ⚠️ IMPORTANT: AWS credential check is overly restrictive (may be partially addressed by #3)

```python
has_s3_credentials = all(
    os.getenv(var)
    for var in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]
)
```

`AWS_SESSION_TOKEN` is only present for temporary credentials (STS assume-role). Long-term IAM credentials only have `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`. Requiring all three means environments with long-term credentials and `THEROCK_HTTP_BASE_URL` set would incorrectly get the HTTP backend instead of S3.

Additionally, boto3 supports other credential sources (config files, IAM roles, EC2 instance profiles) that don't set any of these env vars. Someone using those with `THEROCK_HTTP_BASE_URL` set would also get HTTP instead of S3.

**Recommendation:** Consider whether the intent is "prefer HTTP when no *explicit* env-var credentials" (current behavior, approximately) or "prefer HTTP when boto3 can't find any credentials" (would require actually checking `boto3.Session().get_credentials()`). If the current approach is intentional for simplicity, at minimum drop the `AWS_SESSION_TOKEN` requirement:
```python
has_s3_credentials = all(
    os.getenv(var)
    for var in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
)
```

---

### 4. artifact_backend.py — Dead stub method

#### 💡 SUGGESTION: Remove or minimize `_discover_gfx_families_from_master_index`

This method is ~40 lines of commented-out code that just returns `[]`. It's never called. The TODO in the docstring is useful context, but the commented-out implementation is noise.

**Recommendation:** Either remove the method entirely and leave a `# TODO:` comment where it would be called, or trim it to just the docstring + `return []` without the commented-out implementation.

---

### 5. artifact_backend.py — `_verify_checksum` return semantics

#### 💡 SUGGESTION: Clarify `_verify_checksum` return value meaning

`_verify_checksum` returns `False` for both "checksum file doesn't exist" and "checksum mismatch". The caller needs to distinguish these cases but can't from the return value alone. Currently the caller pre-checks by catching `FileNotFoundError` from the download, but this is fragile (see BLOCKING issue #1).

**Recommendation:** Consider raising an exception on mismatch and returning `None`/`False` only for "no checksum available", or just always raise if the checksum file exists but doesn't match (the current behavior works, but would be clearer).

---

### 6. Tests

#### 💡 SUGGESTION: Test for `_download_file` error handling after fix

Once the error-masking issue in `_download_file` is fixed, add a test that verifies:
- HTTP 404 for checksum → download succeeds without verification (current behavior)
- HTTP 500 for checksum → download fails with an appropriate error (not silently accepted)
- Network timeout for checksum → download fails with an appropriate error

The existing `test_download_artifact_without_checksum` only tests the happy path of "checksum not found" but doesn't distinguish 404 from other failures.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Fix error type masking in `_download_file` — distinguish 404 from other HTTP/network errors so checksum verification isn't silently bypassed on transient failures
2. Fix module docstring: `THEROCK_HTTP_RUN_ID` → `THEROCK_HTTP_BASE_URL`
3. Use `WorkflowOutputRoot` for path construction instead of manual URL assembly — fixes fork support and eliminates duplicated path logic

### ✅ Recommended:

1. Fix AWS credential check — at minimum drop `AWS_SESSION_TOKEN` requirement
2. Improve error handling in `_fetch_index` — catch specific exceptions, log warnings for unexpected failures, remove redundant try/except in `list_artifacts`

### 💡 Consider:

1. Remove or trim `_discover_gfx_families_from_master_index` dead code
2. Clarify `_verify_checksum` semantics
3. Add tests for error-type-specific behavior in checksum download

---

## Testing Recommendations

- Run existing tests: `python -m pytest build_tools/tests/artifact_backend_test.py -v`
- After fixing error handling, add test for HTTP 500 during checksum download → should not silently skip verification
- Manual test: verify the backend works with a real workflow summary URL (as described in PR description)

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The HTTPBackend is a useful addition. The two blocking issues are straightforward to fix: update the docstring, and refine the error handling in `_download_file` to preserve error semantics so that checksum verification isn't silently skipped on network errors. The other recommendations are lower priority but would improve robustness.
