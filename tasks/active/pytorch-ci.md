---
repositories:
  - therock
---

# Build and Test PyTorch Python Packages in CI

**Status:** Not started
**Priority:** P1 (High)
**Started:** 2026-02-06
**Issue:** https://github.com/ROCm/TheRock/issues/3177
**Depends on:** `python-packages-ci` (PR #3261)

## Overview

Build and test PyTorch wheels as part of CI, not just during scheduled release workflows. This extends the pattern from `python-packages-ci` (ROCm Python packages in CI) to also cover PyTorch/torchvision/torchaudio/triton.

**Problem:** CI and release workflows have diverged. Commits that pass presubmit can break release builds because PyTorch wheel building only happens in release workflows. Developers work around this by triggering expensive "dev release" workflow runs on PR branches, which wastes resources and indicates the CI gap.

**Goal:** Make CI configurable enough that most development tasks can be validated via CI alone, giving confidence that release workflows will succeed if CI passes on a PR.

## Goals

- [ ] Build PyTorch wheels in CI using ROCm packages from the same CI run
- [ ] Upload PyTorch wheels to S3 CI artifacts bucket
- [ ] Test PyTorch wheels on GPU runners
- [ ] Integrate into `ci_linux.yml` orchestration
- [ ] Integrate into `ci_windows.yml` orchestration
- [ ] Make CI workflow configurable (pytorch_git_ref, python_version, etc.)
- [ ] Update documentation (github_actions_debugging.md, etc.)
- [ ] Minimize divergence between CI and release workflows (shared building blocks)

### Phasing

**Phase 1: Build PyTorch in CI** — Refactor build/test/release orchestration
and add PyTorch building to CI workflows. Multiple PRs:

1. Add `--find-links` support to `build_prod_wheels.py`
2. Refactor `build_portable_linux_pytorch_wheels.yml` to only build + upload
3. Move test/promote orchestration into `release_portable_linux_pytorch_wheels.yml`
4. Add `build_pytorch` configuration to `configure_ci.py`
5. Add `build_pytorch_wheels` job to `ci_linux.yml` (build only, no test yet)
6. Same for Windows equivalents
7. Documentation updates

Building in CI alone catches issues like #3042 (project source changes that
break PyTorch compilation).

**Phase 2: Test PyTorch in CI** — Add testing after server-side index generation
is in place. Server-side AWS Lambda will generate `index.html` for all files in
a directory, eliminating client-side index generation and race conditions. With
that in place:
- Add `test_pytorch_wheels` job to `ci_linux.yml` / `ci_windows.yml`
- Update `test_pytorch_wheels.yml` to accept `package_find_links_url` input
- Shared `python/` directory "just works" with server-side indexing

## Context

### Background

Current state:
- `build_portable_linux_pytorch_wheels.yml` builds PyTorch from **release** ROCm packages (cloudfront index)
- `release_portable_linux_pytorch_wheels.yml` orchestrates matrix builds (python versions × pytorch refs)
- Neither is triggered during CI — only via `workflow_dispatch` or scheduled releases
- Same pattern on Windows with `build_windows_pytorch_wheels.yml`

The `python-packages-ci` task established a pattern for CI:
1. Build ROCm Python packages → upload to S3 (`therock-ci-artifacts`)
2. Generate flat `index.html` with `indexer.py`
3. Test on GPU runners using `--find-links` URL
4. Orchestrate from `ci_linux.yml` / `ci_windows.yml`

This task extends that chain: after ROCm packages are built and uploaded, build PyTorch wheels using those same packages, upload, and test.

### Related Work

- **Task:** `python-packages-ci` — established CI pattern for ROCm packages (PR #3261)
- **Issue #3177:** Tracking issue for expanding CI workflows (ROCm Python, PyTorch, JAX, native Linux)
- **Workflow:** `build_portable_linux_pytorch_wheels.yml` — existing release build workflow
- **Workflow:** `build_windows_pytorch_wheels.yml` — Windows equivalent
- **Workflow:** `test_pytorch_wheels.yml` — existing test workflow
- **Script:** `external-builds/pytorch/build_prod_wheels.py` — main PyTorch build script
- **Script:** `build_tools/github_actions/upload_python_packages.py` — S3 upload (from python-packages-ci)
- **Script:** `build_tools/github_actions/write_torch_versions.py` — extract versions from wheels
- **Script:** `build_tools/github_actions/promote_wheels_based_on_policy.py` — staging→release promotion

### Directories/Files Involved

```
# New workflows (Phase 1)
.github/workflows/build_portable_linux_pytorch_wheels_ci.yml  (NEW)
.github/workflows/build_windows_pytorch_wheels_ci.yml          (NEW)

# Workflows to modify (Phase 1)
.github/workflows/ci_linux.yml              # add pytorch build job
.github/workflows/ci_windows.yml            # add pytorch build job

# Scripts to modify (Phase 1)
external-builds/pytorch/build_prod_wheels.py  # add --find-links
build_tools/github_actions/configure_ci.py    # add build_pytorch output

# Reference workflows (not modified in Phase 1, used as templates)
.github/workflows/build_portable_linux_pytorch_wheels.yml   # release build (template for CI workflow)
.github/workflows/build_windows_pytorch_wheels.yml          # release build Windows (template)
.github/workflows/build_portable_linux_python_packages.yml  # CI pattern to follow

# Supporting scripts (used as-is)
build_tools/github_actions/upload_python_packages.py
build_tools/github_actions/write_torch_versions.py
build_tools/github_actions/determine_version.py
external-builds/pytorch/sanity_check_wheel.py

# Documentation
docs/development/github_actions_debugging.md
```

## Design

### Ideal Architecture: "Build only builds, test only tests, release only releases"

The ideal separation of concerns is:

| Workflow | Sole Responsibility |
|----------|---------------------|
| Build workflow | Compile packages + upload artifacts |
| Test workflow | Install packages + run tests |
| Release workflow | Orchestrate: build → test → promote to release bucket |
| CI workflow | Orchestrate: build → test (no promotion) |

This is how `build_portable_linux_python_packages.yml`, `test_rocm_wheels.yml`,
and `ci_linux.yml` work today for ROCm Python packages. Each does one thing.

### Why We Can't Refactor the Release Build Workflow (Yet)

The current `build_portable_linux_pytorch_wheels.yml` bundles all four concerns:
build, staging upload, test, and promotion — all in one workflow. Ideally we'd
refactor it to only build, then move staging/test/promote into the release
orchestration workflow.

**We're not doing that now** because:

1. **Matrix output problem:** The release workflow uses `strategy.matrix` to call
   the build workflow for each (python_version × pytorch_git_ref) combo. If we
   moved test/promote into the release workflow, we'd need per-matrix-entry
   outputs (e.g., `torch_version`), but GHA collapses matrix outputs to a single
   value. Solving this requires either version precomputation (#1236), unrolled
   job generation, or intermediate workflows — all non-trivial.

2. **Mixing CI and release logic is fragile.** Adding `release_type: ci` with
   conditional skips scattered throughout (skip staging upload for CI, skip
   promote for CI, different IAM role for CI, different bucket for CI...) creates
   a minefield of `if: ${{ inputs.release_type != 'ci' }}` conditions. Any
   mistake can break production releases.

3. **The release workflow is working today.** Refactoring a working release
   pipeline to add CI support risks breaking releases with no immediate benefit
   to release users.

### Approach: Separate CI Workflow, Shared Scripts

Instead, we create a new CI-specific workflow that calls the same build scripts.
The existing release workflow stays untouched.

**Core principle: share code at the script level, not the workflow level.**
Workflows are thin plumbing — route inputs/outputs to scripts, minimal YAML logic.
The real build logic lives in `build_prod_wheels.py`, which is shared. Forking a
workflow for a different context is cheap when the workflow is thin.

### Architecture (Phase 1)

| Workflow | Responsibility | Shared Script |
|----------|---------------|---------------|
| `build_portable_linux_pytorch_wheels.yml` | Release: build + stage + test + promote | `build_prod_wheels.py` |
| **`build_portable_linux_pytorch_wheels_ci.yml`** (NEW) | CI: build + upload to artifacts bucket | `build_prod_wheels.py` |
| `test_pytorch_wheels.yml` | Test PyTorch wheels on GPU | `setup_venv.py` |
| `release_portable_linux_pytorch_wheels.yml` | Release matrix orchestration | (calls release build workflow) |
| `ci_linux.yml` | CI orchestration | (calls CI build workflow) |

Same pattern for Windows:
- **`build_windows_pytorch_wheels_ci.yml`** (NEW) mirrors the Linux CI workflow

### Current vs Target Structure

**Current:**
```
release_portable_linux_pytorch_wheels.yml
  └── build_portable_linux_pytorch_wheels.yml (per matrix entry)
        ├── build_pytorch_wheels (build + upload to staging)
        ├── generate_target_to_run
        ├── test_pytorch_wheels
        └── upload_pytorch_wheels (promote)

ci_linux.yml
  ├── build_portable_linux_artifacts
  ├── build_portable_linux_python_packages
  └── test_rocm_wheels
  (no pytorch)
```

**Target (Phase 1):**
```
release_portable_linux_pytorch_wheels.yml
  └── build_portable_linux_pytorch_wheels.yml (UNCHANGED)

ci_linux.yml
  ├── build_portable_linux_artifacts
  ├── build_portable_linux_python_packages
  ├── test_rocm_wheels
  └── build_portable_linux_pytorch_wheels_ci (NEW - build only, no test yet)

build_portable_linux_pytorch_wheels_ci.yml (NEW)
  └── single job: build_pytorch_wheels
      ├── checkout + select python
      ├── checkout pytorch sources
      ├── build_prod_wheels.py --install-rocm --find-links ...
      ├── sanity_check_wheel.py
      └── upload_python_packages.py (to CI artifacts bucket)
```

**Future (Phase 2 + release restructuring):**
```
release_portable_linux_pytorch_wheels.yml (restructured — see #1236)
  ├── resolve_versions (precompute torch_version per combo)
  ├── build (matrix) → calls build-only workflow
  ├── test (matrix) → uses precomputed versions
  └── promote (matrix) → staging → release

ci_linux.yml
  ├── ...existing...
  ├── build_portable_linux_pytorch_wheels_ci
  └── test_pytorch_wheels (after server-side index generation)
```

Once the release workflow is restructured (after version precomputation from
#1236 and server-side index generation), both CI and release could share the
same build-only workflow. At that point we'd converge from two build workflows
back to one. The CI workflow is a stepping stone, not the end state.

### New Workflow: `build_portable_linux_pytorch_wheels_ci.yml`

A lean CI-specific workflow modeled after `build_portable_linux_python_packages.yml`.
Steps mirror the release build workflow's `build_pytorch_wheels` job, but with
CI-appropriate plumbing:

- Uses `--find-links` (not `--index-url`) for ROCm package installation
- Uses `therock-ci` IAM role (not `therock-{release_type}`)
- Uploads via `upload_python_packages.py` (not raw `aws s3 cp` to staging bucket)
- Single job: no staging, no test, no promote

```yaml
name: Build Portable Linux PyTorch Wheels (CI)

on:
  workflow_call:
    inputs:
      amdgpu_family:
        type: string
        required: true
      python_version:
        type: string
        default: "3.12"
      pytorch_git_ref:
        type: string
        default: "nightly"
      rocm_package_find_links_url:
        description: "URL for pip --find-links to install ROCm packages"
        type: string
        required: true
      rocm_version:
        description: "ROCm version for version suffix (e.g. 7.12.0.dev0)"
        type: string
    outputs:
      torch_version:
        value: ${{ jobs.build.outputs.torch_version }}

jobs:
  build:
    name: Build | ${{ inputs.amdgpu_family }} | py ${{ inputs.python_version }} | torch ${{ inputs.pytorch_git_ref }}
    runs-on: ${{ github.repository_owner == 'ROCm' && 'azure-linux-scale-rocm' || 'ubuntu-24.04' }}
    container:
      image: ghcr.io/rocm/therock_build_manylinux_x86_64@sha256:db2b63f...
      options: -v /runner/config:/home/awsconfig/
    permissions:
      id-token: write
    outputs:
      torch_version: ${{ steps.versions.outputs.torch_version }}
    env:
      PACKAGE_DIST_DIR: ${{ github.workspace }}/output/packages/dist
      AWS_SHARED_CREDENTIALS_FILE: /home/awsconfig/credentials.ini
    steps:
      - name: Checkout
        uses: actions/checkout@...

      - name: Select Python version
        run: python build_tools/github_actions/python_to_cp_version.py --python-version ${{ inputs.python_version }}

      - name: Add selected Python version to PATH
        # (same as release workflow)

      - name: Checkout PyTorch Source Repos from nightly branch
        if: ${{ inputs.pytorch_git_ref == 'nightly' }}
        # (same as release workflow)

      - name: Checkout PyTorch Source Repos from stable branch
        if: ${{ inputs.pytorch_git_ref != 'nightly' }}
        # (same as release workflow)

      - name: Create pip cache directory
        run: mkdir -p /tmp/pipcache

      - name: Determine optional arguments
        if: ${{ inputs.rocm_version }}
        run: |
          pip install packaging
          python build_tools/github_actions/determine_version.py \
            --rocm-version ${{ inputs.rocm_version }}

      - name: Build PyTorch Wheels
        run: |
          ./external-builds/pytorch/build_prod_wheels.py \
            build \
            --install-rocm \
            --find-links "${{ inputs.rocm_package_find_links_url }}" \
            --pip-cache-dir /tmp/pipcache \
            --clean \
            --output-dir ${{ env.PACKAGE_DIST_DIR }} \
            ${{ env.optional_build_prod_arguments }}

      - name: Write versions
        id: versions
        run: python ./build_tools/github_actions/write_torch_versions.py --dist-dir ${{ env.PACKAGE_DIST_DIR }}

      - name: Sanity Check Wheel
        run: python external-builds/pytorch/sanity_check_wheel.py ${{ env.PACKAGE_DIST_DIR }}/

      - name: Configure AWS Credentials
        if: ${{ !github.event.pull_request.head.repo.fork }}
        uses: aws-actions/configure-aws-credentials@...
        with:
          aws-region: us-east-2
          role-to-assume: arn:aws:iam::692859939525:role/therock-ci

      - name: Upload Python packages
        id: upload
        run: |
          python build_tools/github_actions/upload_python_packages.py \
            --input-packages-dir="${{ env.PACKAGE_DIST_DIR }}" \
            --artifact-group="${{ inputs.amdgpu_family }}" \
            --run-id="${{ github.run_id }}"
```

A corresponding `build_windows_pytorch_wheels_ci.yml` follows the same pattern
but mirrors `build_windows_pytorch_wheels.yml` (cmd shell, MSVC setup, no triton,
`B:/src` checkout paths, etc.).

### Changes to `build_prod_wheels.py`

Add `--find-links` argument to `add_common()`:
```python
p.add_argument("--find-links", help="URL for pip --find-links (flat index)")
```

In `do_install_rocm()`, add after `--index-url` handling:
```python
if args.find_links:
    pip_args.extend(["--find-links", args.find_links])
```

When `--find-links` is used without `--index-url`, pip will fall through to PyPI
for dependencies. This is fine because the ROCm packages in the find-links index
are self-contained with their deps.

### S3 Layout: Shared `python/` Directory

**Decision:** Upload both ROCm and PyTorch packages to the same `python/` subdirectory.

```
s3://therock-ci-artifacts/
└── {run_id}-{platform}/
    └── python/{artifact_group}/
        ├── rocm_sdk_core-*.whl         # ROCm packages
        ├── rocm_sdk_devel-*.whl
        ├── rocm_sdk_libraries_*.whl
        ├── torch-*.whl                 # PyTorch packages
        ├── torchvision-*.whl
        ├── torchaudio-*.whl
        ├── triton-*.whl                # Linux only
        └── index.html                  # generated by server-side Lambda (Phase 2)
```

**Benefit:** Single `--find-links` URL covers both ROCm and PyTorch for test install.

**Index generation:** In Phase 1, we just upload packages (no index generation
needed for build-only). In Phase 2, server-side AWS Lambda will generate
`index.html` automatically for all files in the directory, eliminating
client-side race conditions and simplifying the upload scripts.

### Changes to `test_pytorch_wheels.yml` (Phase 2)

Deferred until server-side index generation is in place. Design:

- Add `package_find_links_url` as alternative to `package_index_url`
- Update `setup_venv.py` call to use `--find-links-url` when provided
- With shared `python/` directory and server-side indexing, a single
  `--find-links` URL provides both ROCm and PyTorch packages

### CI Workflow Orchestration in `ci_linux.yml` (Phase 1: build only)

```yaml
build_portable_linux_pytorch_wheels_ci:
  needs: [build_portable_linux_python_packages]
  name: Build PyTorch
  if: >-
    ${{
      !failure() &&
      !cancelled() &&
      (
        inputs.use_prebuilt_artifacts == 'false' ||
        inputs.use_prebuilt_artifacts == 'true'
      ) &&
      inputs.expect_failure == false &&
      inputs.build_pytorch == true
    }}
  uses: ./.github/workflows/build_portable_linux_pytorch_wheels_ci.yml
  secrets: inherit
  with:
    amdgpu_family: ${{ inputs.artifact_group }}
    python_version: "3.12"
    pytorch_git_ref: "nightly"
    rocm_package_find_links_url: ${{ needs.build_portable_linux_python_packages.outputs.package_find_links_url }}
    rocm_version: ${{ inputs.rocm_package_version }}
  permissions:
    contents: read
    id-token: write

# Phase 2: add test_pytorch_wheels job here (after server-side index generation)
```

### Configurability via `configure_ci.py`

Add a `build_pytorch` output that controls whether CI builds PyTorch:

**Default behavior by trigger type:**

| Trigger | `build_pytorch` |
|---------|----------------|
| `pull_request` | `false` (opt-in via label) |
| `push` (long-lived branch) | `true` |
| `schedule` (nightly) | `true` |
| `workflow_dispatch` | configurable input |

**PR label opt-in:** Add a `build:pytorch` label. When present, `configure_ci.py`
sets `build_pytorch=true`.

**CI defaults (narrow scope):**
- One Python version: `3.12`
- One or two PyTorch refs: `nightly` (and optionally latest stable, e.g. `release/2.10`)
- Full matrix is for release workflows only

**New inputs to `ci_linux.yml`:**
```yaml
inputs:
  build_pytorch:
    type: boolean
    default: false
  pytorch_git_ref:
    type: string
    default: "nightly"
  pytorch_python_version:
    type: string
    default: "3.12"
```

**New outputs from `configure_ci.py`:**
```python
output["build_pytorch"] = json.dumps(build_pytorch)
```

### Windows Support

Same pattern applies to `build_windows_pytorch_wheels.yml` and `ci_windows.yml`.
Key differences:
- No triton wheel on Windows
- Uses `cmd` shell for MSVC setup
- Different runner (`azure-windows-scale-rocm`)
- Source checkout to `B:/src` (shorter Windows paths)

### Documentation Updates

**`docs/development/github_actions_debugging.md`:**
- Update "Testing PyTorch release workflows" section to note that CI now
  validates PyTorch builds and most changes can be tested via CI
- Document when you still need the release workflow (full matrix, promotion)
- Add section on using the `build:pytorch` label for PR-level validation

## Investigation Notes

### 2026-02-06 - Initial Analysis

**`build_prod_wheels.py` ROCm installation (lines 293-326):**
- `do_install_rocm()` builds a pip command with `--index-url` and `--force-reinstall`
- Adding `--find-links` is straightforward — just add to `pip_args` when provided
- The `add_common()` function (line 945) adds `--index-url` to argparse
- Need to add `--find-links` there too
- Both `--index-url` and `--find-links` can be used together (pip supports this)
- With `--find-links` only (no `--index-url`), pip falls through to PyPI for deps

**`test_pytorch_wheels.yml` (line 130-136):**
- Uses `setup_venv.py` with `--index-url` and `--index-subdir`
- `setup_venv.py` already supports `--find-links-url` (added in PR #3242)
- Need to make the workflow inputs flexible to accept either URL type
- Deferred to Phase 2 (after server-side index generation)

**Index generation — server-side approach:**
- Plans to move index generation to server-side AWS Lambda
- Lambda will generate `index.html` for all files in a directory on S3
- Eliminates client-side race conditions (multiple uploads to same directory)
- For Phase 1 (build-only in CI), we just upload packages — no index needed
- For Phase 2 (test in CI), server-side index makes shared directory "just work"

**`configure_ci.py` extension points:**
- Currently outputs: `linux_variants`, `linux_test_labels`, `windows_variants`,
  `windows_test_labels`, `enable_build_jobs`, `test_type`
- PR labels already drive target selection (e.g., `gfx*` patterns)
- Adding `build:pytorch` label follows the existing label-based pattern
- Need to add `build_pytorch` to output dict and `gha_set_output()`

**Release workflow restructuring challenge:**
- `release_portable_linux_pytorch_wheels.yml` uses `strategy.matrix` to call
  the build workflow — this creates independent instances
- Moving test/promote into the release workflow means we need multi-job
  orchestration per matrix entry
- May need a "release single" intermediate workflow that handles one combo
- Alternative: keep test/promote in build workflow for release mode only (conditional)
  — but this contradicts the clean separation principle

## Decisions Made

- **Separate CI workflow:** New `build_portable_linux_pytorch_wheels_ci.yml`
  (and Windows equivalent) rather than modifying the release build workflow.
  Share build logic at the script level (`build_prod_wheels.py`), not the
  workflow level.
- **Release workflow untouched (Phase 1):** `build_portable_linux_pytorch_wheels.yml`
  stays as-is. Restructuring it (moving test/promote out) is deferred until
  version precomputation (#1236) and server-side index generation are in place.
- **CI workflow responsibility:** Phase 1 = build only; Phase 2 = build + test
- **Shared `python/` directory:** ROCm and PyTorch packages share the same S3
  subdirectory. Server-side Lambda will generate `index.html` (Phase 2).
- **CI scope defaults:** One Python version (3.12), 1-2 PyTorch refs (nightly + maybe latest stable)
- **CI opt-in:** `build:pytorch` PR label; always-on for postsubmit/nightly
- **`build_prod_wheels.py`:** Add `--find-links` flag to `add_common()` and
  use in `do_install_rocm()` alongside or instead of `--index-url`
- **Index generation:** Moving to server-side AWS Lambda. Workflows just upload
  packages; Lambda generates `index.html` for all files in the directory.
  This avoids client-side race conditions with multiple uploads.
- **Convergence plan:** The CI build workflow is a stepping stone. Once the
  release workflow is restructured to separate build/test/promote (after #1236),
  both CI and release can share a single build-only workflow.

## MVP Plan: Build PyTorch on CI

Concrete plan to get the minimum viable "build pytorch on CI" working. Each
numbered item can be a separate PR.

### PR 1: Add `--find-links` to `build_prod_wheels.py`

**Files changed:**
- `external-builds/pytorch/build_prod_wheels.py`

**Changes:**
- Add `--find-links` to `add_common()` argparse
- Use in `do_install_rocm()`: `pip_args.extend(["--find-links", args.find_links])`
- Small, self-contained, easy to review

**Testing:** Unit test or manual test with a known find-links URL.

### PR 2: Create `build_portable_linux_pytorch_wheels_ci.yml`

**Files changed:**
- `.github/workflows/build_portable_linux_pytorch_wheels_ci.yml` (NEW)

**Changes:**
- New workflow, modeled on `build_portable_linux_pytorch_wheels.yml` build job
- Uses `--find-links` for ROCm packages (from PR 1)
- Uploads to CI artifacts bucket via `upload_python_packages.py`
- Single job, no test/promote

**Testing:** Trigger via `workflow_dispatch` on a test branch with a known
`rocm_package_find_links_url` from a recent CI run.

### PR 3: Add `build_pytorch` to `configure_ci.py` + wire into `ci_linux.yml`

**Files changed:**
- `build_tools/github_actions/configure_ci.py`
- `.github/workflows/ci_linux.yml`
- `.github/workflows/setup.yml` (if needed to pass through `build_pytorch`)

**Changes:**
- `configure_ci.py`: Add `build_pytorch` output. Default false for PRs
  (opt-in via `build:pytorch` label), true for postsubmit/nightly.
- `ci_linux.yml`: Add `build_portable_linux_pytorch_wheels_ci` job
  after `build_portable_linux_python_packages`, gated on `build_pytorch`.
- Wire `build_pytorch` input through setup workflow.

**Testing:** Push to a branch with the `build:pytorch` label. Verify
the pytorch build job runs and completes after ROCm packages are built.

### PR 4: Windows equivalent

**Files changed:**
- `.github/workflows/build_windows_pytorch_wheels_ci.yml` (NEW)
- `.github/workflows/ci_windows.yml`

**Changes:**
- Same pattern as Linux but mirroring `build_windows_pytorch_wheels.yml`:
  cmd shell, MSVC, no triton, `B:/src` paths, etc.
- Wire into `ci_windows.yml` with same `build_pytorch` gating.

### PR 5: Documentation

**Files changed:**
- `docs/development/github_actions_debugging.md`

**Changes:**
- Update "Testing PyTorch release workflows" to note that CI now validates
  PyTorch builds for most changes
- Document the `build:pytorch` label
- Document when you still need the full release workflow

### Phase 2 (future)

- Test PyTorch in CI (after server-side index generation)
- Restructure release workflow (after version precomputation, #1236)
- Converge CI and release onto a single build-only workflow

## Open Questions

- **CI runtime impact:** PyTorch builds are expensive. Build caching (separate task)
  will help, but for now, opt-in via label + always-on for postsubmit keeps costs down.
- **`rocm_version` input:** The CI build needs `rocm_version` for
  `determine_version.py` to compute the version suffix. This is already available
  as `rocm_package_version` in `ci_linux.yml` inputs — need to confirm it's the
  right format.
- **PR #3261 status:** PR 2+ are blocked until python-packages-ci lands (need
  `package_find_links_url` output from the ROCm packages build job).
