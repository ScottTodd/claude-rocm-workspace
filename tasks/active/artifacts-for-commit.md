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

## Investigation Notes

### 2026-01-13 - Task Created

Extracted from submodule-bisect-tooling as a focused sub-task. Ready to implement piece by piece.

## Next Steps

1. [ ] Define step-by-step functions/scripts to implement
2. [ ] Start implementation
