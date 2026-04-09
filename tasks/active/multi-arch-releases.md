# Multi-Arch Release Workflows

**Tracking issue:** https://github.com/ROCm/TheRock/issues/3334
**Status:** In progress — workstream 1 PR #4386 (merged), workstream 1b PR #4408 (in review)

## Goal

Set up multi-arch release workflows that reuse the existing multi-arch CI build
infrastructure, uploading artifacts to release S3 buckets
(`therock-dev-artifacts`, `therock-nightly-artifacts`, etc.) instead of
`therock-ci-artifacts`. The release-specific part then copies/promotes outputs
from the artifacts bucket to package-specific buckets (`therock-dev-tarball`,
`therock-dev-python`).

Release workflows (including dev release dispatch) live in **TheRock** to
keep workflow code close together. **rockrel** has thin wrappers that run
on a schedule and set nightly/prerelease release type — rockrel owns the
schedule/triggering/run history for nightly and prerelease releases, not the
workflow logic itself. Build workflows in TheRock are modified to accept
explicit bucket/role configuration computed once in setup.

## Architecture

### Current multi-arch CI call chain

```
multi_arch_ci.yml                         (top-level, TheRock)
  ├── setup_multi_arch.yml                (matrix + version)
  ├── multi_arch_ci_linux.yml             (Linux orchestrator)
  │     ├── copy_prebuilt_stages          (optional)
  │     ├── multi_arch_build_portable_linux.yml  (stage orchestrator)
  │     │     └── multi_arch_build_portable_linux_artifacts.yml × N stages
  │     ├── test_artifacts_per_family
  │     ├── build_python_packages
  │     ├── test_python_packages_per_family
  │     └── build_pytorch_wheels_per_family
  └── ci_summary
```

### Proposed release job graph

Follows the existing release pattern: separate workflows connected by
`benc-uk/workflow-dispatch`, each independently retryable. Tests are NOT
in the critical path — they run separately (via CI or a dedicated test
workflow). This matches the current non-multi-arch release pipeline.

```
TheRock: multi_arch_release_portable_linux.yml    (release workflow, manual dispatch)
  │
  ├── setup_multi_arch.yml                        (matrix + version + infra config)
  │     └── release_type → computes iam_role, artifacts_bucket
  │
  ├── multi_arch_build_portable_linux.yml         (build all stages)
  │     └── iam_role, artifacts_bucket threaded to each stage job
  │
  ├── publish tarballs → therock-{type}-tarball/{s3_subdir}/
  │
  ├── build python packages → publish python → therock-{type}-python/{s3_subdir}/
  │
  ├── dispatch: pytorch wheels workflow (per-family)
  ├── dispatch: jax wheels workflow (per-family)
  └── dispatch: native packages workflow (deb + rpm)

rockrel: multi_arch_release_portable_linux.yml    (thin wrapper, schedule only)
  └── calls TheRock workflow with release_type=nightly (or prerelease)
```

Each dispatched workflow receives `run_id`, `release_type`, `rocm_version`,
`amdgpu_family`, etc. as inputs — same pattern as existing releases.

**Workflow location rationale:** Release workflow logic lives in TheRock so
it's close to the build workflows it calls and can be manually dispatched
for dev releases. rockrel owns schedule triggers and nightly/prerelease
run history — its workflows are thin wrappers that set release_type and
call the TheRock workflow.

### Publishing: staging → production

Nightly/prerelease: publish to **staging** subdir immediately after build,
then copy to **production** subdir only after tests pass. Users can choose
between "latest build" (staging) and "latest tested" (production).
Promotion is a separate step (manual or gated on test results from CI).

Dev releases: single publish (no staging/production distinction).

Tests run separately and don't block the release pipeline. This avoids
the retryability and queue bottleneck problems that would come from putting
flaky/slow tests in the critical path.

## Workstreams

### Workstream 1: Explicit bucket/role plumbing (prerequisite)

Make S3 bucket and IAM role selection explicit instead of inferred from
environment. Currently `workflow_outputs.py` reads `RELEASE_TYPE`,
`GITHUB_REPOSITORY`, and `IS_PR_FROM_FORK` env vars to guess the bucket.
This is fragile and doesn't generalize to cross-repo (rockrel) workflows.

**Approach: compute once in setup, pass explicitly everywhere.**

**Scope: artifacts bucket only.** The setup-computed config covers the
*artifacts bucket* (`therock-ci-artifacts`, `therock-dev-artifacts`, etc.)
where build outputs (tarballs, logs, packages) are stored during a workflow
run. All artifacts buckets are in the same AWS account and region.

The downstream *release buckets* (`therock-dev-python`, `therock-dev-tarball`,
`therock-nightly-packages`, etc.) are a separate concern — some are in a
different AWS account and region. The publish jobs that copy from artifacts
to release buckets will handle their own bucket/role configuration. We
intentionally do NOT plumb a full list of release bucket configs through
the build pipeline.

#### 1a. `configure_multi_arch_ci.py` computes infra config

Add `release_type` to `CIInputs` (from env var `RELEASE_TYPE`, default empty).
Add new outputs:

- `iam_role`: Full ARN string (e.g., `arn:aws:iam::692859939525:role/therock-ci`)
- `artifacts_bucket`: S3 bucket name (e.g., `therock-ci-artifacts`)

Logic (replaces `_retrieve_bucket_info` for the workflow path):

```python
def compute_infra_config(release_type: str, repository: str, is_fork: bool) -> InfraConfig:
    if release_type in ("dev", "nightly", "prerelease"):
        bucket = f"therock-{release_type}-artifacts"
        role = f"arn:aws:iam::692859939525:role/therock-{release_type}"
    elif is_fork or repository != "ROCm/TheRock":
        bucket = "therock-ci-artifacts-external"
        role = ""  # use runner base credentials
    else:
        bucket = "therock-ci-artifacts"
        role = "arn:aws:iam::692859939525:role/therock-ci"
    return InfraConfig(bucket=bucket, iam_role=role)
```

This is similar to what `get_s3_config.py` does for native packages — the
pattern should be consolidated. The `get_s3_config.py` script can call into
shared logic or be replaced.

#### 1b. `setup_multi_arch.yml` exposes new outputs

```yaml
inputs:
  release_type:
    type: string
    default: ""
outputs:
  iam_role:
    value: ${{ jobs.setup.outputs.iam_role }}
  artifacts_bucket:
    value: ${{ jobs.setup.outputs.artifacts_bucket }}
  # ... existing outputs unchanged ...
```

#### 1c. Thread through workflow chain

Each workflow in the chain gets `iam_role` and `artifacts_bucket` inputs:

```
setup_multi_arch.yml outputs →
  multi_arch_ci_linux.yml inputs →
    multi_arch_build_portable_linux.yml inputs →
      multi_arch_build_portable_linux_artifacts.yml inputs
```

At the leaf (`multi_arch_build_portable_linux_artifacts.yml`):
- `Configure AWS Credentials` step uses `inputs.iam_role` directly
  (no `github.repository` guard needed — empty role = skip the step)
- Scripts receive bucket explicitly via CLI args (see 1d)

#### 1d. `WorkflowOutputRoot` explicit bucket parameter

Add `bucket` parameter to `from_workflow_run()`:

```python
@classmethod
def from_workflow_run(
    cls,
    run_id: str,
    platform: str,
    bucket: str | None = None,  # NEW: explicit bucket, skips env inference
    github_repository: str | None = None,
    ...
) -> "WorkflowOutputRoot":
    if bucket:
        # Explicit bucket — no env var inference needed
        external_repo = _compute_external_repo(github_repository)
        return cls(bucket=bucket, external_repo=external_repo, ...)
    # Fallback: existing env-var-based logic (for backward compat)
    ...
```

Scripts that call `from_workflow_run()` get a `--bucket` CLI arg:

| Script | Current call | New call |
|--------|-------------|----------|
| `artifact_manager.py push` | `from_workflow_run(run_id=...)` | `from_workflow_run(run_id=..., bucket=args.bucket)` |
| `artifact_manager.py fetch` | `from_workflow_run(run_id=..., lookup_workflow_run=True)` | unchanged (fetches from other runs, needs lookup) |
| `post_stage_upload.py` | `from_workflow_run(run_id=...)` | `from_workflow_run(run_id=..., bucket=args.bucket)` |
| `upload_python_packages.py` | `from_workflow_run(run_id=...)` | `from_workflow_run(run_id=..., bucket=args.bucket)` |
| `generate_s3_index.py` | `from_workflow_run(run_id=...)` | `from_workflow_run(run_id=..., bucket=args.bucket)` |

For `fetch` (reading from another run): the `lookup_workflow_run=True` path
uses the GitHub API to determine the source bucket. This is correct — the
source run's bucket may differ from the current run's. No change needed.

For `copy` (copying between runs): same — source bucket is looked up via API.

**Backward compatibility**: All `--bucket` args default to `None`. When not
provided, the existing env-var logic in `_retrieve_bucket_info()` kicks in.
This means existing (non-multi-arch) workflows keep working without changes.
We can migrate them to explicit bucket passing incrementally.

#### 1e. Workflow YAML changes

**`multi_arch_build_portable_linux_artifacts.yml`** (the leaf build job):

Before:
```yaml
env:
  IS_PR_FROM_FORK: ${{ github.event.pull_request.head.repo.fork }}

- name: Configure AWS Credentials
  if: ${{ github.repository == 'ROCm/TheRock' && !github.event.pull_request.head.repo.fork }}
  uses: aws-actions/configure-aws-credentials@...
  with:
    role-to-assume: arn:aws:iam::692859939525:role/therock-ci

- name: Push stage artifacts
  run: python build_tools/artifact_manager.py push --run-id ${{ github.run_id }} ...
```

After:
```yaml
# No RELEASE_TYPE or IS_PR_FROM_FORK env vars needed

- name: Configure AWS Credentials
  if: ${{ inputs.iam_role != '' }}
  uses: aws-actions/configure-aws-credentials@...
  with:
    role-to-assume: ${{ inputs.iam_role }}

- name: Push stage artifacts
  run: |
    python build_tools/artifact_manager.py push \
      --run-id ${{ github.run_id }} \
      --bucket ${{ inputs.artifacts_bucket }} \
      ...
```

### Workstream 2: Release workflows

Depends on workstream 1 being complete.

**New file in TheRock:** `multi_arch_release_portable_linux.yml`

The release workflow lives in TheRock alongside the build workflows it calls.
It supports manual `workflow_dispatch` for dev releases and can be called by
rockrel wrappers for nightly/prerelease.

```yaml
on:
  workflow_call:
    inputs:
      release_type:
        type: string
        required: true
  workflow_dispatch:
    inputs:
      release_type:
        type: choice
        options: [dev, nightly, prerelease]
        default: dev
      families:
        type: string
        description: "Comma-separated GPU families"
      s3_subdir:
        type: choice
        options: [v3, v3-staging]
        default: v3
      prerelease_version:
        type: string
      ref:
        type: string
        default: ''

jobs:
  setup:
    uses: ./.github/workflows/setup_multi_arch.yml
    with:
      release_type: ${{ inputs.release_type }}

  build:
    needs: setup
    uses: ./.github/workflows/multi_arch_build_portable_linux.yml
    with:
      # ... build config from setup ...
      iam_role: ${{ needs.setup.outputs.iam_role }}
      artifacts_bucket: ${{ needs.setup.outputs.artifacts_bucket }}

  publish_tarballs:
    needs: [build]
    # Copy from therock-{type}-artifacts to therock-{type}-tarball
    # This job handles its own release bucket credentials (possibly
    # different AWS account/region from the artifacts bucket)
    ...

  publish_python:
    needs: [build]
    # Copy from therock-{type}-artifacts to therock-{type}-python
    ...
```

**New file in rockrel:** `multi_arch_release_portable_linux.yml`

Thin wrapper — owns the nightly schedule and run history, delegates to TheRock.

```yaml
on:
  workflow_dispatch:
    inputs:
      release_type:
        type: choice
        options: [nightly, prerelease]
        default: nightly
      ref:
        type: string
        default: ''
  schedule:
    - cron: '0 04 * * *'  # nightly

jobs:
  release:
    uses: ROCm/TheRock/.github/workflows/multi_arch_release_portable_linux.yml@main
    secrets: inherit
    with:
      release_type: ${{ inputs.release_type || 'nightly' }}
    permissions:
      contents: read
      actions: write
      id-token: write
```

### Workstream 3: Publish jobs

The publish jobs copy outputs from the artifacts bucket to package-specific
release buckets. TBD whether this is a new script or an extension of
`artifact_manager.py`.

Staging → production promotion:
- Staging publish runs unconditionally after build
- Production publish runs only if tests pass (conditional on test job results)
- For nightly: both staging and production subdirs
- For dev: single subdir (no staging distinction)

### IAM / OIDC Changes

- The `github.repository == 'ROCm/TheRock'` guard is eliminated entirely
  for artifacts bucket access (replaced by `if: inputs.iam_role != ''`)
- `therock-ci` and `therock-{dev,nightly,prerelease}` roles already trust
  `ROCm/TheRock` — no change needed for the artifacts bucket path since
  release workflows live in TheRock
- rockrel's thin wrappers call TheRock workflows via `workflow_call`, so the
  jobs run in TheRock's context — OIDC tokens come from `ROCm/TheRock`
- Publish jobs that write to release buckets in other AWS accounts/regions
  will need their own IAM role configuration (separate from the artifacts
  bucket role computed in setup)

### Name Collision Avoidance

Use `v3` subdirectory for multi-arch releases in tarball/python buckets.
Single-stage releases continue using `v2`. Both coexist during migration.

## MVP Scope

**MVP:**
1. ~~Workstream 1: explicit bucket/role plumbing (artifacts bucket only)~~ — done (#4386)
2. ~~Workstream 1b: thread release_type through full workflow chain~~ — in review (#4408)
3. Workstream 2a: build multi-arch tarballs workflow — branch `multi-arch-tarball-1`, testing on fork
4. Workstream 2b: release_multi_arch.yml scaffold (calls builds, copies to release buckets)

**Follow-up:**
- Workstream 3: publish jobs (copy artifacts → release buckets, handling
  cross-account/cross-region credentials)
- Python package publishing
- rockrel nightly schedule wrapper
- Prerelease support
- Windows multi-arch releases
- PyTorch/JAX wheel publishing

### Workstream 2a: Build multi-arch tarballs

**Current focus.** Standalone workflow that fetches multi-arch build artifacts,
flattens them into ROCm tarballs, and uploads to the artifacts bucket.

Structure similar to `build_portable_linux_python_packages.yml`:
1. Fetch artifacts via `artifact_manager.py fetch --flatten` (or fetch then
   flatten manually)
2. Produce tarballs (TBD: with/without KPACK_SPLIT, which families)
3. Upload tarballs to artifacts bucket in a subfolder

The existing release workflow (`release_portable_linux_packages.yml`) builds
`therock-dist` CMake target then runs `tar cfz`, but for multi-arch we want
to work from pre-built artifacts rather than rebuilding.

**Done:**
- Prototyped locally: `artifact_manager.py fetch --flatten` produces clean
  per-family install-prefix layouts. Verified gfx94X-dcgpu and gfx110X-all
  have correctly filtered GPU-specific files (e.g. `*.co` only for that family).
- Added `--download-cache-dir` to `artifact_manager.py` + cache-hit check in
  `download_artifact()` — avoids re-downloading generic artifacts across families.
- Created `build_tarballs.py` script: fetch/flatten/compress per family,
  shared download cache, `tar cfz` compression.
- Created `multi_arch_build_tarballs.yml` workflow scaffold.
- Tested end-to-end with Windows artifacts (Linux has a harmless ncurses
  symlink error on Windows hosts).
- Branch: `multi-arch-tarball-1`

**Tarball structure decisions:**
- KPACK_SPLIT=OFF (current default): per-family tarballs, since files from
  different families conflict when flattened together.
- KPACK_SPLIT=ON (future): single combined tarball possible, files are additive.
  Could use matrix `include:` to produce both per-family and combined tarballs.

**Compression performance:**

*Initial benchmarks (Python tarfile vs subprocess):*
- Python `tarfile` module: ~72s for 1.4GB, 3.5GB output (default compresslevel
  appears broken or very low — `compresslevel` kwarg may need tuning)
- `tar cfz` subprocess: ~22s for 1.4GB, 419MB output — 3x faster, correct size
- CI timings: ~4min (Windows) / ~6min (Linux) per family for full tarball

*Comprehensive benchmark (2026-04-10, Windows, 64-core machine, 1423MB source):*

```
Method                 Time (s)  Size (MB)    Ratio
----------------------------------------------------
tar-cfz                    21.0      419.4   29.5%    <- current default
gz-1                       12.2      449.8   31.6%
gz-3                       15.2      440.5   31.0%
gz-6                       26.4      420.9   29.6%
gz-9                       67.9      420.2   29.5%
zst-1                       3.3      420.2   29.5%    <- matches gz-6 ratio, 6x faster
zst-3                       4.4      360.5   25.3%    <- sweet spot
zst-6                       8.0      343.9   24.2%
zst-9                      10.0      317.9   22.3%
zst-19                    197.9      199.4   14.0%

Parallel (2 families, wall time):
  tar-cfz x2: 24.9s  (vs 21s single — some slowdown but not 2x)
  zst-3   x2:  9.7s  (vs 4.4s single — good scaling)
```

zst used pyzstd (Python binding), not the zstd CLI. gz used subprocess
`gzip -N` piped from `tar cf -`. `tar cfz` is the baseline matching current
`build_tarballs.py`.

*Analysis:*
- `zst-3` is the sweet spot: 14% smaller than gz-6, 5x faster
- For full ~19GB gfx94X-dcgpu, extrapolating: gz ~5-6 min, zst-3 ~1 min
- gz-9 is 3x slower than gz-6 for negligible improvement (0.1%)
- Serial compression uses ~3% of 64 cores (one core pinned). Parallel
  compression reached ~30% utilization (spread across logical processors).
  zstd's native `-T0` multi-threading (not benchmarked, needs CLI tool)
  could saturate all cores for a single tarball.
- Keeping `.tar.gz` for now to match existing release tarballs. Switching
  to `.tar.zst` would cut compression time ~5x and reduce output ~14% —
  worth proposing if downstream consumers can handle zstd.

*Parallelism scaling (2026-04-10, 64-core Windows, 10 jobs × 1.4GB each):*

```
Workers   Wall (s)    Avg/job  Speedup  Efficiency
------------------------------------------------------
      1      244.2       24.4     1.0x       103%
      2      128.3       25.6     2.0x        98%
      4       79.4       26.6     3.2x        79%
      6       54.4       27.2     4.6x        77%
      8       54.0       27.6     4.7x        58%
     10       28.8       28.6     8.8x        88%
```

Per-job time barely increases (25→29s) even at 10 concurrent — gzip is
CPU-bound on one core and 64 cores have plenty of headroom. Anecdotally,
serial compression showed ~3% CPU utilization (one core pinned), parallel
reached ~30% (spread across logical processors).

*Decision: single job with script-level parallelism.*
- 10 families in one job with ProcessPoolExecutor: ~29s wall for 1.4GB
  sources, extrapolating to full-size (~19GB) ≈ 6-7 min total.
- Compare to 10 separate CI jobs: each ~6 min compression + ~2 min setup
  overhead = ~8 min wall, but 10x the runner cost.
- Single job is cheaper, simpler (no matrix coordination), and wall time
  is comparable. `build_tarballs.py` parallelizes fetch+compress per family.
- Fetch is still sequential (shared download cache for generic artifacts),
  only compression is parallelized.

**Implementation (branch `multi-arch-tarball-1`):**

Commits:
- `artifact_manager.py`: download cache check + `--download-cache-dir` flag
- `multi_arch_build_tarballs.yml`: workflow scaffold (dispatch + call)
- `build_tarballs.py`: fetch/flatten/compress with shared cache, parallel
  compression, KPACK_SPLIT multiarch tarball support
- `upload_tarballs.py`: uploads .tar.gz to `{run_id}-{platform}/tarballs/`
  via `WorkflowOutputRoot.tarballs()` + `StorageBackend`
- `build_tarballs_test.py`: unit tests for `is_kpack_split`, `compress_tarball`
- `workflow_outputs.md`: tarballs layout + consumer entry

Testing on fork — may hit disk space limits on github-hosted runners
(fetch + flatten + compress for multiple families needs significant disk).

**Known issues:**
- KPACK_SPLIT artifact fetching broken for family groups (#4433) — with
  KPACK split enabled, artifacts are keyed by individual targets (gfx942)
  not family groups (gfx94X-dcgpu). `build_tarballs.py` works when given
  individual targets but the orchestrator passes family groups.
- Disk space: full tarball builds for all families may exceed github-hosted
  runner disk. May need compress→upload→delete pipeline or self-hosted runners.

**Next steps:**
- Validate workflow_dispatch on fork CI
- Wire into `multi_arch_ci_linux.yml` as a downstream job
- Address #4433 (family→target expansion) for KPACK split builds

### Workstream 2b: release_multi_arch.yml scaffold

Depends on 2a. Top-level release workflow that:
- Calls multi-arch build workflows across GPU families (via
  `setup_multi_arch.yml` or `fetch_package_targets.py`)
- Runs tarball workflow from 2a
- Copies outputs from artifacts bucket to release buckets
  (e.g. `therock-dev-artifacts` → `therock-dev-tarball`)

## Open Questions

1. **`setup_multi_arch.yml` inputs for release**: `configure_multi_arch_ci.py`
   reads `GITHUB_EVENT_PATH` for GPU families from PR labels / dispatch inputs.
   When called from rockrel, the event payload is rockrel's dispatch event.
   Does `setup_multi_arch.yml` need explicit family inputs for the release case?

2. **Which GPU families for releases?** Hardcode defaults in the orchestrator,
   or make it configurable?

3. **Publish script**: New `publish_release.py`, extend `artifact_manager.py`
   with a `publish` subcommand, or inline S3 commands?

4. **Consolidate with `get_s3_config.py`**: The native package workflow's
   `get_s3_config.py` has overlapping bucket/role logic. Should we consolidate
   into shared code in `configure_multi_arch_ci.py` or a shared utility?

## Alternatives Considered

### Single monolithic workflow (build + test + package in one graph)

The multi-arch CI pipeline (`multi_arch_ci_linux.yml`) runs builds, tests,
python packaging, and pytorch builds as jobs within a single workflow. We
could do the same for releases: one workflow that builds ROCm, runs tests,
builds all downstream packages (python, pytorch, jax, native), publishes
everything, and has a final "promote" gate.

**Why it's appealing:**
- Matches the CI pipeline structure — CI and CD use the same job graph,
  reducing divergence and making it easier to reason about "what ran."
- Single workflow run = single place to check status. No hunting across
  multiple dispatched workflow runs to see if a release succeeded.
- Job dependencies are explicit in YAML — no cross-workflow coordination.

**Why we chose separate workflows instead:**
- **Retryability.** GitHub Actions "re-run failed jobs" is coarse-grained
  within a workflow. If a pytorch wheel build fails after 4 hours, re-running
  it may also re-run unrelated failed jobs. With separate workflows, each
  is independently retryable without touching the others.
- **Test instability.** Current tests are flaky/unstable. Putting them in
  the critical path of the release workflow means flaky failures block
  everything downstream. With separate workflows, tests can run in parallel
  (or separately) without blocking package builds or publishing.
- **Queue bottlenecks.** Different jobs need different runner types with
  different queue depths. A 6-hour test queue on one machine type shouldn't
  bottleneck pytorch wheel builds that use a different runner. Monolithic
  workflows serialize these waits.
- **Incremental testing expansion.** We want to run more tests for nightly
  releases in the future. Adding slow/comprehensive test jobs to a
  monolithic release workflow makes the whole pipeline slower and more
  fragile. With separate workflows, adding tests is low-risk.
- **Existing precedent.** The current (non-multi-arch) release pipeline
  already uses `benc-uk/workflow-dispatch` to trigger pytorch, jax, and
  native package workflows separately. This is a proven pattern.
- **Promotion flexibility.** Separating "publish to staging" from "promote
  to production" lets us gate promotion on test results without blocking
  the build/publish pipeline. A monolithic workflow would need GitHub
  environment protection rules (manual approval) or complex conditional
  logic to achieve the same thing.

**Related precedent: CI vs. release pytorch workflows.** The same CI/CD
divergence already exists at the pytorch level.
`build_portable_linux_pytorch_wheels_ci.yml` installs ROCm via
`--find-links` (CI artifacts), builds only torch, and skips S3 upload.
`build_portable_linux_pytorch_wheels.yml` (release) installs via
`--index-url` (CloudFront CDN), builds the full suite (torchvision,
torchaudio, triton), and handles staging/promotion. They share
`build_prod_wheels.py` for build logic but diverge on plumbing. See
#3291 for convergence plans. This pattern — shared build scripts,
separate workflow plumbing for CI vs. release — is consistent with our
chosen approach.

If test infrastructure stabilizes significantly, revisiting this decision
would be reasonable — a monolithic workflow is simpler when all jobs are
fast and reliable. The separate-workflow approach is the pragmatic choice
given current constraints.

## Script inventory: `WorkflowOutputRoot.from_workflow_run()` callsites

Scripts that need `--bucket` arg (write to current run's bucket):
- `artifact_manager.py` (push subcommand)
- `post_stage_upload.py`
- `post_build_upload.py`
- `upload_python_packages.py`
- `upload_pytorch_manifest.py`
- `upload_jax_manifest.py`
- `upload_test_report_script.py`
- `generate_s3_index.py`

Scripts that DON'T need changes (read from other runs via API lookup):
- `artifact_manager.py` (fetch, copy subcommands — source bucket from API)
- `find_artifacts_for_commit.py`

Script that uses it for summary formatting (read-only, cosmetic):
- `configure_multi_arch_ci_summary.py`

## Worklog

### Approach 1: Explicit bucket/role plumbing (`multi-arch-release-type-explicit`)

Commit `9f69d16f`. 15 files, +391/-35.

- Added `InfraConfig` dataclass + `compute_infra_config()` to `configure_multi_arch_ci.py`
- Added `bucket` param to `WorkflowOutputRoot.from_workflow_run()` and
  `create_backend_from_env()`
- Added `--bucket` CLI arg to `artifact_manager.py` and `post_stage_upload.py`
- `setup_multi_arch.yml` outputs `artifacts_bucket` + `artifacts_bucket_iam_role`
- Threaded both through the full workflow chain (Linux + Windows)
- Leaf workflows use `inputs.artifacts_bucket_iam_role` for AWS credentials
  (no `github.repository` guard needed)

**Pros:** Fully explicit — no env var inference at point of use.
**Cons:** Large surface area, touches Python code that PR #4199 also modifies.
Friction: `external_repo` still inferred from env (noted with TODO).

### Approach 2: Implicit bucket via RELEASE_TYPE env var (`multi-arch-release-type-implicit`)

Commits `8e04296f`, `a7427d17`, `3d378139`, `cafa2eee`, `8b8b5191`. 7-8 workflow files only.

- Thread `release_type` input through workflows
- Set `RELEASE_TYPE` env var on push/upload steps → existing
  `_retrieve_bucket_info()` in `workflow_outputs.py` picks the right bucket
- "Determine IAM role" bash step selects the right OIDC role
- Extracted into `configure_aws_artifacts_credentials` composite action
- Test run: https://github.com/ROCm/TheRock/actions/runs/23873686956
  - Found: RELEASE_TYPE needed in setup_multi_arch.yml for summary URLs
  - Found: ccache preset should vary by release_type (TODO added)

**Pros:** Much smaller change, no Python modifications, ships fast.
**Cons:** Bucket selection implicit (env var), IAM role in bash (untestable),
duplicates logic that exists in multiple places.

### Approach 3: s3_buckets inventory library (current direction)

Building on approach 2. Landed as two stacked branches:

**PR #4386 — S3 bucket inventory + composite action (merged)**

Centralizes bucket selection into `s3_buckets.py`, replaces inline
`aws-actions/configure-aws-credentials` blocks with a composite action:

- `S3BucketConfig` dataclass: name, region, iam_account, iam_role
- `get_artifacts_bucket_config()`: pure lookup with validation
- `get_artifacts_bucket_config_for_workflow_run()`: GHA-aware wrapper
- `write_artifacts_bucket_info.py`: thin CLI for GITHUB_OUTPUT
- `configure_aws_artifacts_credentials` composite action
- `workflow_outputs.py` delegates to `get_artifacts_bucket_config_for_workflow_run()`
- Migrated 8 workflows to composite action
- Updated `docs/development/s3_buckets.md`
- Tests: `s3_buckets_test.py` (17 tests)

Also merged separately: PR #4402 (ccache preset rename, `--release-type` shorthand).

**PR #4408 — release_type plumbing (in review)**

Threads `release_type` through the full multi-arch workflow chain:

- `setup_multi_arch.yml` → `multi_arch_ci_{linux,windows}.yml` (existing)
- → `multi_arch_build_{portable_linux,windows}_artifacts.yml` (existing)
- → `build_{portable_linux,windows}_python_packages.yml` (new)
- → `test_artifacts_structure.yml` (new)
- → `test_artifacts.yml` → `test_component.yml` → `setup_test_environment` (new)
- `configure_aws_artifacts_credentials` receives `release_type` for IAM role selection
- `RELEASE_TYPE` env var set at job level for scripts that read it
- Build artifact workflows use `--release-type` for ccache preset selection

Known limitation: manual `workflow_dispatch` with `artifact_run_id` requires
the caller to match `release_type` manually — no way to query which bucket
a past run used. Acceptable for now; a central run metadata store could
fix this later.

**Resolved design questions:**

1. Fork detection lives in `s3_buckets.py` as `_is_current_run_pr_from_fork()` (private)
2. `get_artifacts_bucket_config_for_workflow_run()` reads env vars directly — callers
   can override `release_type` explicitly, falls back to RELEASE_TYPE env var
3. `workflow_outputs.py` delegates to `get_artifacts_bucket_config_for_workflow_run()` —
   no duplicate logic
4. CDN/HTTPS URL support deferred — `S3BucketConfig` stays a simple bucket+role struct
