---
repositories:
  - therock
---

# Artifacts for Commit

- **Status:** In progress
- **Priority:** P1 (High)
- **Started:** 2026-01-13
- **Target:** TBD

## Overview

Build the capability to find and fetch CI artifacts for a given commit SHA. This is the foundational piece for the submodule bisect tooling (RFC0009) - without it, we can't download pre-built artifacts for historical commits.

## Goals

- [ ] Query GitHub API to find workflow run_id for a commit
- [ ] Determine correct S3 bucket for a given repo/workflow
- [ ] Download and cache artifacts for a commit
- [ ] Provide clean API/CLI for "give me artifacts for commit X"

## Context

### Background

The submodule bisect tooling needs to fetch pre-built artifacts for arbitrary commits in rocm-systems/rocm-libraries. The prototype in `query_workflow_runs.py` validated that:
- All 19 test commits have workflow runs
- GitHub API `head_sha` parameter works for commit→run_id lookup
- Artifacts are in S3 at `{bucket}/{external_repo}{run_id}-{platform}/`

### Related Work
- Parent task: `tasks/active/submodule-bisect-tooling.md`
- RFC: `../TheRock/docs/rfcs/RFC0009-Submodule-Bisect-Tooling.md`
- Discussion: https://github.com/ROCm/TheRock/issues/2608

### Directories/Files Involved
```
prototypes/query_workflow_runs.py           # Working prototype for commit→run_id
../TheRock/build_tools/find_artifacts_for_commit.py   # NEW: Find artifacts for a commit
../TheRock/build_tools/find_latest_artifacts.py       # NEW: Find latest commit with artifacts
../TheRock/build_tools/fetch_artifacts.py             # Existing S3 artifact fetcher
../TheRock/build_tools/github_actions/github_actions_utils.py  # GitHub API utils (refactored)
../TheRock/build_tools/github_actions/tests/github_actions_utils_test.py  # Tests for GitHubAPI
../TheRock/build_tools/bisect/              # Target location for new code
```

### Existing Infrastructure

**GitHub API (github_actions_utils.py):**
- `gha_query_workflow_run_information(repo, run_id)` - Get run metadata
- `gha_query_last_successful_workflow_run(repo, workflow, branch)` - Find recent runs
- `retrieve_bucket_info(repo, run_id)` - Determine S3 bucket

**Artifact Fetching (fetch_artifacts.py):**
- Downloads from S3 using `boto3`
- Include/exclude regex filtering
- Parallel download + extraction
- Requires: `--run-id`, `--artifact-group`, `--output-dir`

**Prototype (query_workflow_runs.py):**
- Uses `gh api` CLI for authenticated access
- Queries `/repos/{repo}/actions/workflows/{workflow}/runs?head_sha={commit}`
- Returns run_id, status, conclusion, url

### Task list

**Scenario 1**: For a given commit, check if it has CI artifacts already.

**Scenario 2**: For a given commit that **does not** have CI artifacts yet, find an appropriate baseline commit that includes all artifacts for the desired GPU family.
* The key observation is that _most_ commits do not modify all artifacts. Notably, the compiler in the amd-llvm artifact changes infrequently, so most workflows should be able to reuse the amd-llvm artifact from a prior job.
* The search logic here will start simple and get more robust/complicated over time. We'll start at a commit by commit granularity but may later want to do a hashmap style lookup from artifact fprint (fingerprints) to a database of CI-produced artifacts that allows for efficient search across a large number of workflow runs and commits. See also https://github.com/ROCm/TheRock/pull/2432 (commit `77f0cb2112d1d0aaae0de6088a6e4337f2488233` in TheRock) which implemented the fingerprinting logic.
* For commits in TheRock and for GPU families that are built continuously (see `amdgpu_family_info_matrix_presubmit` and `amdgpu_family_info_matrix_postsubmit` in `build_tools/github_actions/amdgpu_family_matrix.py`), we can currently assume that workflow runs of https://github.com/ROCm/TheRock/actions/workflows/ci.yml?query=branch%3Amain will include artifacts for all subprojects. So for a commit on a local branch or on a pull request, we could start by finding the base commit of that branch that already exists on the `main` branch and checking if that commit has completed workflow runs on github already. If it does not, or if that commit failed workflow runs for some reason, we could go back in history one commit at a time until we find a commit with artifacts.
* For commits in rocm-libraries and rocm-systems, the baseline is currently the `ref` used for the `Checkout TheRock repository` step in the `therock-ci.yml` workflow. When a pull request runs a CI job in rocm-libararies it uses that commit of TheRock to checkout rocm-systems and amd-llvm.

So here are some example "user journeys":

1. I'm working locally. I branch off of `main` and make a few source changes to rocm-libraries. Now I want to build from source, but I don't want to build LLVM or rocm-systems. I run a script that finds artifacts from CI runs and bootstraps my local build.
2. I send a pull request to TheRock with my changes. The CI workflows run the same script (or a similar script).
3. I send a pull request to rocm-libraries with my changes. The CI workflows in that repository do the same thing.
4. I want to compare the binary size of artifacts between two commits. I run the "find CI artifacts for commit" script once for each commit and it points me to where those artifacts are stored on AWS S3. I run a different script to diff the binary size of each file.

## Implementation Plan

### New Script: `find_artifacts_for_commit.py`

Location: `build_tools/find_artifacts_for_commit.py`

**CLI Interface:**

```
python find_artifacts_for_commit.py \
  --commit <sha>              # Required, or HEAD if omitted
  --repo <owner/repo>         # e.g., ROCm/TheRock (or detect from git remote)
  --workflow <file>           # e.g., ci.yml (default: infer from repo)
  --platform <linux|windows>  # Default: platform.system().lower()
  --amdgpu-family <family>    # e.g., gfx94X-dcgpu, gfx110X-all (required for index URL)

Exit codes:
  0 = found workflow run with artifacts
  1 = not found (no workflow run for this commit)
  2 = error (API failure, invalid input, etc.)
```

**GPU Family Values** (from `amdgpu_family_matrix.py`):

| Trigger | Family |
|---------|--------|
| presubmit | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151` |
| postsubmit | `gfx950-dcgpu`, `gfx120X-all` |
| nightly | `gfx90X-dcgpu`, `gfx101X-dgpu`, `gfx103X-dgpu`, `gfx1150`, `gfx1152`, `gfx1153` |

**Output (human-readable to stdout):**

```
Commit:       abc123def456...
Repository:   ROCm/TheRock
Workflow:     ci.yml
Run ID:       12345678901
Status:       completed (success)
URL:          https://github.com/ROCm/TheRock/actions/runs/12345678901
Platform:     linux
GPU Family:   gfx94X-dcgpu
S3 Bucket:    therock-ci-artifacts
S3 Path:      12345678901-linux/
Index:        https://therock-ci-artifacts.s3.amazonaws.com/12345678901-linux/index-gfx94X-dcgpu.html
```

**Python API (for script-to-script composition):**

```python
@dataclass
class ArtifactRunInfo:
    """Information about a workflow run's artifacts."""
    commit_sha: str
    repo: str
    workflow: str
    run_id: str
    status: str           # "completed", "in_progress", etc.
    conclusion: str | None   # "success", "failure", None if in_progress
    html_url: str
    platform: str         # "linux" or "windows"
    amdgpu_family: str    # e.g., "gfx94X-dcgpu"
    s3_bucket: str
    s3_path: str          # e.g., "12345678901-linux/"

    @property
    def s3_uri(self) -> str:
        return f"s3://{self.s3_bucket}/{self.s3_path}"

    @property
    def index_url(self) -> str:
        return f"https://{self.s3_bucket}.s3.amazonaws.com/{self.s3_path}index-{self.amdgpu_family}.html"

# Usage from another Python script:
from find_artifacts_for_commit import find_artifacts_for_commit

info: ArtifactRunInfo | None = find_artifacts_for_commit(
    commit="abc123",
    repo="ROCm/TheRock",
    amdgpu_family="gfx94X-dcgpu",
)
if info:
    # Pass to artifact_manager or other tooling
    print(f"Found artifacts at {info.s3_uri}")
    print(f"Browse: {info.index_url}")
```

This allows composition via Python imports rather than shell pipes or JSON parsing.

**Core Functions:**

```python
def find_artifacts_for_commit(
    commit: str,
    repo: str,
    amdgpu_family: str,           # e.g., "gfx94X-dcgpu"
    workflow: str | None = None,  # None = infer from repo
    platform: str | None = None,  # None = current platform
) -> ArtifactRunInfo | None:
    """Main entry point: find artifact info for a commit.

    Returns ArtifactRunInfo if workflow run exists, None otherwise.
    This is the function other Python scripts should import and call.
    """

def query_workflow_run(
    repo: str,           # "ROCm/TheRock"
    workflow: str,       # "ci.yml"
    commit_sha: str,     # Full SHA
) -> dict | None:
    """Query GitHub API for workflow run matching this commit.

    Uses github_actions_utils.gha_send_request() for API access.
    Returns raw API response dict or None if no run exists.
    Internal function - callers should use find_artifacts_for_commit().
    """

def get_artifact_location(
    repo: str,
    run_id: str,
    platform: str,
) -> tuple[str, str]:
    """Determine S3 bucket and path for a workflow run's artifacts.

    Uses github_actions_utils.retrieve_bucket_info() for bucket selection.
    Returns (bucket, path) tuple.
    """

def detect_repo_from_git() -> str | None:
    """Detect repo from git remote origin URL.

    Parses: git@github.com:ROCm/TheRock.git -> ROCm/TheRock
            https://github.com/ROCm/TheRock.git -> ROCm/TheRock
    """

def infer_workflow_for_repo(repo: str) -> str:
    """Infer default workflow file for a repository.

    ROCm/TheRock -> ci.yml
    ROCm/rocm-libraries -> therock-ci.yml
    ROCm/rocm-systems -> therock-ci.yml
    """
```

**Composition with artifact_manager.py:**

```python
# In a higher-level script (e.g., bootstrap_from_commit.py)
from find_artifacts_for_commit import find_artifacts_for_commit, ArtifactRunInfo
from artifact_manager import do_fetch

info = find_artifacts_for_commit(
    commit="abc123",
    repo="ROCm/TheRock",
    amdgpu_family="gfx94X-dcgpu",
)
if info is None:
    sys.exit("No artifacts found for commit")

# Build args namespace for artifact_manager
args = argparse.Namespace(
    run_id=info.run_id,
    platform=info.platform,
    stage="all",
    amdgpu_families=info.amdgpu_family,
    output_dir=Path("./build"),
    # ... other required args
)
do_fetch(args)
```

Or via CLI (less preferred, but works):
```bash
# Human runs CLI, reads output, then runs artifact_manager
python build_tools/find_artifacts_for_commit.py --commit abc123
# Output shows run_id, user copies it
python build_tools/artifact_manager.py fetch --run-id 12345678901 ...
```

### Future: Scenario 2 (Fallback Search)

Not in initial scope. Will add later:
- `--fallback` flag to search for baseline commit if direct lookup fails
- Walk back through git history to find commit with successful CI
- For rocm-libraries/rocm-systems: find TheRock ref from workflow

### Out of Scope (Separate Tasks)

**1. ~~`gh` CLI fallback for `github_actions_utils.py`~~** ✅ DONE (see 2026-01-14 notes)

**2. Consolidate `ArtifactRunInfo` with `BucketMetadata`**

`fetch_artifacts.py` has `BucketMetadata`:
```python
@dataclass
class BucketMetadata:
    external_repo: str
    bucket: str
    workflow_run_id: str
    platform: str
    s3_key_path: str  # derived: f"{external_repo}{workflow_run_id}-{platform}"
```

Our `ArtifactRunInfo` overlaps (platform, bucket, path, run_id) but adds workflow metadata (commit, status, conclusion, html_url, amdgpu_family).

Options:
- `ArtifactRunInfo` contains `BucketMetadata` (composition)
- Shared base class for S3 location info
- Single unified dataclass

Should revisit after initial implementation to reduce duplication.

**3. Resolve partial commit SHAs in `github_actions_utils.py`**

The GitHub API `head_sha` parameter requires a full 40-char SHA. Add a `resolve_commit_sha(partial, repo)` function to `github_actions_utils.py` that:
- Returns as-is if already a full 40-char hex string
- Tries local `git rev-parse --verify {partial}^{commit}` first (fast, no network)
- Falls back to GitHub API `GET /repos/{owner}/{repo}/commits/{partial}` (works without local clone)
- Raises if the partial SHA is ambiguous (git errors with "ambiguous argument", GitHub returns 409/422)

This would let `find_artifacts_for_commit.py` accept abbreviated SHAs from the user.

## Investigation Notes

### 2026-01-13 - Task Created

Extracted from submodule-bisect-tooling as a focused sub-task. Ready to implement piece by piece.

### 2026-01-14 - GitHubAPI Auth and find_latest_artifacts.py

**New script: `find_latest_artifacts.py`**

Created script to find the most recent commit on a branch with CI artifacts. Uses GitHub API to list commits, then checks each for artifacts via S3 HEAD requests.

Key features:
- Uses GitHub API for commit listing (no local git dependency)
- Verifies artifacts actually exist via HTTP HEAD to S3 index URL
- `--max-commits` flag to limit search depth (default 50)
- `-v/--verbose` for progress output

**New function: `check_artifacts_exist()`** in `find_artifacts_for_commit.py`

Added S3 verification via HTTP HEAD request. This is important because workflow status/conclusion alone isn't reliable - a CI run can fail tests but still upload artifacts.

**GitHubAPI refactoring** in `github_actions_utils.py` (will be separate PR)

Refactored GitHub API authentication into a `GitHubAPI` class:
- Detects auth automatically: GITHUB_TOKEN → gh CLI → unauthenticated
- `AuthMethod` enum as inner class
- Private methods: `_detect_auth_method()`, `_send_request_via_gh_cli()`, `_send_request_via_rest_api()`
- Module singleton `_default_github_api` with wrapper functions for backwards compatibility
- `GitHubAPIError` exception class

This enables local dev with `gh auth login` without needing GITHUB_TOKEN env var.

**Commits on `artifacts-for-commit` branch:**
- Multiple commits for GitHubAPI class refactoring (to be cherry-picked to separate PR)
- `find_latest_artifacts.py` implementation
- `check_artifacts_exist()` addition

**Next session:** After GitHubAPI auth changes are in separate PR, continue with:
- Adjusting logging verbosity (reduce noise)
- Landing initial `find_artifacts_for_commit.py` and `find_latest_artifacts.py`

**Session end state (2026-01-14):**
- `github-actions-gh-authentication` branch: Sent as PR for review (single commit: eeb69681)
- `artifacts-for-commit` branch: Still has the artifact scripts, will need rebase after auth PR lands
- Review written: `reviews/local_003_github-actions-gh-authentication.md` (APPROVED)

### 2026-01-13 - Initial Implementation Complete

Created `build_tools/find_artifacts_for_commit.py` with:

**ArtifactRunInfo dataclass** with descriptive field names:
- `git_commit_sha`, `github_repository_name`, `external_repo`
- `platform`, `amdgpu_family`
- `workflow_file_name`, `workflow_run_id`, `workflow_run_status`, `workflow_run_conclusion`, `workflow_run_html_url`
- `s3_bucket`
- Computed properties: `s3_path`, `s3_uri`, `s3_index_url`

**Functions:**
- `query_workflow_run()` - GitHub API query via `gha_send_request()`
- `find_artifacts_for_commit()` - Main entry point, returns `ArtifactRunInfo`
- `infer_workflow_for_repo()` - Maps repo name to workflow file
- `detect_repo_from_git()` - Parses git remotes for ROCm repos
- `print_artifact_info()` - Human-readable CLI output

**Tested with:**
- rocm-systems commit `3568e0df` → Found run `20723767265` in `therock-ci-artifacts-external`
- TheRock commit `77f0cb21` → Found run `20083647898` in `therock-ci-artifacts`
- TheRock fork commit `62bc1eaa` → Found run `20384488184` in `therock-ci-artifacts-external`

**Commits:**
- `c8b65570` - Initial implementation
- (uncommitted) - Renamed fields to be more descriptive, added `external_repo`, made `s3_path` computed

**TODOs added in code:**
- Consider wrapping `ArtifactBackend` or using `BucketMetadata` to reduce duplication
- Consider moving `print_artifact_info` into `ArtifactRunInfo` class

Test commands and output:
```
D:\projects\TheRock (artifacts-for-commit)
λ python build_tools\find_artifacts_for_commit.py --commit=62bc1eaa02e6ad1b49a718eed111cf4c9f03593a --amdgpu-family=gfx110X-all

Warning: GITHUB_TOKEN not set, requests may be rate limited
Sending request to URL: https://api.github.com/repos/ROCm/TheRock/actions/workflows/ci.yml/runs?head_sha=62bc1eaa02e6ad1b49a718eed111cf4c9f03593a
Retrieving bucket info...
  (explicit) github_repository: ROCm/TheRock
  workflow_run_id             : 20384488184
Warning: GITHUB_TOKEN not set, requests may be rate limited
Sending request to URL: https://api.github.com/repos/ROCm/TheRock/actions/runs/20384488184
  head_github_repository      : ScottTodd/TheRock
  is_pr_from_fork             : True
Retrieved bucket info:
  external_repo: ROCm-TheRock/
  bucket       : therock-ci-artifacts-external
Commit:       62bc1eaa02e6ad1b49a718eed111cf4c9f03593a
Repository:   ROCm/TheRock
Workflow:     ci.yml
Run ID:       20384488184
Status:       completed (failure)
Run URL:      https://github.com/ROCm/TheRock/actions/runs/20384488184
Platform:     windows
GPU Family:   gfx110X-all
S3 Bucket:    therock-ci-artifacts-external
S3 Path:      ROCm-TheRock/20384488184-windows/
S3 Index:     https://therock-ci-artifacts-external.s3.amazonaws.com/ROCm-TheRock/20384488184-windows/index-gfx110X-all.html

D:\projects\TheRock (artifacts-for-commit)
λ python build_tools\find_artifacts_for_commit.py --commit=62bc1eaa02e6ad1b49a718eed111cf4c9f03593a --amdgpu-family=gfx110X-all
Warning: GITHUB_TOKEN not set, requests may be rate limited
Sending request to URL: https://api.github.com/repos/ROCm/TheRock/actions/workflows/ci.yml/runs?head_sha=62bc1eaa02e6ad1b49a718eed111cf4c9f03593a
Retrieving bucket info...
  (explicit) github_repository: ROCm/TheRock
  workflow_run_id             : 20384488184
Warning: GITHUB_TOKEN not set, requests may be rate limited
Sending request to URL: https://api.github.com/repos/ROCm/TheRock/actions/runs/20384488184
  head_github_repository      : ScottTodd/TheRock
  is_pr_from_fork             : True
Retrieved bucket info:
  external_repo: ROCm-TheRock/
  bucket       : therock-ci-artifacts-external
Commit:       62bc1eaa02e6ad1b49a718eed111cf4c9f03593a
Repository:   ROCm/TheRock
Workflow:     ci.yml
Run ID:       20384488184
Status:       completed (failure)
Run URL:      https://github.com/ROCm/TheRock/actions/runs/20384488184
Platform:     windows
GPU Family:   gfx110X-all
S3 Bucket:    therock-ci-artifacts-external
S3 Path:      ROCm-TheRock/20384488184-windows
S3 Index:     https://therock-ci-artifacts-external.s3.amazonaws.com/ROCm-TheRock/20384488184-windows/index-gfx110X-all.html
```

### 2026-01-15 - Refactoring and Error Handling

**Error handling improvements** (on `github-actions-gh-authentication` branch):
- Standardized all error paths in `GitHubAPI.send_request()` to raise `GitHubAPIError`
- Exception chaining via `raise ... from e` preserves original cause
- Added unit tests for all failure modes (timeout, OSError, HTTP errors, JSON errors)
- Commit: `9026d029`

**API deduplication** (on `artifacts-for-commit` branch):
- Renamed `gha_query_workflow_run_information` → `gha_query_workflow_run_by_id` (with compat alias)
- Added `gha_query_workflow_runs_for_commit()` - queries by commit SHA, returns list
- `retrieve_bucket_info()` now accepts `workflow_run` param to skip redundant API call
- `find_artifacts_for_commit()` iterates runs, uses `check_artifacts_exist()` to find first with artifacts
- Added `git_commit_url` property to `ArtifactRunInfo`
- Commits: `2a7e341a`, `5dc9f8aa`

**Current branch state:**
- `github-actions-gh-authentication`: PR #2771 under review (gh CLI auth + error handling)
- `github-actions-query-workflow-runs`: PR #2961 sent for review (query functions + tests)
- `artifacts-for-commit`: Has local commits for find_artifacts_for_commit.py, will land after PRs merge

**PRs in flight:**
- https://github.com/ROCm/TheRock/pull/2771 - gh CLI authentication ✅ MERGED 2026-01-15
- https://github.com/ROCm/TheRock/pull/2961 - gha_query_workflow_runs_for_commit + unit tests ✅ MERGED 2026-01-16

### 2026-01-22 - Prerequisite PRs Merged, Rebase Needed

Both prerequisite PRs are now merged. The `artifacts-for-commit` branch (23 commits) needs rebasing onto current `main`. Most commits should drop automatically since they're already in main via those PRs.

**Branch diffs after rebase should be limited to:**
- `build_tools/find_artifacts_for_commit.py` (new file)
- `build_tools/find_latest_artifacts.py` (new file)
- Possibly minor diffs to `github_actions_utils.py` (older versions of error handling/timeout code that should be resolved in favor of main)

**Cleanup items identified:**
- `find_latest_artifacts.py` calls `check_artifacts_exist()` redundantly — the current `find_artifacts_for_commit()` already calls it internally when iterating workflow runs. The `find_latest_artifacts` code at line 124 checks again after getting a result.
- Logging verbosity: still using raw `print()` to stderr; should switch to Python `logging` module.

**Parallel work: `run-outputs-layout` (PR #3000)**
- Introduces `RunOutputRoot` to consolidate S3 path computation
- Lists "Migrate `find_artifacts_for_commit.py` to use `RunOutputRoot`" as future work
- Landing the artifact scripts with `ArtifactRunInfo` is fine for now — migration happens separately
- Expect merge conflicts between these branches when both land, but they're in different files so should be manageable

### 2026-01-23 - Unit Tests Added

**Tests created:**
- `build_tools/tests/find_artifacts_for_commit_test.py` — 4 tests for `find_artifacts_for_commit()`
- `build_tools/tests/find_latest_artifacts_test.py` — 3 tests for `find_latest_artifacts()`

**Mocking strategy:**
- `check_if_artifacts_exist()` is mocked in all tests (S3 retention policy means artifacts may be deleted for older runs)
- `get_recent_branch_commits_via_api()` is mocked in find_latest_artifacts tests (controls which commits are searched)
- GitHub API calls (`gha_query_workflow_runs_for_commit`, `retrieve_bucket_info`) are NOT mocked — they hit the real API
- Tests use `_skip_unless_authenticated_github_api_is_available` decorator

**Pinned test data:**
- `find_artifacts_for_commit_test.py`: Uses `77f0cb21...` (main, run 20083647898) and `62bc1eaa...` (fork, run 20384488184)
- `find_latest_artifacts_test.py`: Uses two consecutive main commits: `5ea91c38...` (run 21249928112) and `02946b22...` (run 21243829022)

**Commits on `artifacts-for-commit` branch:**
- `4810e7bf` - Add tests for find_artifacts_for_commit and find_latest_artifacts
- `d224b48a` - Cleanup find_artifacts_for_commit_test (user edit)
- `b12cf34c` - Use consecutive main branch commits in find_latest_artifacts tests

**Open questions for next session:**
- `detect_repo_from_git()` concern is narrower than initially thought: in CI, `retrieve_bucket_info()` uses the `GITHUB_REPOSITORY` env var (which is always correct). Locally, `detect_repo_from_git()` would always return `ROCm/TheRock` since that's the repo you'd be in. For rocm-libraries usage, `--repo` would need to be explicit — but that's the expected CI usage pattern anyway.
- Need rocm-libraries test cases to exercise different workflow/bucket paths.

### 2026-01-26 - PR Sent for Review

**Work completed:**
- Added test for `gha_query_recent_branch_commits()` in `github_actions_utils_test.py`
- Added rocm-libraries test case to `find_artifacts_for_commit_test.py` (commit `ab692342`, run `21365647639`)
- Fixed mock paths in `find_latest_artifacts_test.py` after function rename
- Fixed typos in scripts
- Added documentation to `docs/development/installing_artifacts.md`:
  - New "Finding Run IDs Programmatically" subsection
  - Examples for both scripts
  - TODO comment about adding `--commit` to `install_rocm_from_artifacts.py`

**PR sent:** https://github.com/ROCm/TheRock/pull/3093

**Branch state:** 12 commits, all tests passing, review approved (local_008)

## Next Steps / Plan

**Done:**
1. [x] Rebase `github_actions_utils.py` changes onto `github-actions-gh-authentication` branch
2. [x] Add unit tests for new functions (`gha_query_workflow_runs_for_commit`, updated `retrieve_bucket_info`)
3. [x] Send PR for review → PR #2961
4. [x] Rebase `artifacts-for-commit` onto current `main` (drop merged commits)
5. [x] Add unit tests for `find_artifacts_for_commit.py` and `find_latest_artifacts.py`
6. [x] Add test case(s) for rocm-libraries usage (different workflow, different bucket)
7. [x] Add documentation to `docs/development/installing_artifacts.md`
8. [x] Send PR for review → **PR #3093** https://github.com/ROCm/TheRock/pull/3093

**Deferred / Future work:**
- [ ] Logging: switch from `print()` to Python `logging` module (can be follow-up)
- [ ] Verify `detect_repo_from_git()` default behavior (low priority - works correctly in practice)

**After artifact scripts land:**
- [ ] Add `--commit` option to `install_rocm_from_artifacts.py` (see TODO in installing_artifacts.md)
- [ ] Scenario 2: Fallback search for baseline commit with artifacts
- [ ] Consolidate `ArtifactRunInfo` with `RunOutputRoot` (after PR #3000 lands)

### 2026-01-26 - Rate Limit Error Handling (PR review feedback)

**Problem identified:** REST API 403 responses for rate limits showed misleading "Check if your token has the necessary permissions" message instead of indicating rate limiting.

**Changes made:**
- `github_actions_utils.py`: Read HTTPError response body, detect "rate limit" text, provide actionable message with `gh auth login` guidance and docs link
- `find_artifacts_for_commit.py`: Now raises `GitHubAPIError` instead of catching and returning `None`. This distinguishes "no artifacts" (None) from "couldn't check" (exception). CLI `main()` catches and exits with code 2.
- `find_latest_artifacts.py`: Same pattern - propagates `GitHubAPIError` from both commit listing and artifact checking. CLI catches with exit code 2.
- Kept `--max-commits` argument after discussion - error messages are clearer when user controls the search depth.

**Tests added:**
- `test_rest_api_rate_limit_error_provides_helpful_message` - verifies REST API rate limit detection
- `test_gh_cli_rate_limit_error_passes_through_message` - verifies gh CLI passes through message
- `test_rate_limit_error_raises_exception` - verifies exception propagation in find_artifacts_for_commit

**Commit:** `9f90be04` - "Improve rate limit error handling in artifact scripts"

**Branch state:** 13 commits on `artifacts-for-commit`, PR #3093 still under review
