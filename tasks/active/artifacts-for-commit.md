---
repositories:
  - therock
---

# Artifacts for Commit

**Status:** In progress
**Priority:** P1 (High)
**Started:** 2026-01-13
**Target:** TBD

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
../TheRock/build_tools/fetch_artifacts.py   # Existing S3 artifact fetcher
../TheRock/build_tools/github_actions/github_actions_utils.py  # GitHub API utils
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

**1. `gh` CLI fallback for `github_actions_utils.py`**

`github_actions_utils.py` should support both:
- GitHub REST API (current: `gha_send_request()` with `GITHUB_TOKEN`)
- `gh` CLI fallback (when REST API auth unavailable but `gh` is authenticated)

This would make local development easier when user has `gh auth login` but no `GITHUB_TOKEN` env var.

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

## Investigation Notes

### 2026-01-13 - Task Created

Extracted from submodule-bisect-tooling as a focused sub-task. Ready to implement piece by piece.

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

## Next Steps

1. [x] Define script interface and core functions
2. [x] Implement `query_workflow_run()` using github_actions_utils
3. [x] Implement S3 bucket/path resolution using `retrieve_bucket_info()`
4. [x] Implement CLI with argparse and human-readable output
5. [x] Test with real commits
6. [x] Add `detect_repo_from_git()` and `infer_workflow_for_repo()` helpers
7. [ ] Commit latest changes (field renames, `external_repo`, computed `s3_path`)
8. [ ] Scenario 2: Fallback search for baseline commit with artifacts
9. [ ] Consolidate with `BucketMetadata` in `fetch_artifacts.py`
10. [ ] Add `gh` CLI fallback to `github_actions_utils.py` (separate task)
