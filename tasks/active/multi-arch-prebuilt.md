---
repositories:
  - therock
---

# Multi-Arch Stage-Aware Prebuilt Artifacts

- **Status:** Not started
- **Priority:** P1 (High)
- **Started:** 2026-02-26
- **Target:** TBD

## Overview

Enable multi-arch CI workflows to selectively use prebuilt artifacts from prior
workflow runs on a per-stage basis, rather than the current all-or-nothing
`use_prebuilt_artifacts` boolean. This dramatically reduces CI time for PRs that
only affect a subset of the build (e.g. a rocm-libraries PR can skip rebuilding
foundation and compiler-runtime stages).

Issue: https://github.com/ROCm/TheRock/issues/3399

## Goals

- [ ] Multi-arch stage pipeline can fetch prebuilt artifacts for specific stages
      from a prior workflow run while building other stages fresh
- [ ] Downstream stages (tests, packaging) work transparently regardless of
      which stages used prebuilts
- [ ] Mechanism for specifying which baseline workflow run to use (initially
      manual/hardcoded, later automatic)
- [ ] Source-set-aware stage selection: given modified files, determine which
      stages need rebuilding vs. which can use prebuilts

## Context

### Background

The multi-arch CI pipeline (`multi_arch_build_portable_linux.yml`) currently
has an all-or-nothing `use_prebuilt_artifacts` flag. If true, the entire build
is skipped. If false, every stage builds from scratch. The motivating scenarios
from issue #3399:

1. **rocm-libraries PRs**: Only need to rebuild `math-libs` and `comm-libs`.
   Foundation and compiler-runtime can use prebuilts.
2. **Packaging-only PRs in TheRock**: No stages need rebuilding.
3. **External-builds PRs in TheRock**: Only need prebuilt rocm Python packages.

### Related Work

- `artifacts-for-commit` — provides `find_artifacts_for_commit.py` and
  `find_latest_artifacts.py` for locating baseline workflow runs (PR #3093,
  under review)
- `configure-ci-refactor` — cleaning up `configure_ci.py` for extensibility;
  issue #3399 is the motivating use case for the refactor
- BUILD_TOPOLOGY.toml source sets — define which git submodules map to which
  artifact groups and stages

### Directories/Files Involved

```
# Workflows
.github/workflows/multi_arch_ci.yml
.github/workflows/multi_arch_ci_linux.yml
.github/workflows/multi_arch_build_portable_linux.yml
.github/workflows/multi_arch_build_portable_linux_artifacts.yml
.github/workflows/multi_arch_ci_windows.yml
.github/workflows/multi_arch_build_windows.yml
.github/workflows/multi_arch_build_windows_artifacts.yml
.github/workflows/setup.yml

# Scripts
build_tools/github_actions/configure_ci.py
build_tools/find_artifacts_for_commit.py
build_tools/find_latest_artifacts.py
build_tools/artifact_manager.py
build_tools/configure_stage.py

# Configuration
BUILD_TOPOLOGY.toml
```

### Current Stage Pipeline (Linux)

```
foundation (generic)
  └─> compiler-runtime (generic)
        ├─> math-libs (per-arch matrix)
        ├─> comm-libs (per-arch matrix)
        ├─> debug-tools (generic)
        ├─> dctools-core (generic)
        ├─> profiler-apps (generic)
        └─> media-libs (generic)
```

Each stage job currently:
1. Fetches inbound artifacts via `artifact_manager.py fetch --run-id=<github.run_id> --stage=<name>`
2. Builds its artifacts
3. Pushes artifacts via `artifact_manager.py push --run-id=<github.run_id> --stage=<name>`

### Current Prebuilt Mechanism

- Single boolean per platform: `linux_use_prebuilt_artifacts` / `windows_use_prebuilt_artifacts`
- If true, the entire `build_multi_arch_stages` job is skipped
- An `artifact_run_id` input is passed to downstream jobs (tests, packaging)
- Downstream jobs use `inputs.artifact_run_id != '' && inputs.artifact_run_id || github.run_id`
- TODO comment in `ci_linux.yml` asks about a "passthrough" approach

## Design

### Phase 1: Per-Stage Prebuilt Capability (The Plumbing)

Make the multi-arch stage pipeline capable of running individual stages in
"prebuilt mode" — fetching artifacts from a specified baseline run_id and
re-publishing them under the current run_id, so downstream stages and jobs
see a uniform artifact set.

**Key insight (from Scott):** This can be done independently from choosing a
baseline run automatically. We can hardcode a baseline run_id for testing, or
pass one via `workflow_dispatch` input.

#### Approach: Fetch-and-Republish

A stage running in prebuilt mode would:
1. Fetch artifacts from the baseline run_id (via `artifact_manager.py fetch`)
2. Push those same artifacts under the current run_id (via `artifact_manager.py push`)
3. Skip the actual build (no cmake configure, no ninja)

This makes prebuilt stages **transparent to downstream consumers** — they
always fetch from `github.run_id` regardless of whether a stage built fresh
or used prebuilts.

**Alternatives considered:**
- **Mixed run_id approach**: Downstream stages fetch from different run_ids
  for different inbound stages. More efficient (no S3 copy) but requires
  changes to `artifact_manager.py` (per-stage run_id mapping) and all
  downstream plumbing. Much higher complexity.
- **Symlink/redirect on S3**: Create an S3 redirect or manifest pointing to
  the baseline artifacts. Efficient but requires S3 changes and new fetching
  logic.

#### Workflow Changes

New inputs to `multi_arch_build_portable_linux.yml`:
- `prebuilt_stages` (string, default: ""): Comma-separated list of stage names
  to use prebuilts for (e.g., `"foundation,compiler-runtime"`)
- `baseline_run_id` (string, default: ""): The run_id to fetch prebuilt
  artifacts from. Required if `prebuilt_stages` is non-empty.

Per-stage job logic (in `multi_arch_build_portable_linux_artifacts.yml` or
a wrapper):
```yaml
# Pseudocode
if stage_name in prebuilt_stages:
  artifact_manager.py fetch --run-id=$baseline_run_id --stage=$stage_name
  artifact_manager.py push --run-id=$github.run_id --stage=$stage_name
else:
  # existing build logic
  artifact_manager.py fetch --run-id=$github.run_id --stage=$stage_name --bootstrap
  cmake + ninja
  artifact_manager.py push --run-id=$github.run_id --stage=$stage_name
```

### Phase 2: Baseline Run Selection (The Policy)

Given a PR or branch, determine which baseline run_id to use.

#### For TheRock PRs

1. Find the merge-base commit with `main`
2. Walk back through `main` commits to find one with successful CI
3. Use `find_artifacts_for_commit.py` or `find_latest_artifacts.py`

#### For rocm-libraries / rocm-systems PRs

The baseline is the TheRock ref used to checkout dependencies. The CI
workflow in these repos checks out a specific commit of TheRock, which
determines which compiler/runtime versions are used. That TheRock commit
should have corresponding CI artifacts.

Initially this could be hardcoded or passed as a workflow input.

#### For Packaging-Only / Build-Tools PRs

All stages use prebuilts. The baseline is the most recent successful CI
run on the base branch.

### Phase 3: Source-Set-Aware Stage Selection

Use BUILD_TOPOLOGY.toml source sets to automatically determine which stages
are affected by a PR's changes.

1. Get list of changed files from PR (via GitHub API or `git diff`)
2. Map changed files to source sets (BUILD_TOPOLOGY.toml `[source_sets.*]`)
3. Map source sets to artifact groups (via `source_set` fields in artifacts)
4. Map artifact groups to stages
5. Stages not affected by any changes use prebuilts

This is the `configure_ci.py` integration piece — it would output per-stage
prebuilt decisions alongside the existing matrix.

### Phase 4: Labels and Manual Controls

- `ci:rebuild-all` label to force all stages to build fresh
- `ci:prebuilt-stages=foundation,compiler-runtime` for explicit control
- `workflow_dispatch` inputs for manual testing

## Open Questions

### Q1: Fetch-and-republish efficiency

The fetch-and-republish approach copies artifacts through the runner (S3 →
runner → S3). For large stages like `compiler-runtime` (amd-llvm is big),
this could be slow. Is there a way to do server-side S3 copy? Or is the
copy time acceptable given we're still saving the build time?

### Q2: Per-arch stage prebuilts

For per-arch stages (math-libs, comm-libs), do we need per-family prebuilt
decisions? Example: a PR modifies rocBLAS for gfx94X but not gfx110X. Could
gfx110X use prebuilt math-libs while gfx94X rebuilds? Or is per-stage
granularity sufficient for now?

### Q3: Artifact compatibility

When using prebuilt artifacts from a prior run, how do we ensure they're
compatible with the current checkout? If `foundation` artifacts change their
ABI, downstream stages need to rebuild. BUILD_TOPOLOGY.toml dependencies
define this, but do we need runtime validation?

### Q4: Interaction with the existing `use_prebuilt_artifacts` flag

Should the existing all-or-nothing flag be preserved as a shortcut (set all
stages to prebuilt), or replaced entirely by the per-stage mechanism?

### Q5: Reusable workflow input limits

GitHub Actions reusable workflows have a limit of 10 inputs. The stage
pipeline workflows already have several inputs. Can we fit `prebuilt_stages`
and `baseline_run_id` without hitting the limit?

## Investigation Notes

### 2026-02-26 - Task Created

Research completed on issue #3399, current multi-arch CI structure,
BUILD_TOPOLOGY.toml stages, and related tasks. Key findings:

- **10 stages** defined in BUILD_TOPOLOGY.toml, 8 active in the Linux
  pipeline, ~4 in Windows
- **Existing per-stage job structure** already does fetch → build → push;
  the fetch-and-republish approach fits naturally
- **`artifact_manager.py`** already supports `--run-id` and `--stage`,
  so the fetch side is ready; need to verify the push side can handle
  artifacts that were fetched rather than built
- **`configure_ci.py`** currently passes `use_prebuilt_artifacts` through
  unchanged; the configure-ci-refactor task would create a better
  insertion point for per-stage decisions
- **PR #3093** (artifacts-for-commit) provides `find_latest_artifacts.py`
  which is the natural tool for baseline run selection

## Decisions & Trade-offs

(to be filled as we make decisions)

## Blockers & Issues

### Dependencies
- PR #3093 (artifacts-for-commit scripts) — needed for Phase 2 baseline
  run selection, not strictly needed for Phase 1
- configure-ci-refactor — nice-to-have for Phase 3 insertion point,
  not blocking

## Resources & References

- [Issue #3399](https://github.com/ROCm/TheRock/issues/3399)
- [BUILD_TOPOLOGY.toml](../TheRock/BUILD_TOPOLOGY.toml)
- [multi_arch_build_portable_linux.yml](../TheRock/.github/workflows/multi_arch_build_portable_linux.yml)
- [multi_arch_build_portable_linux_artifacts.yml](../TheRock/.github/workflows/multi_arch_build_portable_linux_artifacts.yml)
- [artifact_manager.py](../TheRock/build_tools/artifact_manager.py)
- [configure_ci.py](../TheRock/build_tools/github_actions/configure_ci.py)
- [PR #3093](https://github.com/ROCm/TheRock/pull/3093) — find_artifacts_for_commit

## Next Steps

1. [ ] Validate fetch-and-republish approach: check that `artifact_manager.py push`
       works with fetched (not built) artifacts
2. [ ] Prototype Phase 1 workflow changes on a branch
3. [ ] Test with a hardcoded baseline run_id via workflow_dispatch
4. [ ] Design `configure_ci.py` integration for automatic stage selection
