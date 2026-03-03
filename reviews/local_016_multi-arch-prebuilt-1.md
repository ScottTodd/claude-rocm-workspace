# Branch Review: multi-arch-prebuilt-1

* **Branch:** `multi-arch-prebuilt-1`
* **Base:** `main`
* **Reviewed:** 2026-03-03
* **Commits:** 3 commits (copy subcommand only; excludes artifact-finding commits)
  - `27eb74a0` Add artifact_manager.py copy subcommand for S3-to-S3 artifact copying
  - `d57b4871` Add runtime type checks to copy_artifact backends
  - `b894b27d` Pre-filter sha256sum files in copy command to avoid noisy retries

---

## Summary

Adds an `artifact_manager.py copy` subcommand that copies all produced artifacts for a build stage from one workflow run to another. Supports S3 server-side copy (no download round-trip) and local directory copy. Includes parallel execution, dry-run mode, and best-effort sha256sum handling.

**Net changes:** +254 lines in `artifact_manager.py`, +40 in `artifact_backend.py`, +238 in tests, +124 in backend tests

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** - Solid implementation with good test coverage, but there's significant code duplication across the fetch/push/copy commands that should be addressed before this grows further.

**Strengths:**

- S3 server-side copy via `s3_client.copy()` — no download/upload round-trip
- sha256sum pre-filter using `artifact_exists()` is a clean fix
- Good test coverage (12 new tests) including cross-bucket, failure, and dry-run scenarios
- `_create_source_backend` correctly handles bucket resolution for cross-repo scenarios

**Issues:**

- Duplicated patterns across fetch/push/copy (artifact enumeration, retry logic, target family parsing, argparse definitions)
- `_create_source_backend` partially duplicates `create_backend_from_env`

---

## Detailed Review

### 1. Duplicated artifact enumeration pattern

**⚠️ IMPORTANT: Three copies of the "artifacts × families × components × extensions" loop**

The same nested loop pattern appears in:
- `do_fetch` (lines 319-333): builds `download_requests`
- `do_copy` (lines 814-836): builds `copy_requests` + `sha256sum_requests`
- `do_push` doesn't use it (it scans the build dir), but shares the `components` list

Both `do_fetch` and `do_copy` iterate `sorted(artifact_names) × target_families × components × extensions`, check `if filename in available`, and `break` on first extension match. The only difference is what request type they construct.

**Recommendation:** Extract an `enumerate_available_artifacts(artifact_names, target_families, available)` helper that yields `(artifact_name, component, target_family, filename)` tuples. Each command builds its own request type from the tuples.

### 2. Duplicated target family parsing

**⚠️ IMPORTANT: Target family parsing duplicated between do_fetch and do_copy**

Lines 289-298 (`do_fetch`) and lines 779-788 (`do_copy`) are nearly identical:

```python
target_families = ["generic"]
if args.generic_only:
    log("... generic (host) artifacts only")
else:
    if args.amdgpu_families:
        target_families.extend(args.amdgpu_families.split(","))
    if args.amdgpu_targets:
        target_families.extend(
            t.strip() for t in args.amdgpu_targets.split(",") if t.strip()
        )
```

**Recommendation:** Extract `parse_target_families(args) -> List[str]`.

### 3. Duplicated retry logic

**⚠️ IMPORTANT: Three near-identical retry loops**

- `download_artifact` (lines 150-174)
- `upload_artifact` (lines 501-531)
- `copy_single_artifact` (lines 697-719)

All follow the same pattern: MAX_RETRIES=3, BASE_DELAY_SECONDS=2, exponential backoff, log retry/failure. The only differences are:
- The operation name in log messages ("Downloading"/"Uploading"/"Copying")
- `download_artifact` returns `Optional[Path]` and handles `FileNotFoundError` specially
- `upload_artifact` and `copy_single_artifact` return `bool`

**Recommendation:** Extract a `with_retry(operation_name, fn, *args)` helper or decorator. The `download_artifact` special case (FileNotFoundError → None) could be handled via a callback or by keeping that one function separate.

### 4. Duplicated argparse definitions for target arguments

**💡 SUGGESTION: Factor out shared argparse argument groups**

The `--amdgpu-families` / `--generic-only` / `--amdgpu-targets` mutually-exclusive group is defined identically for both `fetch_parser` (lines 1010-1026) and `copy_parser` (lines 1119-1135). The help text even has the same wording.

**Recommendation:** Extract `_add_target_args(parser)` alongside the existing `_add_backend_args`. This is a natural extension of the existing pattern.

### 5. `_create_source_backend` partially duplicates `create_backend_from_env`

**⚠️ IMPORTANT: Two functions that create backends from similar inputs**

`_create_source_backend` (lines 722-755) and `create_backend_from_env` (in `artifact_backend.py`) both:
- Check `THEROCK_LOCAL_STAGING_DIR` to decide local vs S3
- Create `LocalDirectoryBackend` with same args
- Resolve bucket info for S3

The key difference is that `_create_source_backend` calls `retrieve_bucket_info(workflow_run_id=source_run_id)` to resolve the *source* run's bucket, while `create_backend_from_env` calls `retrieve_bucket_info()` without a run ID (uses current run's context).

**Recommendation:** Consider adding an optional `workflow_run_id` parameter to `create_backend_from_env` instead of having a separate function. The local path is identical; only the S3 bucket resolution differs.

### 6. Stage validation boilerplate

**💡 SUGGESTION: Repeated stage validation pattern**

Three functions (`do_fetch`, `do_push`, `do_copy`) all start with:
```python
if args.stage not in topology.build_stages:
    log(f"ERROR: Stage '{args.stage}' not found")
    log(f"Available stages: {', '.join(topology.build_stages.keys())}")
    sys.exit(1)
```

This is minor, but a `validate_stage(topology, stage_name)` helper would reduce the boilerplate. `do_fetch` has the extra `"all"` case but could call the helper for non-"all" stages.

### 7. copy_artifact type signature vs isinstance check

**💡 SUGGESTION: Type annotation says `ArtifactBackend` but body requires same type**

In `artifact_backend.py`, both `LocalDirectoryBackend.copy_artifact` and `S3Backend.copy_artifact` declare `source_backend: "LocalDirectoryBackend"` / `source_backend: "S3Backend"` in their signatures, but the abstract base declares `source_backend: "ArtifactBackend"`. The runtime `isinstance` check enforces same-type.

This is functional but the mixed signals between the type annotation and runtime check could confuse readers. The abstract base says "any backend" but the implementations reject cross-type.

No action needed right now — this is a known limitation documented in the task file. Just noting it for the record.

### 8. `components` list defined twice

**💡 SUGGESTION: Components list duplicated**

The `components = ["lib", "run", "dev", "dbg", "doc", "test"]` list appears in both `do_fetch` (line 316) and `do_copy` (line 809). Could be a module-level constant.

---

## Recommendations

### ❌ REQUIRED (Blocking):

None — the code is correct and well-tested. The duplication issues are important but not blocking for an initial implementation.

### ✅ Recommended:

1. Extract `enumerate_available_artifacts()` helper to deduplicate the artifact enumeration loop between fetch and copy
2. Extract `parse_target_families(args)` to deduplicate target family parsing
3. Consider merging `_create_source_backend` into `create_backend_from_env` with an optional `workflow_run_id` parameter
4. Extract shared retry logic (at least between `upload_artifact` and `copy_single_artifact` which have identical structure)

### 💡 Consider:

1. Factor out `_add_target_args(parser)` for shared argparse argument groups
2. Module-level `ARTIFACT_COMPONENTS` constant
3. Stage validation helper

### 📋 Future Follow-up:

1. `copy_artifact` cross-backend support (e.g., S3→Local for the "mirror to local staging" use case discussed earlier)
2. Integration with `run-outputs-layout` work for cleaner local backend paths

---

## Testing Recommendations

The existing 12 tests cover the main scenarios well. Additional tests to consider:

- Test `parse_target_families` extraction (if done) with edge cases (empty strings, whitespace)
- Test `enumerate_available_artifacts` helper (if done) with mixed extensions (.tar.zst and .tar.xz in same source)

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The implementation is correct and functional. The main concern is code duplication that will compound as more commands are added or existing ones are modified. The recommended extractions (artifact enumeration, target family parsing, retry logic, backend creation) are all mechanical refactors that would reduce the copy command from ~130 lines to ~60-70 lines while making fetch and push shorter too.

Suggest addressing the "Recommended" items before sending as PR, since this code will be the foundation for the workflow integration in Phase 1.
