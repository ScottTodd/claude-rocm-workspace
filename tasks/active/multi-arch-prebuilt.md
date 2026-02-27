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

#### Approach: Copy-and-Early-Exit Inside the Per-Stage Workflow

The per-stage reusable workflow (`multi_arch_build_portable_linux_artifacts.yml`)
gains two new inputs: `use_prebuilt` (boolean) and `baseline_run_id` (string).
When `use_prebuilt` is true, the workflow:

1. Checks out the repo (needed for scripts)
2. Installs python deps (needed for artifact_manager)
3. Configures AWS credentials
4. Fetches artifacts from the baseline run_id
5. Pushes them under the current run_id
6. Skips everything else (ccache, source fetch, cmake, build)

The top-level pipeline workflow (`multi_arch_build_portable_linux.yml`) stays
**straight-line** — every stage job runs unconditionally, just as it does today.
The build-vs-copy decision is internal to each stage's reusable workflow.

**Trade-off: VM overhead for prebuilt stages.** Each prebuilt stage still
spins up a runner, pulls the container, and runs a few setup steps (~3-5 min
overhead). For a rocm-libraries PR skipping foundation + compiler-runtime,
that's ~6-10 minutes of overhead to save 1-4+ hours of build time.

**Alternatives considered:**
- **`if:` conditions at the pipeline level**: Skip prebuilt stage jobs entirely
  (no VM cost) but pollutes the pipeline DAG with conditional logic. This is
  the pattern used in non-multi-arch `ci_linux.yml` and is fragile — exactly
  what multi-arch was designed to avoid.
- **Mixed run_id approach**: Downstream stages fetch from different run_ids
  for different inbound stages. More efficient (no S3 copy) but requires
  changes to `artifact_manager.py` (per-stage run_id mapping) and all
  downstream plumbing. Much higher complexity.
- **S3 server-side copy**: Use S3 CopyObject API to copy artifacts between
  run_id prefixes without downloading to the runner. Could reduce the
  overhead significantly. Worth investigating as a Phase 1 optimization but
  not essential for initial implementation.

#### Workflow Input Changes

**`multi_arch_build_portable_linux_artifacts.yml`** (per-stage, currently 6 inputs):
- Add `use_prebuilt` (boolean, default: false)
- Add `baseline_run_id` (string, default: ""): run_id to fetch prebuilt
  artifacts from

That brings it to 8/10 inputs.

**`multi_arch_build_portable_linux.yml`** (pipeline, currently 12 inputs):
- Add `prebuilt_stages` (string, default: ""): comma-separated stage names
- Add `baseline_run_id` (string, default: "")

Each stage call passes `use_prebuilt: contains(inputs.prebuilt_stages, 'foundation')`
(or similar parsing) and `baseline_run_id: inputs.baseline_run_id`.

**Issue:** `multi_arch_build_portable_linux.yml` already has 12 inputs, which
is over the GitHub Actions limit of 10 for reusable workflows. Need to check
how it currently works — it may be using `workflow_call` without the limit,
or some inputs may need consolidation.

#### Per-Stage Workflow Pseudocode

```yaml
steps:
  - name: Checkout Repository
    uses: actions/checkout@...

  - name: Install python deps
    run: pip install -r requirements.txt

  - name: Configure AWS Credentials
    if: ${{ !github.event.pull_request.head.repo.fork }}
    uses: aws-actions/configure-aws-credentials@...

  # === PREBUILT PATH ===
  - name: Copy prebuilt artifacts
    if: ${{ inputs.use_prebuilt && !github.event.pull_request.head.repo.fork }}
    run: |
      python build_tools/artifact_manager.py fetch \
        --run-id=${{ inputs.baseline_run_id }} \
        --stage="${STAGE_NAME}" \
        --amdgpu-families="${{ inputs.amdgpu_family }}" \
        --output-dir="${BUILD_DIR}"
      python build_tools/artifact_manager.py push \
        --run-id=${{ github.run_id }} \
        --stage="${STAGE_NAME}" \
        --build-dir="${BUILD_DIR}"

  # === BUILD PATH (all gated on !use_prebuilt) ===
  - name: Fetch inbound artifacts
    if: ${{ !inputs.use_prebuilt && !github.event.pull_request.head.repo.fork }}
    run: |
      python build_tools/artifact_manager.py fetch \
        --run-id=${{ github.run_id }} ...

  - name: Fetch sources
    if: ${{ !inputs.use_prebuilt }}
    ...
  # (remaining build steps all gated on !inputs.use_prebuilt)
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

### Q1: S3 copy efficiency

The copy-and-republish approach downloads artifacts to the runner then
re-uploads (S3 → runner → S3). For large stages like `compiler-runtime`
(amd-llvm is large), this adds transfer time. S3 server-side copy
(`CopyObject` API or `aws s3 cp --recursive`) could avoid the round-trip.
Worth investigating whether `artifact_manager.py` could support a
`copy --source-run-id=X --dest-run-id=Y --stage=Z` command.

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

### Q5: Pipeline workflow input count

`multi_arch_build_portable_linux.yml` already has 12 `workflow_call` inputs.
GitHub's documented limit is 10 for reusable workflows. Need to verify
whether this is actually enforced (it may have been raised or may not apply
to all input types). If it is enforced, we need to consolidate existing
inputs before adding `prebuilt_stages` and `baseline_run_id`.

The per-stage workflow (`multi_arch_build_portable_linux_artifacts.yml`) has
6 inputs, so adding 2 more (8 total) is fine.

### Q6: `artifact_manager.py` fetch/push mismatch for copy-forward

**Answered (partially):** There is a semantic mismatch between fetch and push:
- `fetch --stage=X` downloads **inbound** artifacts (dependencies from prior stages)
- `push --stage=X` uploads **produced** artifacts (this stage's outputs)

For copy-forward, we need to fetch the **produced** artifacts of stage X from
the baseline run and push them under the current run. `fetch` doesn't have
this mode — it only fetches inbound dependencies.

**Options:**
1. Add `artifact_manager.py copy --source-run-id=X --dest-run-id=Y --stage=Z`
   that copies produced artifacts between runs (could use S3 server-side copy)
2. Add `--fetch-produced` flag to `fetch` that gets produced artifacts instead
   of inbound
3. Compute artifact names from topology and construct S3 paths directly in the
   workflow script

Option 1 is probably cleanest — it's a distinct operation with clear semantics
and could use `CopyObject` for efficiency (no download/upload round-trip).

**Also confirmed:** When using normal fetch (not `--bootstrap`), artifacts land
in `build/artifacts/{name}_{comp}_{family}/` which is exactly where push looks.
So a download-then-upload path through the runner is mechanically compatible,
just semantically awkward with the current CLI.

## Investigation Notes

### 2026-02-26 - Task Created

Research completed on issue #3399, current multi-arch CI structure,
BUILD_TOPOLOGY.toml stages, and related tasks. Key findings:

- **10 stages** defined in BUILD_TOPOLOGY.toml, 8 active in the Linux
  pipeline, ~4 in Windows
- **Existing per-stage job structure** already does fetch → build → push;
  the copy-and-early-exit approach fits naturally
- **`configure_ci.py`** currently passes `use_prebuilt_artifacts` through
  unchanged; the configure-ci-refactor task would create a better
  insertion point for per-stage decisions
- **PR #3093** (artifacts-for-commit) provides `find_latest_artifacts.py`
  which is the natural tool for baseline run selection

**Design decision:** Copy-and-early-exit inside the per-stage reusable
workflow, keeping the pipeline DAG straight-line and unconditional. Each
stage job always runs; the reusable workflow decides internally whether to
build or copy-forward. Pays VM startup overhead per prebuilt stage but
avoids `if:` conditions at the pipeline level.

**Key technical finding:** `artifact_manager.py` fetch/push have a semantic
mismatch for copy-forward — `fetch --stage=X` gets inbound artifacts, not
produced artifacts. Need a new `copy` subcommand or `--fetch-produced` mode.
S3 server-side copy (`CopyObject`) would avoid the download-upload round-trip.

**Open threads for next session:**
- Scott has baseline selection ideas not yet captured (Phase 2)
- Need to check the 12-input situation on `multi_arch_build_portable_linux.yml`
  (over GitHub's documented 10-input limit for reusable workflows — is it
  enforced?)
- Priority of S3 server-side copy vs download-upload through runner
- Scott mentioned hardcoding baseline run_ids for rocm-libraries and
  rocm-systems repos as a starting point

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
