# Multi-Arch Release Workflows

**Tracking issue:** https://github.com/ROCm/TheRock/issues/3334
**Status:** Design

## Goal

Set up multi-arch release workflows that reuse the existing multi-arch CI build
infrastructure, uploading artifacts to release S3 buckets
(`therock-dev-artifacts`, `therock-nightly-artifacts`, etc.) instead of
`therock-ci-artifacts`. The release-specific part then copies/promotes outputs
from the artifacts bucket to package-specific buckets (`therock-dev-tarball`,
`therock-dev-python`).

Release workflows live in **rockrel** (`ROCm/rockrel`) for credential
isolation. Build workflows in TheRock are modified to accept explicit
bucket/role configuration computed once in setup.

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
Workflow 1: rockrel/multi_arch_release_portable_linux.yml (orchestrator)
  │
  ├── TheRock: setup_multi_arch.yml           (matrix + version + infra config)
  │     └── NEW: release_type → computes iam_role, artifacts_bucket
  │
  ├── TheRock: multi_arch_build_portable_linux.yml  (build all stages)
  │     └── iam_role, artifacts_bucket threaded to each stage job
  │
  ├── publish tarballs → therock-{type}-tarball/{s3_subdir}/
  │
  ├── build python packages → publish python → therock-{type}-python/{s3_subdir}/
  │
  ├── dispatch: pytorch wheels workflow (per-family)
  ├── dispatch: jax wheels workflow (per-family)
  └── dispatch: native packages workflow (deb + rpm)
```

Each dispatched workflow receives `run_id`, `release_type`, `rocm_version`,
`amdgpu_family`, etc. as inputs — same pattern as existing releases.

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

### Workstream 2: Release orchestrator (rockrel)

Depends on workstream 1 being complete.

**New file in rockrel:**
`multi_arch_release_portable_linux.yml`

```yaml
on:
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
  schedule:
    - cron: '0 04 * * *'  # nightly

jobs:
  setup:
    uses: ROCm/TheRock/.github/workflows/setup_multi_arch.yml@main
    with:
      release_type: ${{ inputs.release_type || 'nightly' }}

  linux_build_and_test:
    needs: setup
    uses: ROCm/TheRock/.github/workflows/multi_arch_ci_linux.yml@main
    with:
      build_config: ${{ needs.setup.outputs.linux_build_config }}
      rocm_package_version: ${{ needs.setup.outputs.rocm_package_version }}
      test_type: ${{ needs.setup.outputs.test_type }}
      iam_role: ${{ needs.setup.outputs.iam_role }}
      artifacts_bucket: ${{ needs.setup.outputs.artifacts_bucket }}

  publish_tarballs:
    needs: [linux_build_and_test]
    # Copy from therock-{type}-artifacts to therock-{type}-tarball
    ...

  publish_python:
    needs: [linux_build_and_test]
    # Copy from therock-{type}-artifacts to therock-{type}-python
    ...
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

- Update trust policies for `therock-dev`, `therock-nightly`,
  `therock-prerelease` roles to accept OIDC from `ROCm/rockrel`
- The `github.repository == 'ROCm/TheRock'` guard is eliminated entirely
  (replaced by `if: inputs.iam_role != ''`)

### Name Collision Avoidance

Use `v3` subdirectory for multi-arch releases in tarball/python buckets.
Single-stage releases continue using `v2`. Both coexist during migration.

## MVP Scope

**MVP:**
1. Workstream 1: explicit bucket/role plumbing
2. Workstream 2: rockrel orchestrator (tarballs only, dev release_type)
3. Manual `workflow_dispatch` only (no schedule yet)

**Follow-up:**
- Workstream 3: publish jobs
- Python package publishing
- Nightly schedule + prerelease support
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
