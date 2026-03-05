# Branch Review: multi-arch-prebuilt-1

* **Branch:** `multi-arch-prebuilt-1`
* **Base:** `upstream/main`
* **Reviewed:** 2026-03-05
* **Commits:** 6 branch-specific commits (+ merge commit + upstream commits)

---

## Summary

Adds an `artifact_manager.py copy` subcommand that copies build artifacts
between workflow runs using S3 server-side copy. This enables the multi-arch
CI pipeline to skip rebuilding stages by copying their artifacts from a
baseline run. Also refactors shared helpers (`parse_target_families`,
`find_available_artifacts`, `_add_target_args`) out of the existing fetch
code so they can be reused by copy.

**Net changes:** +765 lines, -49 lines across 4 files

---

## Overall Assessment

**✅ APPROVED** — Clean implementation that follows existing patterns well.
The copy subcommand is well-tested (12 new tests), integrates cleanly with
the existing backend abstraction, and the shared helper extraction reduces
duplication. A few items worth addressing before sending for human review.

**Strengths:**
- S3 server-side copy avoids download-upload round-trip
- Cross-bucket copy works via `CopySource.Bucket`
- Good test coverage: happy path, error paths, dry-run, multi-stage, sha256sum
- Clean extraction of shared helpers from fetch → reusable by copy
- `_create_source_backend` properly uses `WorkflowOutputRoot.from_workflow_run(lookup_workflow_run=True)` for bucket resolution

**Issues:**
- One important duplication concern (retry logic)
- A few minor suggestions

---

## Detailed Review

### 1. artifact_manager.py — Retry logic duplication

### ⚠️ IMPORTANT: Three copies of identical retry logic

`copy_single_artifact` (line 728), `download_single_artifact` (line 203),
and `upload_single_artifact` (line 534) all contain the same
MAX_RETRIES/BASE_DELAY/exponential-backoff pattern. This was already noted
in the prior review (`local_016`) and deferred to align with the
StorageBackend refactor. Since that refactor has now landed (#3596), the
deferred alignment work is unblocked.

**Recommendation:** Note this as a follow-up but don't block the PR on it.
The duplication is stable (all three copies are identical) and extracting a
shared retry helper is a clean separate commit. Consider adding a brief
`# TODO: extract shared retry helper (three copies: download, upload, copy)`
comment near one of the copies so the intent is visible.

---

### 2. artifact_manager.py — ARTIFACT_COMPONENTS constant

### 💡 SUGGESTION: Consider sourcing component list from artifact system

`ARTIFACT_COMPONENTS = ["lib", "run", "dev", "dbg", "doc", "test"]` is
hardcoded at the top of the file (line 67). This list also exists implicitly
in the artifact descriptor system. If a new component type were added,
this list would need manual updating. Not blocking — the component list
is stable and the existing fetch code had the same inline list.

---

### 3. artifact_manager.py — sha256sum pre-filter uses `artifact_exists`

### 💡 SUGGESTION: sha256sum pre-filter makes N extra S3 HEAD calls

In `do_copy` (lines 870-889), the sha256sum pre-filter calls
`source_backend.artifact_exists()` for each sha256sum file, which is an
S3 `HeadObject` call per file. For ~100 artifacts this is ~100 extra API
calls. This is a deliberate design choice (avoids noisy retry logs from
trying to copy nonexistent files), and the calls are cheap and fast.
Just noting it for awareness — no change needed.

---

### 4. artifact_backend.py — `copy_artifact` type annotations

### 💡 SUGGESTION: Narrow type annotations on concrete implementations

`LocalDirectoryBackend.copy_artifact` annotates `source_backend` as
`"LocalDirectoryBackend"` and `S3Backend.copy_artifact` annotates it as
`"S3Backend"`. This is technically a Liskov Substitution Principle
violation (the abstract base says `"ArtifactBackend"` but concrete classes
narrow the type). The runtime `isinstance` check makes this safe in
practice, and the annotations serve as documentation of the actual
constraint. Not blocking.

---

### 5. Tests — Good coverage

The 12 new tests in `artifact_manager_tool_test.py` cover:
- Basic copy between runs
- sha256sum transfer
- Multiple components
- Stage filtering (only produced artifacts)
- Dry run
- Copy failure → exit code 1
- Invalid stage → exit code 1
- Missing --source-run-id → exit code 2
- Multi-stage comma-separated input

The 6 new tests in `artifact_backend_test.py` cover:
- Local-to-local copy
- Nonexistent source raises FileNotFoundError
- Wrong backend type raises TypeError (both directions)
- S3 same-bucket copy (verifies CopySource dict)
- S3 cross-bucket copy (verifies external_repo prefix)

No significant gaps found.

---

### 6. `_create_source_backend` — Clean separation

The function cleanly handles two paths:
- Local: `WorkflowOutputRoot.for_local()` → `LocalDirectoryBackend`
- S3: `WorkflowOutputRoot.from_workflow_run(lookup_workflow_run=True)` → `S3Backend`

The `lookup_workflow_run=True` correctly triggers a GitHub API call to
resolve the source run's bucket, handling cross-repo and bucket-cutover
scenarios. This aligns well with the `WorkflowOutputRoot` API introduced
in #3596.

---

## Recommendations

### ❌ REQUIRED (Blocking):

None.

### ✅ Recommended:

1. Consider a TODO comment near the retry logic noting the three-copy
   duplication and intent to extract a shared helper.

### 💡 Consider:

1. The `ARTIFACT_COMPONENTS` constant could reference the artifact system
   rather than being hardcoded, but this is stable and matches prior
   practice.

### 📋 Future Follow-up:

1. Extract shared retry helper (download/upload/copy all use identical
   logic) — now unblocked by #3596 landing.
2. Semicolon standardization for `--amdgpu-families` (planned for workflow
   wiring PR).

---

## Testing Recommendations

All existing tests pass (422 passed, 1 skipped). The new copy tests are
comprehensive. Before merging:

- Run a workflow_dispatch test with a known baseline run_id to verify
  end-to-end S3 copy behavior (already done in prototype testing with
  run 22655391643).

---

## Conclusion

**Approval Status: ✅ APPROVED**

The copy subcommand is ready for human review. The code is clean, follows
existing patterns, and has thorough test coverage. The main follow-up item
(retry deduplication) is tracked and doesn't block this PR.
