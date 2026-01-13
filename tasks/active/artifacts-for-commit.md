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

## Investigation Notes

### 2026-01-13 - Task Created

Extracted from submodule-bisect-tooling as a focused sub-task. Ready to implement piece by piece.

## Next Steps

1. [ ] Define step-by-step functions/scripts to implement
2. [ ] Start implementation
