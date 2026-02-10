---
repositories:
  - therock
---

# Build and Test PyTorch Python Packages in CI

**Status:** In progress — PR 2 up for review
**Priority:** P1 (High)
**Started:** 2026-02-06
**Issue:** https://github.com/ROCm/TheRock/issues/3291
**Parent issue:** https://github.com/ROCm/TheRock/issues/3177
**Depends on:** `python-packages-ci` (PR #3261, merged)

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
- **Issue #3291:** This task's tracking issue
- **Issue #3177:** Parent tracking issue for expanding CI workflows (ROCm Python, PyTorch, JAX, native Linux)
- **Issue #1236:** Release workflows do not freeze commits (version precomputation)
- **Issue #2156:** Test failures / narrower test set needed for CI-level pytorch testing
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

**Index generation:** In Phase 1, we upload packages to the CI artifacts bucket.
If we limit to a single PyTorch+Python version, we could generate the index
locally from a directory containing both ROCm and PyTorch packages (option 1
from #3291), which might enable testing sooner. For multiple parallel uploads
(multiple pytorch versions), we'd need server-side index generation (option 3).
In Phase 2, server-side AWS Lambda will generate `index.html` automatically
for all files in the directory, eliminating client-side race conditions.

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
      inputs.build_pytorch == true
    }}
  uses: ./.github/workflows/build_portable_linux_pytorch_wheels_ci.yml
  secrets: inherit
  with:
    amdgpu_family: ${{ inputs.artifact_group }}
    python_version: "3.12"
    pytorch_git_ref: "release/2.10"
    rocm_package_find_links_url: ${{ needs.build_portable_linux_python_packages.outputs.package_find_links_url }}
    rocm_version: ${{ inputs.rocm_package_version }}
  permissions:
    contents: read
    id-token: write

# Phase 2: add test_pytorch_wheels job here (after server-side index generation)
```

No `inputs.expect_failure` check here. `build_pytorch` is the sole gate — a
positive selection set by `configure_ci.py`. Families with known pytorch build
failures aren't selected, so there's no need to also check `expect_failure`.

### Configurability via `configure_ci.py`

**PR 2 (minimal):** `configure_ci.py` adds a per-variant `build_pytorch` field,
initially just `not expect_pytorch_failure`. This prevents nightly from
scheduling pytorch builds for known-broken families.

**PR 3 (follow-up):** Per-trigger narrowing and label support:

| Trigger | Which families get `build_pytorch: true` |
|---------|----------------------------------------|
| `pull_request` | None by default. `build:pytorch` label → gfx94x only |
| `push` (long-lived branch) | gfx94x only |
| `schedule` (nightly) | All non-broken families |
| `workflow_dispatch` | Configurable; defaults to all non-broken families |

**CI defaults (narrow scope):**
- One Python version: `3.12` (or `3.13`)
- Latest stable PyTorch: `release/2.10` (or `release/2.9`)
- NOT nightly — nightly can break from upstream PyTorch changes outside our
  control, making it unsuitable as a blocking CI signal on our PRs. Stable
  release branches are much more predictable.
- Full matrix (multiple python versions × multiple pytorch refs) is for release
  workflows only

**New input on `ci_linux.yml` / `ci_windows.yml`:**
```yaml
inputs:
  build_pytorch:
    type: boolean
    default: false
```

**Callers (`ci.yml`, `ci_nightly.yml`) pass it through:**
```yaml
build_pytorch: ${{ matrix.variant.build_pytorch == true }}
```

Python version and pytorch ref are hardcoded in the `ci_linux.yml` job for now.
Configurability can be added later if needed.

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
- `build_pytorch` goes into the per-variant matrix row (not a top-level output),
  since it varies per family. Callers pass it through to ci_linux/ci_windows.
- `expect_pytorch_failure` is read from `amdgpu_family_matrix.py` per-family
  and inverted into `build_pytorch` — positive selection, not negative filtering

### 2026-02-10 - `expect_pytorch_failure` plumbing analysis

**How it works in release workflows:**
- `amdgpu_family_matrix.py` defines `expect_pytorch_failure: True` per family/platform
- `fetch_package_targets.py` extracts it into the `package_targets` JSON output
- Release workflows (`release_portable_linux_packages.yml:322`,
  `release_windows_packages.yml:340`) use it as a step-level `if` to skip
  the "Trigger building PyTorch wheels" step

**Families with `expect_pytorch_failure: True`:**
- `gfx90x` / windows — #1927: `std::memcpy` in device code (HIP compiler)
- `gfx101x` / linux — #1926: CK bgemm missing `CK_BUFFER_RESOURCE_3RD_DWORD`
- `gfx101x` / windows — #1925: aotriton rejects unrecognized arch strings

All three issues are still open (2026-02-10). #1926 and #1927 need upstream
fixes (CK team, ROCm system headers). #1925 could be worked around by adding
gfx101X to the `AOTRITON_UNSUPPORTED_ARCHS` list in `build_prod_wheels.py`
(lines 705, 766) — same pattern as PR #3164 used for gfx103X on Windows.

**CI plumbing gap:** `configure_ci.py` does NOT extract `expect_pytorch_failure`.
The current `ci_linux.yml` pytorch job gates on `expect_failure` as a proxy,
which works by accident for gfx101x/linux (which has both flags) but not for
gfx90x/windows (only has `expect_pytorch_failure`).

**Decision:** Use positive selection instead of negative filtering. `configure_ci.py`
sets `build_pytorch = not expect_pytorch_failure` per variant. The pytorch job
gates on `inputs.build_pytorch == true`. No need to plumb `expect_pytorch_failure`
through the CI workflow stack.

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
- **CI scope defaults:** One Python version (3.12 or 3.13), latest stable
  PyTorch (release/2.10 or release/2.9). Not nightly — upstream breakage
  would create false negatives on our PRs.
- **Positive selection over negative filtering:** `configure_ci.py` sets
  `build_pytorch` per variant (inverted from `expect_pytorch_failure`). The
  pytorch job in `ci_linux.yml` gates on `build_pytorch == true` — no need to
  plumb `expect_pytorch_failure` through the CI workflow stack.
- **CI opt-in (PR 3):** `build:pytorch` PR label; always-on for postsubmit/nightly.
  Per-trigger narrowing (gfx94x only on PR/postsubmit) saves CI resources.
- **`build_prod_wheels.py`:** Add `--find-links` flag to `add_common()` and
  use in `do_install_rocm()` alongside or instead of `--index-url`
- **Index generation:** Moving to server-side AWS Lambda. Workflows just upload
  packages; Lambda generates `index.html` for all files in the directory.
  This avoids client-side race conditions with multiple uploads.
- **Convergence plan:** The CI build workflow is a stepping stone. Once the
  release workflow is restructured to separate build/test/promote (after #1236),
  both CI and release can share a single build-only workflow.

## Alternatives Considered

### CI as "dev release" — every CI run uploads to a shared release-like bucket

**Idea:** Make CI workflows run a "dev release" that uploads to e.g.
`therock-dev-python`, bringing CI and release workflows much closer together
(potentially sharing the same workflow YAML).

**Why it's appealing:**
- Reduces code duplication between CI and release workflows
- CI would exercise the actual release path, catching release-specific issues
- `pip install rocm==7.10.0.dev0+abcdef` from a dev index for an arbitrary
  commit would be useful for some developer and tooling workflows

**Why we rejected it:**

1. **Security boundary.** CI jobs include runs from developer forks on
   potentially unreviewed code. A strong separation between development
   artifacts and release artifacts is good security practice. Dev releases are
   already triggered manually (more controlled), and we're trying to *reduce*
   that manual triggering — keeping "dev releases" focused on testing the
   release process itself, not validating routine source changes.

2. **Build scope mismatch.** Release builds typically build the full project
   stack with a release-specific build cache. CI builds can build subsets of
   the stack and use more permissive, broadly shared build caches. These are
   fundamentally different build profiles that shouldn't share an output bucket.

3. **Volume and cost.** CI runs on every PR push, potentially dozens of times
   per day. Uploading full wheel sets to a persistent release-like bucket on
   every run creates significant storage churn. Release uploads are infrequent
   and deliberate — different lifecycle for artifact retention and cleanup.

4. **Versioning.** CI builds from different PRs targeting the same base could
   produce wheels with the same version string but different contents. The
   `dev0+{commit_hash}` suffix from `compute_rocm_package_version.py` should
   avoid most collisions, but the semantics are wrong — a "release" artifact
   (even dev) implies intentional publication, while CI artifacts are transient
   validation byproducts.

5. **Signal clarity.** A package in `therock-dev-python` carries implicit
   meaning: "someone intentionally published this for external consumption."
   CI artifacts don't carry that intent. Mixing them muddies the signal for
   anyone consuming from that bucket.

**Notes on version collision:** `compute_rocm_package_version.py` includes a
git commit hash in dev versions (e.g. `7.10.0.dev0+abcdef`), which should be
sufficient to avoid most collisions across workflow runs. And having
`pip install rocm==7.10.0.dev0+abcdef` work for arbitrary commits would
genuinely be useful. But this can be achieved through existing tooling like
`setup_venv.py` and `build_tools/find_artifacts_for_commit.py` without
conflating CI artifacts with release artifacts.

**Bottom line:** Share code at the script level, not the bucket or workflow
level. CI validates the build; release validates the distribution. Same
scripts, different trust boundaries.

## MVP Plan: Build PyTorch on CI

Concrete plan to get the minimum viable "build pytorch on CI" working. Each
numbered item can be a separate PR.

### PR 1: Add `--find-links` to `build_prod_wheels.py` — [#3293](https://github.com/ROCm/TheRock/pull/3293) ✅

**Files changed:**
- `external-builds/pytorch/build_prod_wheels.py`

**Changes:**
- Add `--find-links` to `add_common()` argparse
- Use in `do_install_rocm()`: `pip_args.extend(["--find-links", args.find_links])`
- Small, self-contained, easy to review

**Testing:** Unit test or manual test with a known find-links URL.

### PR 1b: Fix pip cache package name — [#3294](https://github.com/ROCm/TheRock/pull/3294) ✅ (merged)

**Files changed:**
- `external-builds/pytorch/build_prod_wheels.py`

**Changes:**
- Fix incorrect package name in `pip cache remove` command (bug found during PR 1 testing)

### PR 2: CI workflow + configure_ci.py gating — [#3303](https://github.com/ROCm/TheRock/pull/3303) (draft)

**Files changed:**
- `.github/workflows/build_portable_linux_pytorch_wheels_ci.yml` (NEW)
- `.github/workflows/ci_linux.yml`
- `build_tools/github_actions/configure_ci.py`
- `build_tools/github_actions/tests/configure_ci_test.py`
- `.github/workflows/ci.yml`
- `.github/workflows/ci_nightly.yml`

**Changes:**

*New CI workflow:*
- `build_portable_linux_pytorch_wheels_ci.yml`, modeled on release build
  workflow's build job
- Uses `--find-links` for ROCm packages (from PR 1)
- Builds torch only (no vision/audio/triton)
- Build + sanity check only, no S3 upload (deferred pending index generation)
- Explicit python_version="3.12" and pytorch_git_ref="release/2.10"

*configure_ci.py — `build_pytorch` per variant:*
- Both `matrix_generator` and `generate_multi_arch_matrix` compute
  `build_pytorch = not expect_failure and not expect_pytorch_failure`
- `format_variants()` in step summary now shows flags (expect_failure, build_pytorch)
- 3 new unit tests in `configure_ci_test.py` covering the build_pytorch logic
- No trigger-type logic or label support yet — just respects the existing
  flags from `amdgpu_family_matrix.py`

*Wiring:*
- `ci_linux.yml`: new `build_pytorch` boolean input (default false), pytorch
  job gated on `inputs.build_pytorch == true`
- `ci.yml` / `ci_nightly.yml`: pass
  `build_pytorch: ${{ matrix.variant.build_pytorch == true }}`
- No `inputs.expect_failure` check on the pytorch job — `build_pytorch` is
  the sole gate (positive selection)

**Testing:**
- Fork test (ScottTodd/TheRock, run 21767399195): setup steps all passed
  (checkout, Python selection, --find-links, ROCm installation). Build hit
  ENOSPC on standard GitHub-hosted runner — expected.
- Upstream test — known-bad (run 21768200125): **FAILED as expected.** Same
  rocprim compilation error from #3042: `rocprim::is_floating_point<__half>::value
  was not satisfied`. Confirms this CI job would have caught the break pre-merge.
- gfx101X plumbing test (run 21879372876): pytorch build job correctly
  skipped for gfx101X (build_pytorch: false due to expect_failure +
  expect_pytorch_failure). CI Summary green.

**Notes:**
- Concurrency group (`workflow-sha`) means two workflow_dispatch runs on the
  same branch cancel each other. Had to run known-bad and known-good
  sequentially. Could encode inputs in concurrency group but that's separate.
- Branch is based on `users/scotttodd/python-package-test-2` with the
  `--find-links` commit cherry-picked. PR depends on #3261 and #3293.

### PR 3: CI pytorch opt-in labels + per-trigger narrowing

**Files changed:**
- `build_tools/github_actions/configure_ci.py`

**Changes:**
- `build:pytorch` label support for PRs (opt-in)
- Per-trigger-type defaults:
  - `pull_request`: false by default, `build:pytorch` label → gfx94x only
  - `push` (long-lived branch): gfx94x only
  - `schedule` (nightly): all non-broken families (same as PR 2)
  - `workflow_dispatch`: configurable
- Saves CI resources by restricting to 1-2 families on PR/postsubmit

**Testing:** Push to a branch with the `build:pytorch` label. Verify
the pytorch build job runs for gfx94x only.

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

### Phase 2 (future — still in TheRock)

- Test PyTorch in CI (after server-side index generation, or option 1 for single version)
  - Will need a narrower test set than nightly runs (see #2156)
- Restructure release workflow (after version precomputation, #1236)
- Converge CI and release onto a single build-only workflow

### Phase 3 (future — cross-repo)

- Enable triggering pytorch CI builds from rocm-libraries and rocm-systems repos (#3177)

## Side Tasks

- **Collapse Python version selection into one script:** The "Select Python
  version" and "Add selected Python version to PATH" steps are duplicated
  across 5 workflows (`build_portable_linux_pytorch_wheels.yml`,
  `build_windows_pytorch_wheels.yml`, `build_linux_jax_wheels.yml`,
  `copy_release.yml`, and our new CI workflow). Could be a single script call
  that writes to `GITHUB_PATH` itself using `gha_add_to_path()` from
  `build_tools/github_actions/github_actions_utils.py`. Note: both Linux and
  Windows workflows use `CP_VERSION` for wheel filename construction in their
  upload steps — further motivation to move upload logic into scripts and
  precompute versions/filenames rather than building them in YAML. The
  consolidation of the PATH-setting steps only applies to the Linux manylinux
  pattern (selecting from `/opt/python/{cp_version}/bin`); Windows uses
  `actions/setup-python` to select the build Python, though it could share the
  `cp_version` computation.
- ~~**Add gfx101X to `AOTRITON_UNSUPPORTED_ARCHS` in `build_prod_wheels.py`**~~ →
  [PR #3355](https://github.com/ROCm/TheRock/pull/3355) (draft, testing).
  Deduplicated the list, added gfx101X, version-gated gfx1152/53 enablement
  for pytorch ≥ 2.11. Test results:
  - Linux gfx1152: succeeded
  - Linux gfx1153: succeeded
  - Windows gfx101X: pytorch build succeeded, later failed on unrelated
    setuptools issue (#3311)
  - Linux gfx101X: still blocked by issue #1926 (CK bgemm), unrelated to aotriton
  - Decision: keep `expect_pytorch_failure` on gfx101x/linux (blocked by #1926),
    remove from gfx101x/windows (aotriton fix works). Removed `expect_failure`
    from gfx101x/linux (only `expect_pytorch_failure` needed now).
- **Converge `configure_ci.py` and `fetch_package_targets.py`:** Both iterate
  over `amdgpu_family_matrix.py` with similar extraction logic. Shared helpers
  for family iteration, input sanitization, and field extraction would reduce
  divergence. `fetch_package_targets.py` could be renamed `configure_release.py`
  to match the naming pattern. Not blocking for pytorch-ci but would reduce the
  surface area for bugs like the `expect_pytorch_failure` plumbing gap.

## Open Questions

- **CI runtime impact:** PyTorch builds are expensive. Build caching (separate task)
  will help. PR 2 builds for all non-broken families; PR 3 narrows to gfx94x
  only on PR/postsubmit to save resources.
- **`rocm_version` input:** The CI build needs `rocm_version` for
  `determine_version.py` to compute the version suffix. This is already available
  as `rocm_package_version` in `ci_linux.yml` inputs — need to confirm it's the
  right format.
- ~~**PR #3261 status:**~~ Merged. PR 2+ are unblocked.
