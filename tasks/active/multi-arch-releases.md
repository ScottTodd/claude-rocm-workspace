# Multi-Arch Release Workflows

**Tracking issue:** https://github.com/ROCm/TheRock/issues/3334
**Status:** In progress — workstream 1 (bucket/role plumbing)

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
1. Workstream 1: explicit bucket/role plumbing (artifacts bucket only)
2. Workstream 2: release workflow in TheRock (tarballs, dev release_type,
   manual dispatch)
3. Coordinate with PR #4199 (StorageConfig refactor) on workflow_outputs.py

**Follow-up:**
- Workstream 3: publish jobs (copy artifacts → release buckets, handling
  cross-account/cross-region credentials)
- Python package publishing
- rockrel nightly schedule wrapper
- Prerelease support
- Windows multi-arch releases
- PyTorch/JAX wheel publishing
- Migrate non-multi-arch workflows to explicit bucket plumbing

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

Building on approach 2. Added `build_tools/_therock_utils/s3_buckets.py` as
centralized bucket inventory (code version of `docs/development/s3_buckets.md`).

- `S3BucketConfig` dataclass: name, region, iam_role, iam_namespace
- `s3_bucket_configs` list: full inventory of CI + release buckets
- `get_artifacts_bucket_config()`: lookup with validation (release_type,
  repo, fork, event_name)
- `ALLOWED_RELEASE_REPOS`: shared constant for repo validation
- `get_artifacts_iam_role.py`: thin CLI wrapper reading GHA env vars,
  writes iam_role + aws_region to GITHUB_OUTPUT
- `configure_aws_artifacts_credentials` composite action calls the script

**Next steps:**
- Tests for `s3_buckets.py` and `get_artifacts_iam_role.py`
- Wire `s3_buckets.py` into `workflow_outputs.py` (replace `_retrieve_bucket_info`)
- Coordinate with PR #4199 on `StorageConfig` using `s3_buckets.py`
- Squash/clean up commits on the implicit branch before PR

**Open design questions:**

1. **`_is_fork_pr()` location:** Currently in `get_artifacts_iam_role.py`.
   Should it move to `github_actions_api.py`? It reads `GITHUB_EVENT_PATH`
   and `GITHUB_REPOSITORY` — general-purpose GHA utility, not specific to
   artifacts.

2. **`get_artifacts_bucket_config()` env-var reading:** Currently the script
   (`get_artifacts_iam_role.py`) reads GHA env vars and passes them as args.
   Should `get_artifacts_bucket_config()` have a `_for_env()` variant that
   reads directly from the environment? Would reduce boilerplate in callers
   but couples the library to GHA.

3. **Interaction with `_retrieve_bucket_info()`:** If `workflow_outputs.py`
   switches to use `s3_buckets.py`, it would also need fork detection and
   env-var reading. The answers to questions 1 and 2 shape whether that's
   clean (shared `_is_fork_pr()` + `_for_env()`) or messy (duplicated env
   reading).

4. **CDN/HTTPS URL support on `S3BucketConfig`:** The bucket inventory in
   `s3_buckets.md` includes CloudFront CDN URLs for each release bucket
   (e.g. `rocm.devreleases.amd.com/v2/`). PR #4199 defines `StorageConfig`
   with `s3_url_schema`, `https_url_schema`, `bucket_schema`. Should
   `S3BucketConfig` grow CDN URL fields so it becomes the single source of
   truth for both bucket identity and access URLs? Or should that stay in
   `StorageConfig`/`StorageLocation`? Need to consider the design space
   before extending `S3BucketConfig` further — it could either stay a
   simple bucket+role struct or become the general-purpose storage config.
