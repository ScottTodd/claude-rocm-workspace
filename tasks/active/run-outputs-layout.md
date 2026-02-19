---
repositories:
  - therock
---

# Run Outputs Layout Consolidation

- **Status:** In Review
- **Priority:** P2 (Medium)
- **Started:** 2026-01-19
- **Branch:** `run-outputs` (15 commits)
- **PR:** https://github.com/ROCm/TheRock/pull/3000

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

### 2026-01-19 - PR Submitted

- Fixed test failures discovered before PR:
  - `fetch_artifacts_test.py`: Updated to use `RunOutputRoot` instead of removed `BucketMetadata`
  - `artifact_manager_tool_test.py`: Updated `LocalDirectoryBackend` calls to use new `RunOutputRoot` interface
- All tests passing: 131 passed in `build_tools/tests/`, 42 passed in `build_tools/github_actions/tests/`
- PR submitted as #3000

### 2026-01-19 - Ready for PR

- All migrations complete (14 commits on `run-outputs` branch)
- Self-review completed: `reviews/local_005_run-outputs.md` - **APPROVED**
- Tests: 39 tests in `run_outputs_test.py` (5 integration tests require GITHUB_TOKEN)
- Tests: 5 tests in `github_actions_utils_test.py` (all require GITHUB_TOKEN)
- Documentation complete with S3 bucket browse links

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

- **PR #3000**: https://github.com/ROCm/TheRock/pull/3000 (15 commits, in review)

## Next Steps

1. [x] Stage and commit `post_build_upload.py` changes
2. [x] Write unit tests for `RunOutputRoot`
3. [x] Migrate `artifact_backend.py` to use `RunOutputRoot`
4. [x] Add documentation to `docs/development/`
5. [x] Migrate `fetch_artifacts.py` and `upload_test_report_script.py`
6. [x] Consolidate `retrieve_bucket_info()` into `run_outputs.py`
7. [x] Create PR for review
8. [ ] Address review feedback (if any)
9. [ ] After PR lands, update `find_artifacts_for_commit.py` on `artifacts-for-commit` branch

## PR Split Consideration

Considered splitting into two PRs but decided against it:

**Option considered: Two PRs**
- PR 1 (~1100 lines, additive): `run_outputs.py` + tests + documentation
- PR 2 (~700 lines, migrations): Migrate all consumers + consolidate `retrieve_bucket_info()`

**Why single PR was chosen:**
- Changes are tightly coupled - `RunOutputRoot.from_workflow_run()` needs `_retrieve_bucket_info`
- Splitting would require either duplicating code or temporary import coupling
- The migration is mechanical and easy to verify
- Well-tested (39 new tests + updated existing tests)
- Single PR gives reviewers full context: new API + how it's used

**If reviewer requests split:** Natural boundary would be foundation (additive) vs migrations (uses new module), but would need refactoring to decouple `retrieve_bucket_info`.

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

## Follow-up Work: Local Testing & Backend Abstraction

### Motivation

We want a better workflow for testing the run outputs structure locally:
1. See what `post_build_upload.py` would do without actually uploading (dry-run)
2. Actually copy local build outputs into the CI structure for testing downstream tools
3. Compose with `LocalDirectoryBackend` in `artifact_backend.py`

### Planned Changes

**A. Add `--dry-run` to `post_build_upload.py`**
- Print what would be uploaded (S3 paths, file sizes) without doing it
- Useful for debugging CI and verifying path computation
- Low effort, immediate value

**B. Refactor upload functions to use a backend abstraction**
- Create `RunOutputBackend` (or extend `ArtifactBackend`) to handle all output types:
  - Artifacts (.tar.xz, .tar.zst)
  - Logs (.log, ninja_logs.tar.gz, index.html, build_time_analysis.html)
  - Manifests (therock_manifest.json)
  - Indices (index-{artifact_group}.html)
- `post_build_upload.py` uses backend.upload_artifact(), backend.upload_log(), etc.
- Same code path for S3 and local testing
- `LocalDirectoryBackend` already exists for artifacts; extend pattern to all output types

### Design Options Considered (2026-01-20)

The current `RunOutputRoot` is heavily S3-oriented (`s3_uri`, `artifact_s3_key`, `https_url`, etc.). We evaluated options to make S3 and local backends first-class citizens:

**Option A: Backend-Agnostic Paths + Separate Backend Classes**
- `RunOutputRoot` returns only relative paths
- Separate `S3Backend` and `LocalBackend` classes resolve paths and handle I/O
- Pros: Clean separation of concerns
- Cons: Two concepts to manage, more indirection

**Option B: Location Objects** ✓ SELECTED
- `RunOutputRoot` returns `OutputLocation` objects
- `OutputLocation` has `.s3_uri`, `.https_url`, `.local_path(staging_dir)` properties
- Caller decides which representation they need at point of use
- Pros: Unified API, all representations from one object, composable
- Cons: Another class, slightly more verbose usage

**Option C: Parallel APIs in RunOutputRoot**
- Add `artifact_local_path()`, `log_local_path()`, etc. alongside existing S3 methods
- Pros: Simple, explicit, no new abstractions
- Cons: Method explosion (3-4 methods per output type)

**Option D: Resolver Pattern**
- `RunOutputRoot` takes a resolver that determines how paths are materialized
- Pros: Pluggable, single method per output type
- Cons: Return type always string (loses `Path` for local), resolver chosen at construction

### Decision: Option B (Location Objects)

Selected because:
1. Single source of truth - one method returns an object with all representations
2. Caller decides which representation at point of use
3. Works well with dry-run (print `loc.s3_uri`) and local testing (`loc.local_path(dir)`)
4. `OutputLocation` is simple and immutable
5. Reduces method count in `RunOutputRoot`
6. Naturally extends to I/O operations later

### Implementation Plan

#### Phase 1: Add OutputLocation class

Add `OutputLocation` dataclass to `run_outputs.py`:

```python
@dataclass(frozen=True)
class OutputLocation:
    """A location that can be resolved to S3 URI, HTTPS URL, or local path."""
    bucket: str
    relative_path: str

    @property
    def s3_uri(self) -> str:
        return f"s3://{self.bucket}/{self.relative_path}"

    @property
    def https_url(self) -> str:
        return f"https://{self.bucket}.s3.amazonaws.com/{self.relative_path}"

    def local_path(self, staging_dir: Path) -> Path:
        return staging_dir / self.relative_path
```

#### Phase 2: Add location methods to RunOutputRoot

Add new methods that return `OutputLocation`:

```python
def artifact(self, filename: str) -> OutputLocation:
    return OutputLocation(self.bucket, f"{self.artifacts_prefix()}/{filename}")

def artifact_index(self, artifact_group: str) -> OutputLocation:
    return OutputLocation(self.bucket, f"{self.artifacts_prefix()}/index-{artifact_group}.html")

def log_file(self, artifact_group: str, filename: str) -> OutputLocation:
    return OutputLocation(self.bucket, f"{self.prefix}/logs/{artifact_group}/{filename}")

def log_index(self, artifact_group: str) -> OutputLocation:
    return OutputLocation(self.bucket, f"{self.prefix}/logs/{artifact_group}/index.html")

def manifest(self, artifact_group: str) -> OutputLocation:
    return OutputLocation(self.bucket, f"{self.prefix}/manifests/{artifact_group}/therock_manifest.json")
```

#### Phase 3: Migrate consumers

Update consumers to use new API:
- `post_build_upload.py`
- `artifact_backend.py` (LocalDirectoryBackend and S3Backend)
- `fetch_artifacts.py`
- `upload_test_report_script.py`

#### Phase 4: Clean up

- Remove old `*_s3_uri()`, `*_s3_key()`, `*_https_url()` methods
- Remove `local_path()` and `for_local()`
- Update documentation

### Files to Modify

| File | Changes |
|------|---------|
| `_therock_utils/run_outputs.py` | Add `OutputLocation`, new methods, deprecate old |
| `_therock_utils/artifact_backend.py` | Use `OutputLocation` in backends |
| `github_actions/post_build_upload.py` | Use new API |
| `tests/run_outputs_test.py` | Add tests for `OutputLocation` |
| `docs/development/run_outputs_layout.md` | Update documentation |

### Scope Decision

**For PR #3000:** Keep current API, merge as-is (the refactoring is additive and can come later)

**Follow-up PR:** Implement OutputLocation pattern, migrate consumers, then deprecate/remove old methods

### Design Issue Discovered (2026-01-20)

While implementing OutputLocation, we found that `fetch_artifacts.py` directly accesses S3:

```python
# fetch_artifacts.py bypasses ArtifactBackend:
def list_s3_artifacts(run_root: RunOutputRoot, ...):
    paginator.paginate(Bucket=run_root.bucket, Prefix=run_root.prefix)
```

This is problematic because:
1. Duplicates logic already in `S3Backend.list_artifacts()`
2. Couples code to S3 implementation details
3. Makes `RunOutputRoot.bucket` a leaky abstraction
4. Blocks making `RunOutputRoot` truly backend-agnostic

**Recommended sequencing:**
1. First: Migrate `fetch_artifacts.py` to use `ArtifactBackend` (separate PR)
2. Then: Resume OutputLocation work with cleaner foundations

**Staged work:** Branch `run-outputs-locations` has partial OutputLocation implementation:
- `OutputLocation` class added
- Location methods added to `RunOutputRoot`
- `post_build_upload.py` and `artifact_backend.py` migrated
- Old methods not yet removed

### 2026-01-20 - Migrated fetch_artifacts.py to use ArtifactBackend

**Completed:**
- Removed `BucketMetadata` dataclass (duplicated path construction)
- Removed module-level S3 client (now uses `S3Backend.s3_client`)
- Updated `list_s3_artifacts()` to take `S3Backend` instead of `BucketMetadata`
- Updated `download_artifact()` to use `backend.s3_client` (preserves retry logic)
- Updated `get_artifact_download_requests()` to take `S3Backend`
- Updated `run()` to create `S3Backend` instead of `BucketMetadata`
- Updated tests to mock `S3Backend` instead of `BucketMetadata` and `paginator`
- Added test for artifact_group filtering behavior

**Key changes:**
- `list_s3_artifacts()` now calls `backend.list_artifacts()` and applies artifact_group filtering post-hoc
- This allows the filtering logic (artifact_group in name OR "generic" in name) to stay in `fetch_artifacts.py` while the raw S3 operations are in the backend

**Tests:** 98 passed, 1 skipped (all `build_tools/tests/`)

### 2026-01-20 - Made fetch_artifacts.py use generic ArtifactBackend interface

**Completed:**
- Added retry logic (3 retries with exponential backoff) to `S3Backend.download_artifact()`
- Updated `ArtifactDownloadRequest`:
  - Changed `backend: S3Backend` to `backend: ArtifactBackend` (generic)
  - Renamed `artifact_key` to `artifact_name` (just the filename, not full S3 key)
  - Removed `bucket` field (backend knows its bucket)
- Simplified `download_artifact()` to just call `backend.download_artifact(artifact_name, output_path)`
- Updated `get_artifact_download_requests()` to use `ArtifactBackend` type hint
- Removed unused `time` import from `fetch_artifacts.py`

**Benefits:**
- `fetch_artifacts.py` no longer accesses S3-specific details like `s3_client`
- Retry logic is now in the backend where it belongs
- `ArtifactDownloadRequest` could theoretically work with `LocalDirectoryBackend` for testing
- Cleaner abstraction boundary

**Tests:** 98 passed, 1 skipped

### 2026-01-20 - PR #3019: Migrate fetch_artifacts.py to ArtifactBackend

**PR:** https://github.com/ROCm/TheRock/pull/3019
**Branch:** `fetch-artifacts-backend` (6 commits)

**Final changes:**
- Removed `BucketMetadata` class and module-level S3 client
- Renamed `list_s3_artifacts()` → `list_artifacts_for_group()` (backend-agnostic)
- Reused `DownloadRequest` and `download_artifact()` from `artifact_manager.py`
- Removed duplicate retry logic (now in `artifact_manager.py`)
- Removed useless `testListArtifactsForGroup_NotFound` test
- Moved `output_dir.mkdir()` to after dry-run check

**Net change:** -119 lines (+69, -188) across 2 files

**Review:** `reviews/local_006_fetch-artifacts-backend.md` - APPROVED

**Next:** Resume `OutputLocation` work on `run-outputs-locations` branch with cleaner foundations. The `fetch_artifacts.py` refactoring resolves the leaky abstraction issue where it was directly accessing S3 via `run_root.bucket` and `run_root.prefix`.

## Design: Server-Side Index Generation (#3331)

**Issue:** https://github.com/ROCm/TheRock/issues/3331
**Parent:** https://github.com/ROCm/TheRock/issues/3344 (move S3 scripts server-side)

### Problem

`post_build_upload.py` currently generates index HTML files client-side (in the workflow) before uploading them alongside raw outputs. This has several problems:

1. **Multi-arch CI gap** — The new multi-arch CI (`multi_arch_build_*_artifacts.yml`) uses `artifact_manager.py push` for artifacts but has no log/index/manifest upload at all. Adding index generation there means duplicating the logic.
2. **Coupling** — Index generation is tangled with uploading, making it hard to test or change either independently.
3. **Fragility** — The `indexer.py` dependency and link-rewriting hack (`a href=".."` → artifact index cross-reference) are brittle.

### Design Principle

**Client-side knows the layout; server-side knows how to list files.**

- Upload scripts decide *where* files go (using `RunOutputRoot` as the structure authority).
- The server-side index generator is completely generic — like Apache's `mod_autoindex`. It lists what's at a prefix, shows filenames/sizes/timestamps, and writes `index.html`. It knows nothing about TheRock, artifact groups, or cross-references.
- Standard `..` parent links provide navigation between levels. No cross-reference rewriting.

### Changes

**Client-side (PR for #3331):**

Remove index generation from the upload path:
- Remove `index_log_files()` — generates log directory index, rewrites parent links
- Remove `index_artifact_files()` — generates artifact directory index
- Remove the `indexer.py` dependency (`sys.path.append` for `third-party/indexer`)
- Keep all upload functions unchanged — they still upload raw files (artifacts, logs, manifests) to the same S3 paths

This is a net deletion from `post_build_upload.py`. The upload path becomes: archive ninja logs → upload artifacts → upload logs → upload manifest → write GHA summary.

**Server-side (separate work, #3344):**

Deploy a Lambda triggered by S3 `PutObject` events that:
1. Determines the "directory" prefix from the uploaded object's key
2. Lists objects at that prefix via `ListObjectsV2`
3. Generates `index.html` with file listing (name, size, last modified)
4. Writes it back to the same prefix

This is generic infrastructure — not TheRock-specific. An off-the-shelf solution like [s3-directory-listing](https://github.com/razorjack/s3-directory-listing) could work, or a minimal custom Lambda.

CloudFront should set `TTL=0` on `*/index.html` paths so listings are always fresh.

### Alternatives Considered

**A. Keep generating indexes client-side (status quo)**

Each CI workflow generates index HTML locally and uploads it alongside raw files. This is what `post_build_upload.py` does today via `index_log_files()`, `index_artifact_files()`, and the `third-party/indexer` dependency.

Rejected because: the multi-arch CI doesn't use `post_build_upload.py` at all (it uses `artifact_manager.py push`), so we'd need to duplicate the index generation logic or shoehorn it in. Also, index generation is coupled to uploading, making both harder to test or change.

**B. Client-side JavaScript directory listing**

Deploy a single static HTML file that uses JavaScript to call S3's `ListObjectsV2` API at browse time, rendering directory listings dynamically in the browser. Projects like [s3-bucket-listing](https://github.com/rufuspollock/s3-bucket-listing) and [s3-autoindex](https://github.com/sgtFloyd/s3-autoindex) implement this pattern.

Rejected because: requires `ListBucket` access from browsers (public access + CORS on the bucket). More importantly, some of our tooling scrapes index pages rather than interfacing with S3 directly — especially relevant as we move toward CloudFront, where the S3 list API wouldn't be available. Static HTML indexes that work through CloudFront are more useful.

**C. Layout-aware Lambda (server knows TheRock structure)**

A Lambda that knows the run outputs layout — artifact groups, log directory nesting, cross-references between output types (e.g., log index parent link → artifact index for the same group). It would generate specialized indexes with cross-navigation links.

Rejected because: coupling the server-side to the layout creates forward/backward compatibility issues. We'll be adding new files and folders over time and may change directory nesting. If the Lambda needs to understand the structure, every layout change requires coordinating client and server updates. A generic file lister avoids this entirely.

**D. S3 static website hosting built-in indexes**

S3's static website hosting feature can serve `index.html` when a "directory" is requested, but it does not auto-generate directory listings. You must provide your own `index.html` at each level. So this doesn't solve the generation problem — it only helps with serving, which CloudFront already handles.

**Selected: Generic Lambda on S3 events (Option E)**

A Lambda triggered by S3 `PutObject` events that simply lists objects at a prefix and generates a static `index.html` with filenames, sizes, and timestamps. Completely generic — works for any directory structure, no TheRock-specific knowledge, no coordination needed when the layout changes. [s3-directory-listing](https://github.com/razorjack/s3-directory-listing) is an existing implementation of this pattern.

### Scope Boundaries

| In scope for #3331 | Out of scope |
|---|---|
| Remove index generation from `post_build_upload.py` | Lambda implementation (#3344) |
| Remove `indexer.py` dependency | CloudFront configuration |
| Remove link-rewriting code | Adding log/manifest upload to multi-arch CI |
| | `RunOutputRoot` refactoring (parallel work) |

### Spectrum of Server-Side Sophistication

The generic file-lister Lambda is the starting point, not the end state. There's a spectrum:

1. **Generic directory lister** (start here) — Lists files at a prefix with name/size/timestamp. No knowledge of what's being uploaded. Works for any layout, zero maintenance. Like `mod_autoindex`.

2. **Content-aware index pages** — The nightly tarball index at `https://therock-nightly-tarball.s3.amazonaws.com/index.html` already has sorting/filtering specific to the file types present. As CI outputs grow, we may want similar treatment — e.g., grouping artifacts by GPU family, showing only `.tar.xz` files in one section and logs in another.

3. **Workflow run dashboard** — A summary page per run that updates dynamically as builds complete. Shows CI configuration (which jobs, why), commit/branch/PR links, pending/completed job status, artifact listings, test report summaries with links to logs. Similar to [EngFlow Build Dashboard](https://www.engflow.com/product/buildDashboard), Google's Sponge, or Buildkite job summary pages. This would require either a more sophisticated static page generator (Lambda that understands build metadata) or a dynamic web server.

The design principle still holds across all three levels: **start generic, add domain knowledge only when there's a concrete need.** Level 1 is #3331/#3344 scope. Levels 2-3 are future work that builds on the same S3 event infrastructure.

### Sequencing

1. **#3331 PR** — Remove client-side index generation (net deletion, low risk)
2. **#3344** — Deploy server-side index Lambda (generic, no TheRock coupling)
3. **Parallel** — Land `RunOutputRoot`/`OutputLocation`, extend multi-arch CI upload story
4. **Future** — Evolve server-side toward content-aware indexes and/or workflow run dashboards as needs arise
