---
repositories:
  - therock
---

# Run Outputs Layout Consolidation

**Status:** Ready for PR
**Priority:** P2 (Medium)
**Started:** 2026-01-19
**Branch:** `run-outputs` (14 commits)

## Overview

Consolidate and document the path computation logic for CI workflow run outputs. Currently, multiple files duplicate the logic for computing S3 paths, URLs, and local staging directories. This task creates a single source of truth (`RunOutputRoot`) and migrates existing code to use it.

## Goals

- [x] Create `RunOutputRoot` dataclass as single source of truth for path computation
- [x] Document the complete layout structure for all output types
- [x] Migrate `post_build_upload.py` to use `RunOutputRoot`
- [x] Migrate `artifact_backend.py` to use `RunOutputRoot`
- [x] Write unit tests for `RunOutputRoot`
- [x] Add `docs/development/run_outputs_layout.md` documentation
- [ ] (Future) Migrate `find_artifacts_for_commit.py` to use `RunOutputRoot`

## Context

### Background

The S3 path pattern `{external_repo}{run_id}-{platform}` was duplicated in 4+ places:
- `artifact_backend.py:167` - `S3Backend.__init__`
- `post_build_upload.py:299` - manual f-string construction
- `find_artifacts_for_commit.py:69` - `ArtifactRunInfo.s3_path` property
- Various URL constructions for HTTPS, index files, etc.

This duplication made it hard to:
1. Understand the complete layout structure
2. Add new output types (python packages, native packages)
3. Make layout changes (e.g., moving artifacts to subdirectory)

### Related Work

- Parent task: `tasks/active/artifacts-for-commit.md` (this work split off from there)
- RFC: `../TheRock/docs/rfcs/RFC0009-Submodule-Bisect-Tooling.md`

### Directories/Files Involved

```
../TheRock/build_tools/_therock_utils/run_outputs.py     # NEW: RunOutputRoot class
../TheRock/build_tools/_therock_utils/artifact_backend.py # To be migrated
../TheRock/build_tools/github_actions/post_build_upload.py # Migrated
../TheRock/build_tools/find_artifacts_for_commit.py       # To be migrated (on different branch)
```

## Decisions & Trade-offs

### Decision: Name "run outputs" instead of "artifacts"

- **Rationale:** "Artifact" is too narrow. A workflow run produces many output types: build artifacts, logs, manifests, reports, python packages, native packages, etc.
- **Alternatives considered:** "run store", "deliverables", "run bundle"

### Decision: Keep artifacts at root (Option A layout)

- **Rationale:** Backwards compatible with existing tooling. Migrating to `artifacts/` subdirectory would be a breaking change.
- **Alternatives considered:**
  - Option B: Everything in typed subdirectories (`artifacts/`, `logs/`, etc.)
  - Option C: Hybrid (new types in subdirs, artifacts at root)
- **Future:** Can migrate to Option B later by changing only `RunOutputRoot` methods.

### Decision: Module location `_therock_utils/run_outputs.py`

- **Rationale:** `_therock_utils/` is for shared utilities; `artifact_backend.py` already lives there.
- **Alternatives considered:** `github_actions_utils.py` (already too large), new top-level module

## Future Work: Compatibility & Versioning

### The Problem

Upload code runs at a fixed point in time and makes layout decisions. Download code runs later and needs to know what to expect. We've already encountered this with:

1. **Bucket cutover** (`_BUCKET_CUTOVER_DATE`): Bucket naming changed from `therock-artifacts` to `therock-ci-artifacts`. Download code checks workflow run date to determine which bucket.

2. **Subdirectory migration** (planned): Moving artifacts from root to `artifacts/` subdirectory would be another breaking change.

As these systems get heavier use, we won't be able to make breaking changes without a compatibility window.

### Options Considered

**Option A: Index/Sitemap at RunOutputRoot**
- Upload creates a machine-readable index (e.g., `manifest.json` or `sitemap.json`) at the root
- Index describes schema version, lists files, includes checksums
- Download code reads index first, then knows how to find everything
- Pros: Self-describing, enables discovery, future-proof
- Cons: One more file to upload, need to handle missing index for old runs

**Option B: Breaking Changes + Retention Policy**
- Establish artifact retention policy (e.g., 30/60/90 days)
- Make breaking changes with notice period
- Once retention window passes, old code paths can be deleted
- Pros: Simpler code, no accumulating backwards-compat logic
- Cons: Users referencing old runs will break during transition

**Option C: Simple Presence Checks (current approach)**
- For subdirectory change: check if `artifacts/` exists, fall back to root
- For bucket changes: use date-based logic
- Pros: Simple, no new infrastructure
- Cons: Each change adds more conditional logic

### Recommendation (2026-01-19)

1. **Short term**: Use presence checks for subdirectory migration (Option C)
2. **Medium term**: Establish retention policy - this makes Option B viable
3. **Long term**: If we need richer metadata (discovery, dependency graphs, checksums), add an index. But don't add it just for schema versioning.

### Open Questions

- What retention period is appropriate? (30/60/90 days?)
- Do we need machine-readable artifact discovery? (Currently requires S3 list operations)
- Should the index include build metadata beyond just file listings?

## Investigation Notes

### 2026-01-19 - Initial Implementation

**Created `run_outputs.py` with:**
- `RunOutputRoot` dataclass (frozen/immutable)
- Properties: `prefix`, `s3_uri`, `https_url`
- Methods for each output type:
  - Artifacts: `artifact_s3_key()`, `artifact_s3_uri()`, `artifact_index_url()`, etc.
  - Logs: `logs_prefix()`, `logs_s3_uri()`, `log_index_url()`, `build_time_analysis_url()`
  - Manifests: `manifest_s3_key()`, `manifest_s3_uri()`, `manifest_url()`
  - Future: `python_prefix()`, `packages_prefix()`, `reports_prefix()`
- Factory methods: `from_workflow_run()`, `for_local()`

**Migrated `post_build_upload.py`:**
- Replaced manual path construction with `RunOutputRoot.from_workflow_run()`
- Updated all upload functions to take `RunOutputRoot` instead of `bucket_uri`/`bucket_url`
- Changed from `from github_actions_utils import *` to explicit imports

## Code Changes

### Files Modified

- `build_tools/_therock_utils/run_outputs.py` - NEW: `RunOutputRoot` class (committed)
- `build_tools/github_actions/post_build_upload.py` - Migrated to use `RunOutputRoot` (committed)
- `build_tools/_therock_utils/artifact_backend.py` - Migrated to use `RunOutputRoot` (committed)
- `build_tools/tests/run_outputs_test.py` - NEW: Unit tests for `RunOutputRoot` (committed)
- `build_tools/tests/artifact_backend_test.py` - Updated for new interface (committed)
- `docs/development/run_outputs_layout.md` - NEW: Documentation (committed)
- `docs/development/README.md` - Added link to run_outputs_layout.md (committed)
- `build_tools/fetch_artifacts.py` - Migrated to use `RunOutputRoot` (committed)
- `build_tools/github_actions/upload_test_report_script.py` - Migrated (committed)
- `build_tools/github_actions/github_actions_utils.py` - Removed `retrieve_bucket_info()` (committed)

### PRs

- Branch: `run-outputs` (14 commits, ready for PR)

## Next Steps

1. [x] Stage and commit `post_build_upload.py` changes
2. [x] Write unit tests for `RunOutputRoot`
3. [x] Migrate `artifact_backend.py` to use `RunOutputRoot`
4. [x] Add documentation to `docs/development/`
5. [x] Migrate `fetch_artifacts.py` and `upload_test_report_script.py`
6. [x] Consolidate `retrieve_bucket_info()` into `run_outputs.py`
7. [ ] Create PR for review
8. [ ] After PR lands, update `find_artifacts_for_commit.py` on `artifacts-for-commit` branch

## Layout Reference

Current layout structure (documented in `run_outputs.py`):

```
{run_id}-{platform}/
├── {name}_{component}_{family}.tar.xz        # Build artifacts (at root)
├── {name}_{component}_{family}.tar.xz.sha256sum
├── index-{artifact_group}.html               # Per-group artifact index
├── logs/{artifact_group}/
│   ├── *.log                                 # Build logs
│   ├── ninja_logs.tar.gz                     # Ninja timing logs
│   ├── index.html                            # Log index
│   └── build_time_analysis.html              # Build timing (Linux)
└── manifests/{artifact_group}/
    └── therock_manifest.json                 # Build manifest
```

Future output types (python packages, native packages, reports) can be added by extending `RunOutputRoot` - see docs/development/run_outputs_layout.md for instructions.
