# PR Review: Add HTTPBackend for read-only artifact downloads

* **PR:** https://github.com/ROCm/TheRock/pull/4088
* **Stacked PR:** https://github.com/ROCm/TheRock/pull/4167 (schema approach — we recommend against)
* **Author:** PeterCDMcLean
* **Reviewed:** 2026-03-24, updated 2026-03-26
* **Status:** OPEN
* **Base:** `main` ← `users/pmclean/workflow_summary_artifact_backend`

---

## Summary

Adds a new `HTTPBackend` class to `artifact_backend.py` that provides read-only
access to artifacts via HTTP downloads (public S3 URLs or CDN). The backend
parses `index-{gfx_family}.html` files to discover artifacts, downloads via
`urllib.request`, and optionally verifies SHA256 checksums. Also updates
`create_backend_from_env()` with a 3-tier priority system: local → S3 (with
credentials) → HTTP.

**Net changes:** ~+700 lines across 5 files (artifact_backend.py, storage_location.py, artifact_manager.py, tests, docs)

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The feature design is sound and fills a real need.
Peter addressed several items from our first review (error handling in
`_download_file`, AWS credential check, WorkflowOutputRoot integration). The
remaining issue is how URL customization is handled — the `THEROCK_HTTPS_URL_`
env var approach in this PR and the template/schema approach in stacked PR #4167
both have problems. We propose a simpler alternative below.

**What's good (improvements since first review):**
- HTTPBackend now uses `WorkflowOutputRoot` for path construction (was our blocking #3)
- `_download_file` now distinguishes HTTP 404/403 from other errors (was our blocking #1)
- AWS credential check only requires `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` (was our recommended fix)
- Clean read-only backend with appropriate `NotImplementedError` for write operations
- SHA256 checksum verification with correct error handling
- Artifact list caching avoids redundant HTTP requests
- Test coverage is thorough

**What needs to change:**
- Remove the `THEROCK_HTTPS_URL_<bucket>` env var override from `StorageLocation` — it
  conflates path computation with deployment configuration
- Add a `base_url` parameter to `HTTPBackend` instead (see detailed design below)
- Error handling in `_fetch_index` still silently swallows all exceptions

---

## Design Direction: `base_url` on HTTPBackend

### The problem

Internal builds and CDN-fronted buckets need customizable HTTPS URLs. Two
approaches have been proposed:

1. **This PR (#4088):** `THEROCK_HTTPS_URL_<bucket>` env vars on `StorageLocation`
2. **Stacked PR (#4167):** `s3_url_schema` / `https_url_schema` / `bucket_schema`
   template parameters threaded through `StorageLocation`, `WorkflowOutputRoot`,
   `create_backend_from_env()`, and CLI args

Both have problems. We propose a third approach.

### Design constraints

**CDN URLs don't follow bucket-derived patterns.** From `docs/development/s3_buckets.md`:

| Bucket | S3 URL | CDN URL |
|--------|--------|---------|
| `therock-dev-python` | `https://therock-dev-python.s3.amazonaws.com/{path}` | `https://rocm.devreleases.amd.com/v2/{path}` |
| `therock-nightly-tarball` | `https://therock-nightly-tarball.s3.amazonaws.com/{path}` | `https://rocm.nightlies.amd.com/tarball/{path}` |

The CDN domain (`rocm.devreleases.amd.com`) and path prefix (`/v2/`) bear no
relationship to the bucket name. A template with `{bucket}` and `{path}`
placeholders (as in #4167) cannot express these URLs. If artifact buckets ever
get CDN fronting (like the python/packages/tarball buckets already have), the
template approach would need to be replaced.

**Who actually consumes custom HTTPS URLs?**

| Consumer | Uses `s3_uri` | Uses `https_url` | Uses bucket directly |
|----------|:---:|:---:|:---:|
| **S3Backend** (boto3 API) | No (uses bucket+key) | No | Yes |
| **S3Backend.base_uri** (logging) | Yes (display only) | No | — |
| **HTTPBackend** | No | **Yes (downloads)** | No |
| **StorageBackend** (upload) | Yes (AWS CLI) | No | — |
| **Workflow summary HTML** | No | **Yes (links)** | — |

Only HTTPBackend and workflow summary HTML use HTTPS URLs. Neither needs
customization baked into every `StorageLocation` instance.

### Why #4088's env var approach is wrong

`THEROCK_HTTPS_URL_<bucket>` puts deployment configuration inside
`StorageLocation`, which is meant to be a pure value type (bucket + path).
Problems:

- **Spooky action at a distance:** `StorageLocation("my-bucket", "path").https_url`
  returns different values depending on which env vars happen to be set. This makes
  the type non-deterministic and hard to test.
- **Wrong scope:** Every `StorageLocation` in the process gets the override, even
  ones that have nothing to do with HTTP downloads.
- **Doesn't compose:** If two different consumers need different base URLs for the
  same bucket (e.g., CDN for downloads, S3 for summary links), env vars can't
  express that.

### Why #4167's schema approach is wrong

Threading `s3_url_schema` and `https_url_schema` through `StorageLocation`,
`WorkflowOutputRoot`, `create_backend_from_env()`, and CLI args:

- **+280 lines of boilerplate:** Every `StorageLocation` construction in
  `WorkflowOutputRoot` (~13 sites) must pass both schemas. Every new method that
  returns a `StorageLocation` must do the same.
- **Can't express CDN URLs:** Templates use `{bucket}` and `{path}` placeholders,
  but CDN URLs like `https://rocm.devreleases.amd.com/v2/{path}` have no
  relationship to the bucket name.
- **Solves a problem that doesn't exist:** The `s3_url_schema` customization has
  almost no consumers — only `base_uri` display and `storage_backend.py` uploads,
  neither of which needs customization.

### Recommended approach: `base_url` on HTTPBackend

Keep `StorageLocation` clean. Each consumer that needs URL customization handles
it locally.

```python
# StorageLocation stays unchanged from main — no env var lookup, no schema fields
@dataclass(frozen=True)
class StorageLocation:
    bucket: str
    relative_path: str

    @property
    def s3_uri(self) -> str:
        return f"s3://{self.bucket}/{self.relative_path}"

    @property
    def https_url(self) -> str:
        return f"https://{self.bucket}.s3.amazonaws.com/{self.relative_path}"
```

```python
class HTTPBackend(ArtifactBackend):
    def __init__(
        self,
        output_root: WorkflowOutputRoot,
        gfx_families: list[str],
        base_url: str | None = None,
    ):
        self.output_root = output_root
        self.gfx_families = gfx_families
        # None → use StorageLocation.https_url (public S3)
        # Set  → use {base_url}/{relative_path} (CDN, internal server, etc.)
        self._base_url = base_url
        self._artifact_cache: Optional[list[str]] = None

    def _url_for(self, loc: StorageLocation) -> str:
        """Resolve a StorageLocation to an HTTP URL."""
        if self._base_url:
            return f"{self._base_url.rstrip('/')}/{loc.relative_path}"
        return loc.https_url

    @property
    def base_uri(self) -> str:
        return self._url_for(self.output_root.root())

    def _fetch_index(self, gfx_family: str) -> list[str]:
        index_url = self._url_for(self.output_root.artifact_index(gfx_family))
        # ... same fetch logic ...

    def download_artifact(self, artifact_key: str, dest_path: Path) -> None:
        artifact_url = self._url_for(self.output_root.artifact(artifact_key))
        checksum_url = self._url_for(
            self.output_root.artifact(f"{artifact_key}.sha256sum")
        )
        # ... same download logic ...
```

```python
# In create_backend_from_env():
http_base_url = os.getenv("THEROCK_HTTP_BASE_URL")  # optional CDN/custom URL
# ...
output_root = WorkflowOutputRoot.from_workflow_run(run_id=run_id, platform=platform_name)
return HTTPBackend(output_root=output_root, gfx_families=targets, base_url=http_base_url)
```

**CLI surface is one arg, not three:**
```bash
# Default (public S3 URLs)
python artifact_manager.py fetch --stage math-libs

# CDN or custom server
python artifact_manager.py fetch --stage math-libs \
    --http-base-url "https://rocm.devreleases.amd.com/artifacts"
```

**This supports all use cases:**
- **Public S3 artifacts** (no `base_url`): Uses `StorageLocation.https_url` →
  `https://therock-ci-artifacts.s3.amazonaws.com/12345-linux/blas_lib_gfx94X.tar.zst`
- **CDN-fronted artifacts** (`base_url` set): Uses `{base_url}/{relative_path}` →
  `https://rocm.devreleases.amd.com/artifacts/12345-linux/blas_lib_gfx94X.tar.zst`
- **Internal/custom servers**: Same mechanism with internal URL

**If `post_build_upload.py` needs custom HTTPS URLs for summary links**, that's a
separate `--https-base-url` arg on that script — it can compute
`{base_url}/{loc.relative_path}` when generating HTML without modifying
`StorageLocation`.

### Alternatives considered

#### Alt 1: `bucket_override` with default mapping

Add a single `bucket_override` option with a mapping from bucket name to URL
patterns, plus a way to inject additional mappings for internal builds.

**Rejected because:** It conflates two independent concerns (bucket naming and URL
patterns). The bucket name is already configurable via `RELEASE_TYPE` and
`_retrieve_bucket_info()`. The mapping indirection adds complexity without
eliminating the core problem — and still can't express CDN URLs where the domain
has no relationship to the bucket name.

#### Alt 2: `bucket_schema` for bucket naming

Add a `bucket_schema` template (e.g., `"mycompany-{release_type}-builds"`) to
`_retrieve_bucket_info()` for internal builds with different bucket naming.

**Deferred:** This could be useful but isn't needed for the HTTPBackend feature.
Internal builds that use different bucket names can already override via
`RELEASE_TYPE` or by calling `WorkflowOutputRoot` directly with a custom bucket.
If needed later, it's a one-parameter, one-call-site change to
`_retrieve_bucket_info()` — low risk to add incrementally.

---

## Remaining Issues in #4088

### 1. StorageLocation — Remove env var override

#### ❌ BLOCKING: Remove `THEROCK_HTTPS_URL_<bucket>` from `StorageLocation`

As discussed above, revert `storage_location.py` to the clean version on `main`
(no `os` import, no env var lookup in `https_url`). The `base_url` parameter on
`HTTPBackend._url_for()` replaces this functionality.

Also remove the `THEROCK_HTTPS_URL_` tests from `workflow_outputs_test.py` and
the "HTTPS URL Override" section from `workflow_outputs.md`.

---

### 2. artifact_backend.py — `_fetch_index` error handling

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

If the server is down, returns malformed HTML, or there's a DNS issue, the user
gets an empty artifact list with no indication of why.

**Recommendation:** In `_fetch_index`, only catch `urllib.error.HTTPError` with
404 status and let other errors propagate. Remove the redundant `try/except` in
`list_artifacts`.

---

### 3. artifact_backend.py — Dead stub method

#### 💡 SUGGESTION: Remove or trim `_discover_gfx_families_from_master_index`

~40 lines of commented-out code that returns `[]`. The TODO is useful context but
the commented-out implementation is noise. Trim to docstring + `return []`, or
remove entirely and leave a `# TODO:` where it would be called.

---

### 4. Module docstring

#### 💡 SUGGESTION: Update environment-based switching docs

The module docstring now lists the 3-tier priority correctly. One nit: the
comment says "THEROCK_AMDGPU_FAMILIES set → use HTTPBackend" but the actual
trigger is "no S3 credentials AND (gfx_families param OR THEROCK_AMDGPU_FAMILIES
env)". The docstring should clarify this is the fallback when S3 credentials
aren't present.

---

## Summary of Requested Changes

### ❌ REQUIRED (Blocking):

1. **Revert `StorageLocation` to main** — remove env var override, keep it a
   clean value type
2. **Add `base_url` parameter to `HTTPBackend`** with `_url_for()` helper —
   this is where URL customization belongs
3. **Add `--http-base-url` CLI arg** (or `THEROCK_HTTP_BASE_URL` env var) to
   `artifact_manager.py` — single point of configuration
4. **Drop stacked PR #4167** — the schema/template approach is unnecessary

### ✅ Recommended:

1. Fix error handling in `_fetch_index` — catch specific HTTP exceptions
2. Remove redundant `try/except` in `list_artifacts`

### 💡 Consider:

1. Trim `_discover_gfx_families_from_master_index` dead code
2. Clarify module docstring for HTTPBackend trigger conditions

---

## Testing Recommendations

- Run existing tests: `python -m pytest build_tools/tests/artifact_backend_test.py -v`
- After adding `base_url`, add tests for:
  - `base_url=None` → URLs use `StorageLocation.https_url` (S3 pattern)
  - `base_url="https://cdn.example.com"` → URLs use `{base_url}/{relative_path}`
  - `base_url` with trailing slash → handled correctly
- After fixing `_fetch_index` error handling, add test for HTTP 500 → propagates error (not silently empty)

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The HTTPBackend is useful — it's the natural way to consume artifacts without S3
credentials, and positions well for CDN-fronted artifact buckets. The main change
needed is moving URL customization from `StorageLocation` (where it doesn't
belong) to `HTTPBackend._url_for()` (where it does). This is a simpler, smaller
change than either the env var approach or the schema approach, and it's the only
one that can express CDN URLs.
