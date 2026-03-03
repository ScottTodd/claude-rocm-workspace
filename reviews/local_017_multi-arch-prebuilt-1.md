# Branch Review: multi-arch-prebuilt-1 (Post-Refactor)

* **Branch:** `multi-arch-prebuilt-1`
* **Base:** `main`
* **Reviewed:** 2026-03-03
* **Commits:** 5 commits (copy subcommand + refactoring)
  - `27eb74a0` Add artifact_manager.py copy subcommand for S3-to-S3 artifact copying
  - `d57b4871` Add runtime type checks to copy_artifact backends
  - `b894b27d` Pre-filter sha256sum files in copy command to avoid noisy retries
  - `7e01ef8f` Extract shared helpers for fetch/copy: target families, artifact enumeration, argparse
  - `453c605b` Support comma-separated stages in copy command
* **Previous review:** `local_016_multi-arch-prebuilt-1.md` (pre-refactor)

---

## Summary

Adds a `copy` subcommand to `artifact_manager.py` for server-side S3 copy of produced artifacts between workflow runs. Supports local directory copy for testing. Includes shared helper extraction (addressing findings from the previous review), comma-separated multi-stage support, and sha256sum pre-filtering.

**Net changes:** +358 lines in `artifact_manager.py`, +40 in `artifact_backend.py`, +280 in artifact_manager tests, +124 in backend tests

---

## Overall Assessment

**✅ APPROVED** - Clean implementation with good test coverage. The refactoring from the previous review has been addressed appropriately. Remaining duplication (retry logic, backend creation) is deliberately deferred to avoid conflicting with the `run-outputs-layout` / `StorageBackend` work.

**Strengths:**

- S3 server-side copy via `s3_client.copy()` — no download/upload round-trip
- Shared helpers (`parse_target_families`, `find_available_artifacts`, `_add_target_args`, `ARTIFACT_COMPONENTS`) effectively deduplicate fetch/copy code
- sha256sum pre-filter using `artifact_exists()` avoids noisy retries for missing files
- Comma-separated `--stage` pushes complexity into the script, keeping workflow YAML simple
- Good test coverage (10 new copy tests + 6 backend tests) covering happy path, failure, dry-run, multi-stage, sha256sum, and argparse validation

**Issues:**

- Minor items only — see below

---

## Detailed Review

### 1. `_create_source_backend` vs `create_backend_from_env`

**💡 SUGGESTION: Partial duplication between source and dest backend creation**

`_create_source_backend` (lines 753-786) and `create_backend_from_env` (in `artifact_backend.py`) share the same structure: check for local staging dir, create `LocalDirectoryBackend` or `S3Backend`. The key difference is that the source version passes `workflow_run_id` to `retrieve_bucket_info()`.

This was noted in the previous review. The decision to defer is sound — the `run-outputs-layout` work is adding `StorageBackend` which will likely subsume both. No action needed now, just noting it's still present.

### 2. Retry logic still duplicated across download/upload/copy

**💡 SUGGESTION: Three near-identical retry loops**

`download_artifact`, `upload_artifact`, and `copy_single_artifact` all follow the same MAX_RETRIES=3, BASE_DELAY_SECONDS=2, exponential backoff pattern. This was noted in the previous review and explicitly deferred.

Deferral is reasonable — these three functions have subtly different return types (`Optional[Path]` vs `bool`) and error handling (`FileNotFoundError` special case in download). A unified retry helper would need to accommodate these differences.

### 3. `do_copy` uses `sys.exit(1)` for errors

**💡 SUGGESTION: `sys.exit(1)` vs exceptions for error handling**

`do_copy` (and `do_fetch`, `do_push`) use `sys.exit(1)` for error conditions. This was discussed during the session and explicitly deferred to a follow-up PR to clean up all commands consistently.

### 4. `getattr(args, "local_staging_dir", None)` in `do_copy`

**💡 SUGGESTION: Defensive attribute access**

Line 821 uses `getattr(args, "local_staging_dir", None)` even though `copy_parser` uses `_add_backend_args` which includes `--local-staging-dir`. The attribute will always exist on `args`. Using `args.local_staging_dir` directly would be cleaner and consistent with how `do_fetch` and `do_push` access it.

This is minor — the `getattr` form is not wrong, just unnecessarily defensive.

### 5. `sha256sum_requests` existence check is sequential

**💡 SUGGESTION: Sequential `artifact_exists()` calls for sha256sum pre-filtering**

Lines 887-891 call `source_backend.artifact_exists()` sequentially for each sha256sum file. For S3 backends, each call is a `head_object` API call. With many artifacts, this could be slow.

For the initial implementation this is fine — the main artifact copy is parallel, and sha256sum is best-effort. If this becomes a bottleneck, the existence checks could be parallelized with a thread pool. Not worth complicating now.

### 6. Test topology expanded appropriately

The test topology now includes `second-upstream-stage` and `second-artifact`, which enables the `test_copy_multiple_stages` test. The downstream-stage correctly depends on both upstream groups. The topology expansion is minimal and well-structured.

### 7. Help text for `--stage` in `copy` vs `fetch`

**💡 SUGGESTION: Inconsistent `--stage` help text**

`copy_parser --stage` help says "Build stage name(s), comma-separated" while `fetch_parser --stage` says "Build stage name (default: 'all' fetches all artifacts)". This is fine — they have different semantics (copy accepts comma-separated, fetch accepts "all"). Just noting the asymmetry for awareness.

---

## Status of Previous Review Findings

| Finding | Status |
|---------|--------|
| Duplicated artifact enumeration pattern | ✅ Fixed — `find_available_artifacts()` |
| Duplicated target family parsing | ✅ Fixed — `parse_target_families()` |
| Duplicated retry logic | Deferred — `run-outputs-layout` work |
| Duplicated argparse definitions | ✅ Fixed — `_add_target_args()` |
| `_create_source_backend` duplication | Deferred — `run-outputs-layout` work |
| Stage validation boilerplate | Deferred — follow-up PR |
| `copy_artifact` type signature | Acknowledged — known limitation |
| `components` list duplicated | ✅ Fixed — `ARTIFACT_COMPONENTS` constant |

---

## Recommendations

### ❌ REQUIRED (Blocking):

None.

### ✅ Recommended:

None — all recommended items from the previous review have been addressed or explicitly deferred with rationale.

### 💡 Consider:

1. Replace `getattr(args, "local_staging_dir", None)` with `args.local_staging_dir` in `do_copy`
2. Parallelize sha256sum existence checks if performance becomes an issue

### 📋 Future Follow-up:

1. Unify retry logic across download/upload/copy (after `StorageBackend` work settles)
2. Merge `_create_source_backend` into `create_backend_from_env` (after `run-outputs-layout`)
3. Replace `sys.exit(1)` with exceptions across all commands (separate PR)
4. Cross-backend `copy_artifact` support (e.g., S3→Local for mirror scenarios)

---

## Testing

53 tests pass (21 artifact_manager + 32 artifact_backend):
- 10 copy-specific tests covering: basic transfer, sha256sum, multiple components, stage filtering, dry-run, failure handling, invalid stage, missing args, multi-stage
- 6 backend copy tests: local-to-local, nonexistent source, wrong backend type, S3 same-bucket, S3 cross-bucket, S3 wrong type

Test coverage for the copy path is good. Edge cases tested include:
- Comma-separated stage validation (invalid stage in list)
- sha256sum files present and absent in source
- Backend type mismatches (TypeError)
- Dry-run mode (no side effects)

---

## Conclusion

**Approval Status: ✅ APPROVED**

The branch is ready for PR. The copy subcommand is correct, well-tested, and the shared helper extraction addresses the main duplication concerns from the previous review. Remaining duplication is deliberately scoped out to avoid conflicts with in-flight storage backend work.
