---
repositories:
  - therock
---

# Multi-Arch Stage-Aware Prebuilt Artifacts

- **Status:** In progress (Phase 1 — workflow plumbing complete, prototype tested)
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

#### Approach: Copy in Setup Job with S3 Server-Side Copy

The existing setup job (which already runs before all build stages) gains a
copy step. When `prebuilt_stages` and `baseline_run_id` are provided, setup
runs `artifact_manager.py copy` to server-side copy all prebuilt stages'
artifacts from the baseline run_id to the current run_id in S3. Build stages
then proceed normally — they fetch inbound artifacts via the usual
`artifact_manager.py fetch --run-id=${{ github.run_id }}` path and find the
copied artifacts waiting.

Stages whose artifacts were pre-copied are skipped (via `if:` on the stage
job). Stages that need fresh builds run unchanged.

```
setup (configure CI matrix + copy prebuilt foundation & compiler-runtime)
  └─> math-libs (builds fresh, fetches inbound from current run_id)
  └─> comm-libs (builds fresh)
  └─> ... (other stages that need building)
```

**Why this approach:**
- **No extra job.** Reuses the existing setup job that all build stages
  already depend on. No new dependency edges, no extra runner spin-up.
- **No per-stage VM overhead.** The per-stage copy-and-early-exit alternative
  would spin up a runner, pull the container, and run setup for each prebuilt
  stage (~3-5 min each). Copying in setup does all stages in one shot.
- **S3 server-side copy is fast.** `artifact_manager.py copy` uses
  `s3_client.copy()` (CopyObject) — no download/upload round-trip through
  the runner. Expected to add seconds, not minutes, to setup.
- **Build stages stay unchanged.** No new inputs or conditions needed on
  the per-stage reusable workflow.
- **Splittable later.** If copy turns out to be slow in practice, the copy
  step can be extracted to a parallel job without changing any per-stage
  workflow logic.

**Alternatives considered:**
- **Separate `copy-prebuilt-stages` job**: Dedicated job before build stages.
  Cleaner separation of concerns, but adds a runner spin-up and extra
  plumbing (checkout, pip install, AWS creds) that setup already has. Can
  migrate to this if copy latency becomes a problem.
- **Copy-and-early-exit inside per-stage workflow**: Each prebuilt stage
  spins up a runner, copies its own artifacts, exits. Pays VM startup
  overhead per prebuilt stage. Rejected due to the overhead cost for
  chained stages (foundation → compiler-runtime).
- **Mixed run_id approach**: Downstream stages fetch from different run_ids
  for different inbound stages. Most efficient (no copy at all) but requires
  significant changes to artifact_manager and all consumers. Deferred as a
  potential future optimization.

#### Workflow Changes

**`multi_arch_build_portable_linux.yml`** (pipeline):
- Add `prebuilt_stages` input (string, default: ""): comma-separated stage names
- Add `baseline_run_id` input (string, default: "")
- Add `if:` conditions on stage jobs to skip stages listed in `prebuilt_stages`

**Issue:** `multi_arch_build_portable_linux.yml` already has 12 `workflow_call`
inputs, which is over GitHub's documented limit of 10 for reusable workflows.
Need to check whether this is enforced. If so, inputs need consolidation
before adding `prebuilt_stages` and `baseline_run_id`.

**`setup.yml`** (or wherever the setup job is defined):
- Add copy step after CI configuration, gated on `prebuilt_stages != ''`
- Needs AWS credentials (may already be configured) and python deps

**`multi_arch_build_portable_linux_artifacts.yml`** (per-stage): No changes
needed. It continues to fetch/build/push as before.

#### Setup Job Copy Step Pseudocode

```yaml
# Inside existing setup job, after CI matrix configuration
- name: Copy prebuilt artifacts
  if: ${{ inputs.prebuilt_stages != '' && inputs.baseline_run_id != '' }}
  run: |
    python build_tools/artifact_manager.py copy \
      --source-run-id=${{ inputs.baseline_run_id }} \
      --run-id=${{ github.run_id }} \
      --stages=${{ inputs.prebuilt_stages }} \
      --amdgpu-families="${{ inputs.amdgpu_families }}"
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

**Open threads:**
- Need to check the 12-input situation on `multi_arch_build_portable_linux.yml`
  (over GitHub's documented 10-input limit for reusable workflows — is it
  enforced?)
- Scott mentioned hardcoding baseline run_ids for rocm-libraries and
  rocm-systems repos as a starting point

### 2026-03-04 - Workflow plumbing and prototype testing

Wired copy into the multi-arch CI pipeline and ran prototype tests via
workflow_dispatch. Branch `multi-arch-prebuilt-2` now has 10 commits.

**What was built (session commits):**
- `0bd27efc` Wire per-stage prebuilt artifacts into multi-arch CI workflow
- `e083ca9e` Move prebuilt copy to separate job, keep setup.yml lightweight
- `f74e2282` Remove copy_prebuilt_stages.py wrapper, use artifact_manager directly
- `08acb685` Move copy job into per-platform orchestrator workflows
- `36fbeb7f` Standardize --amdgpu-families on semicolon separator
- `cf71140a` Add test for semicolon-separated --amdgpu-families
- `3b4e4517` Add setup-python to copy_prebuilt_stages job
- `e6ae7709` Allow stage jobs to run when predecessor stages are skipped

**Architecture decisions made during session:**
- Copy job lives in per-platform orchestrators (multi_arch_ci_linux.yml),
  not in setup.yml or multi_arch_ci.yml — each platform copies its own
  artifacts independently.
- Eliminated the copy_prebuilt_stages.py wrapper script — the copy job
  calls artifact_manager.py directly, using dist_amdgpu_families input.
- Standardized --amdgpu-families on semicolons (matching configure_stage.py
  convention) instead of commas, since no live callers used commas with
  multiple values.
- setup.yml stays on ubuntu-24.04 with read-only permissions — prebuilt_stages
  input is a passthrough for future heuristics-driven defaults.

**Prototype test results:**
- Baseline run: 22655391643 (manually identified, no automated lookup yet)
- Copy job: 185 artifacts + 185 sha256sums copied via S3 server-side copy in
  ~16 seconds (plus runner queue time). Logging shows stage→artifact mapping,
  source/dest S3 paths, and per-file copy progress.
- All 8 stage skip conditions work correctly with !cancelled() && !failure()
- Concurrency group collisions between dispatch runs confirmed as expected —
  tracked in tasks/active/concurrency-groups.md

**Bugs found and fixed:**
- `pip: command not found` on azure-linux-scale-rocm runner → added
  actions/setup-python (3b4e4517)
- Downstream stages skipped when predecessor was skipped (prebuilt) →
  added !cancelled() && !failure() to if: conditions (e6ae7709)

### 2026-03-02 - copy subcommand implemented

Branch `multi-arch-prebuilt-1`, commits `d9febabe` and `9d1ae32c`.

**What was built:**
- `ArtifactBackend.copy_artifact(artifact_key, source_backend)` — abstract
  method with S3Backend (server-side copy) and LocalDirectoryBackend
  (shutil.copy2) implementations. Runtime isinstance checks enforce
  same-backend-type constraint.
- `artifact_manager.py copy` subcommand — copies all produced artifacts for
  a stage from `--source-run-id` to `--run-id`. Source bucket resolved via
  `retrieve_bucket_info(workflow_run_id=...)`. Parallel via ThreadPoolExecutor.
  sha256sum files copied best-effort. Supports `--dry-run`.
- `_create_source_backend()` helper — separate from `create_backend_from_env`
  because the source needs its own bucket resolution (different workflow run
  may be in a different bucket).
- 12 new tests across artifact_backend_test.py and artifact_manager_tool_test.py.

**What to review before PR:**
- Scott mentioned he'd have comments after the commit — review and refine
- sha256sum best-effort approach: currently runs as a separate pass after
  main artifacts copy. Could be simplified or made more robust.
- `_create_source_backend` is a standalone function in artifact_manager.py,
  not on the backend module. Consider whether it belongs elsewhere.

**Open threads for next session:**
- Review and refine the copy code, send as PR
- Continue vertical spike: wire copy into workflow for "prebuilt
  compiler-runtime → build math-libs fresh" scenario
- Still undecided: single copy job upfront vs per-stage copy-and-exit

### 2026-03-05 - Copy subcommand PR posted

Synced `multi-arch-prebuilt-1` with `main` (merge commit 0352e56e). The
merge brought in #3596 (WorkflowOutputRoot refactor) which changed
`S3Backend`/`LocalDirectoryBackend` constructors and moved
`retrieve_bucket_info` into `WorkflowOutputRoot`. Updated
`_create_source_backend` and 13 failing tests to use the new API
(commit 2a0cc338). Self-review in `reviews/local_018_multi-arch-prebuilt-1.md`.

Posted as PR #3801. Semicolon delimiter changes from `multi-arch-prebuilt-2`
left out intentionally — they'll go in the workflow wiring PR.

### 2026-03-06 - PR #3801 review feedback addressed

Review from HereThereBeDragons. Pushed 3 commits addressing feedback:

- `10dfea29` — Widened `copy_artifact` type hints to `ArtifactBackend`
  (runtime isinstance checks already enforce same-backend-type). Replaced
  `getattr(args, "local_staging_dir", None)` with direct `args.local_staging_dir`.
  Added failed artifact names to error output. (Led to style guide PR #3826
  for the argparse `getattr` anti-pattern.)
- `57ce8a0b` — Moved sha256sum copying into `copy_artifact` on both backends
  for consistency with `download_artifact`/`upload_artifact`. Removed separate
  sha256sum pass from `do_copy`. Added `test_copy_artifact_without_sha256sum`.
- `e28882f2` — Added comment clarifying why `do_copy` validates multiple
  stages in a loop vs single-stage validation in `do_fetch`/`do_push`.

Reviewer also asked about listing available stages in source — deferred as
future work. `list-stages` subcommand already shows topology stages, and
`copy` validates `--stage` against that list.

Also verified local copy output with real artifacts (no sha256sums) from
run 22703255745 — output is clean after the refactor.

## Decisions & Trade-offs

### Where to run the copy: setup job vs separate job vs per-stage
**Decided: copy in setup job.** S3 server-side copy is expected to be fast
(seconds, not minutes) since CopyObject doesn't transfer data through the
runner. Setup already has checkout, python deps, and AWS creds, and all build
stages already depend on it — so no new plumbing needed. If copy turns out
to be slow, it can be extracted to a parallel job later without changing
per-stage workflows. Per-stage copy-and-early-exit was rejected due to VM
startup overhead (~3-5 min each) for chained stages.

**Runner caveat:** Setup needs S3 write access for the copy, which ubuntu-24.04
doesn't have reliably. For the prototype, setup uses our hosted build runners.
Long-term, consider a lightweight self-hosted runner with the right IAM role,
or splitting copy to a separate job if queue times are a problem.

### S3 server-side copy
Confirmed: `s3_client.copy()` (boto3 high-level transfer manager) handles
server-side copy with automatic multipart for >5GB objects. No download
through the runner. Cross-bucket supported via `CopySource.Bucket`.

### Source bucket resolution
Source bucket is NOT passed explicitly. `retrieve_bucket_info(workflow_run_id=...)`
fetches workflow run metadata from GitHub API and derives the correct bucket
and external_repo prefix. This handles cross-repo scenarios (e.g. copying from
`therock-ci-artifacts` to `therock-ci-artifacts-external`).

### No boto3 batch copy API
Investigated S3 Batch Operations — it's designed for millions of objects with
async job semantics. Too heavyweight for ~50-100 artifacts. Using
`ThreadPoolExecutor` + `s3_client.copy()` per-artifact, consistent with
existing fetch/push patterns.

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

1. [x] Implement `artifact_manager.py copy` subcommand (S3-to-S3)
2. [x] Refine copy code — extracted shared helpers, multi-stage support, sha256sum pre-filter
   - Addressed duplication findings from `reviews/local_016_multi-arch-prebuilt-1.md`
   - Reviewed post-refactor in `reviews/local_017_multi-arch-prebuilt-1.md` (APPROVED)
   - Remaining duplication (retry logic, `_create_source_backend`) deferred to
     align with `run-outputs-layout` / `StorageBackend` work
3. [x] Vertical spike: wire copy into multi-arch workflow for
       "prebuilt compiler-runtime → build math-libs" scenario
4. [x] Test with a hardcoded baseline run_id via workflow_dispatch
   - Baseline run: 22655391643
   - Test run (compiler-runtime only): 22685667001 — `pip` not found, fixed
     with setup-python (3b4e4517). Also: foundation ran because it wasn't in
     prebuilt list — user must specify all stages including predecessors for now.
   - Test run (partial skip): 22685667001 — skipped stages worked after
     adding !cancelled() && !failure() (e6ae7709). Some artifact extraction
     failures due to known overlapping artifact files issue (not ours).
   - Test run (all stages prebuilt): 22686926501 — copy job succeeded (185
     artifacts + 185 sha256sums in ~16s). Cancelled prior partial-skip run
     due to concurrency group collision.
5. [x] Send copy subcommand PR
   - PR #3801 (branch `multi-arch-prebuilt-1`)
   - Updated for WorkflowOutputRoot refactor from #3596 (merged from main)
   - Self-review: `reviews/local_018_multi-arch-prebuilt-1.md` (APPROVED)
   - Review feedback addressed: type hints, sha256sum consistency, error reporting

**Immediate next steps (short-term):**

6. [ ] Clean up `use_prebuilt_artifacts` — replace with `prebuilt_stages`
   - Consider "all" sentinel to skip `build_multi_arch_stages` entirely
7. [ ] Fix concurrency groups for parallel dispatch testing
   - See `tasks/active/concurrency-groups.md`
8. [ ] Send workflow plumbing as PR (branch `multi-arch-prebuilt-2`)
   - Includes: copy job in per-platform orchestrators, stage skip conditions,
     semicolon standardization for --amdgpu-families
   - Depends on #3801 merging first

**Medium-term (configure_ci.py integration):**

8. [ ] Auto-expand prebuilt_stages to include predecessor stages
   - Read stage ordering from BUILD_TOPOLOGY.toml in configure_ci.py
9. [ ] Design `configure_ci.py` integration for automatic stage selection
   - setup.yml heuristics for choosing baseline run + stages
10. [ ] Improve copy logging and workflow summary
    - Per-stage artifact counts (not just total)
    - Log source/dest S3 key paths (not just filenames)
    - Explain filtered-out artifacts (e.g. "143 from non-matching families skipped")
    - When configure_ci.py auto-selects stages: write to workflow summary
      explaining what copies were requested and why (so users understand
      the auto-selection logic without inspecting inputs)
11. [ ] Automated baseline run lookup (find_latest_artifacts.py doesn't work
    for multi-arch CI yet — no S3 index page generated)

**Lower priority:**

12. [ ] Add sha256sum downloads to `fetch_artifacts.py` — currently only archives
       are fetched; sha256sum sidecar files exist in S3 but are never downloaded.

## Branches

- `multi-arch-prebuilt-1` — original 5-commit branch (preserved as-is)
- `multi-arch-prebuilt-2` — squashed copy of prebuilt-1, used for continued work
