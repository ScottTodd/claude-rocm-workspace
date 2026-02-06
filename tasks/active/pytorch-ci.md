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
# Workflows to modify
.github/workflows/ci_linux.yml
.github/workflows/ci_windows.yml
.github/workflows/build_portable_linux_pytorch_wheels.yml
.github/workflows/build_windows_pytorch_wheels.yml
.github/workflows/release_portable_linux_pytorch_wheels.yml
.github/workflows/test_pytorch_wheels.yml

# Build scripts
external-builds/pytorch/build_prod_wheels.py
external-builds/pytorch/pytorch_torch_repo.py
external-builds/pytorch/sanity_check_wheel.py

# Upload/index tooling
build_tools/github_actions/upload_python_packages.py
third-party/indexer/indexer.py

# Test infrastructure
build_tools/setup_venv.py

# Documentation
docs/development/github_actions_debugging.md
```

## Design

### Architecture: "Build only builds, test only tests, release only releases"

**Decision:** Option B — extend existing workflows, with clear responsibility separation.

The key principle: each workflow has one job.

| Workflow | Responsibility |
|----------|---------------|
| `build_portable_linux_pytorch_wheels.yml` | Build PyTorch wheels + upload to artifacts bucket |
| `test_pytorch_wheels.yml` | Test PyTorch wheels on GPU runners |
| `release_portable_linux_pytorch_wheels.yml` | Matrix orchestration + staging copy + test + promote |
| `ci_linux.yml` | CI orchestration: build → test (no promotion) |

This means moving `generate_target_to_run`, `test_pytorch_wheels`, and
`upload_pytorch_wheels` **out of** the build workflow and **into** the release workflow.

### Current vs Target Workflow Structure

**Current** (`build_portable_linux_pytorch_wheels.yml` does everything):
```
build_portable_linux_pytorch_wheels.yml:
  build_pytorch_wheels        # build + upload to staging
  generate_target_to_run      # determine test runner
  test_pytorch_wheels         # test from staging
  upload_pytorch_wheels       # promote staging → release

release_portable_linux_pytorch_wheels.yml:
  release (matrix wrapper)    # calls build workflow for each python × pytorch combo
```

**Target** (clean separation):
```
build_portable_linux_pytorch_wheels.yml:
  build_pytorch_wheels        # build + upload to CI artifacts bucket
  outputs: package_find_links_url, torch_version, etc.

release_portable_linux_pytorch_wheels.yml:
  build (matrix wrapper)      # calls build workflow for each python × pytorch combo
  copy_to_staging             # copy from artifacts bucket to release staging
  generate_target_to_run      # determine test runner
  test_pytorch_wheels         # test from staging URL
  promote_to_release          # promote staging → release (based on policy)

ci_linux.yml:
  ...existing jobs...
  build_pytorch_wheels        # calls build workflow (gets package_find_links_url)
  test_pytorch_wheels         # calls test workflow (using find-links URL)
```

### Changes to `build_portable_linux_pytorch_wheels.yml`

**Remove these jobs:**
- `generate_target_to_run`
- `test_pytorch_wheels`
- `upload_pytorch_wheels`

**Remove these steps from `build_pytorch_wheels` job:**
- "Upload wheels to S3 staging" (raw `aws s3 cp` to release bucket)
- "(Re-)Generate Python package release index for staging" (`manage.py`)

**Add these steps to `build_pytorch_wheels` job:**
- "Upload Python packages" using `upload_python_packages.py` (same as ROCm packages)
  - Uploads to `therock-ci-artifacts/{run_id}-{platform}/python/{artifact_group}/`
  - Generates flat `index.html` via `indexer.py`
  - Sets `package_find_links_url` output

**Add/modify inputs:**
- Add `rocm_package_find_links_url` (optional) — CI provides this; release provides `cloudfront_url`
- Keep `cloudfront_url` for release workflow compatibility
- Remove `s3_subdir`, `s3_staging_subdir`, `cloudfront_staging_url` (release-only concerns)
- Keep `release_type` for now (used for IAM role selection — may need refactoring)

**Add workflow outputs:**
```yaml
outputs:
  package_find_links_url:
    value: ${{ jobs.build_pytorch_wheels.outputs.package_find_links_url }}
  torch_version:
    value: ${{ jobs.build_pytorch_wheels.outputs.torch_version }}
  torchaudio_version: ...
  torchvision_version: ...
  triton_version: ...
```

**ROCm installation logic:**
```bash
# CI mode (find-links):
./external-builds/pytorch/build_prod_wheels.py build \
  --install-rocm \
  --find-links "${{ inputs.rocm_package_find_links_url }}" \
  --clean --output-dir ...

# Release mode (index-url):
./external-builds/pytorch/build_prod_wheels.py build \
  --install-rocm \
  --index-url "${{ inputs.cloudfront_url }}/${{ inputs.amdgpu_family }}/" \
  --clean --output-dir ...
```

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

### Changes to `release_portable_linux_pytorch_wheels.yml`

Currently a thin matrix wrapper. Needs to become a multi-job workflow:

```yaml
jobs:
  build:
    # Matrix over python_version × pytorch_git_ref (existing)
    uses: ./.github/workflows/build_portable_linux_pytorch_wheels.yml
    with:
      cloudfront_url: ${{ inputs.cloudfront_url }}
      # ... same inputs as now, minus staging/promote concerns
    # Gets back: package_find_links_url, torch_version, etc.

  copy_to_staging:
    needs: [build]
    # Copy wheels from CI artifacts bucket to release staging bucket
    # aws s3 cp from artifacts → staging

  generate_target_to_run:
    # Same as current job in build workflow

  test_pytorch_wheels:
    needs: [copy_to_staging, generate_target_to_run]
    uses: ./.github/workflows/test_pytorch_wheels.yml
    with:
      package_index_url: ${{ inputs.cloudfront_staging_url }}
      # Uses staging URL (PEP-503) not find-links

  promote_to_release:
    needs: [build, test_pytorch_wheels, generate_target_to_run]
    # Same promote_wheels_based_on_policy.py logic as current upload_pytorch_wheels job
```

**Challenge:** The release workflow currently uses `strategy.matrix` which creates
independent instances of the called workflow. If we need multi-job orchestration
(build → copy → test → promote) per matrix entry, we may need to restructure.

**Options:**
1. Make `release_portable_linux_pytorch_wheels.yml` call a new
   `release_single_pytorch_wheels.yml` that handles one (python, pytorch_ref) combo
2. Keep the matrix in the build call, then use a separate job to iterate over results
3. Move orchestration into a single job with sequential steps

This needs more investigation. For MVP, we can keep the release workflow calling the
build workflow as-is and add staging/promote as separate follow-up jobs.

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
        └── index.html                  # flat index listing ALL packages
```

**Benefit:** Single `--find-links` URL covers both ROCm and PyTorch for test install.

**Challenge:** `upload_python_packages.py` generates `index.html` from local
`--input-packages-dir`. When PyTorch uploads second, it won't know about
the ROCm packages already in S3. Options:

1. **Regenerate from S3:** Have the upload script list existing S3 objects and
   include them in the generated index. The `indexer.py` already generates from
   directory listings — could adapt to list S3 contents via `aws s3 ls`.
2. **Append mode:** Download existing `index.html`, parse it, add new entries.
3. **Upload all at once:** Have the PyTorch build step also download the ROCm
   packages (or at least their filenames) to include in index generation.

Option 1 is cleanest. Need to check if `upload_python_packages.py` can be extended.

### Changes to `test_pytorch_wheels.yml`

Add `package_find_links_url` as an alternative to `package_index_url`:

```yaml
inputs:
  package_index_url:
    type: string
    default: ""  # Used by release (PEP-503)
  package_find_links_url:
    type: string
    default: ""  # Used by CI (flat index)
```

Update the "Set up virtual environment" step:
```bash
# CI mode:
python build_tools/setup_venv.py ${VENV_DIR} \
  --packages torch==${{ inputs.torch_version }} \
  --find-links-url=${{ inputs.package_find_links_url }} \
  --activate-in-future-github-actions-steps

# Release mode:
python build_tools/setup_venv.py ${VENV_DIR} \
  --packages torch==${{ inputs.torch_version }} \
  --index-url=${{ inputs.package_index_url }} \
  --index-subdir=${{ inputs.amdgpu_family }} \
  --activate-in-future-github-actions-steps
```

With the shared `python/` directory, a single `--find-links` URL provides
both ROCm and PyTorch packages, so torch's dependency on rocm-sdk is resolved
from the same index.

### CI Workflow Orchestration in `ci_linux.yml`

```yaml
build_pytorch_wheels:
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
  uses: ./.github/workflows/build_portable_linux_pytorch_wheels.yml
  with:
    amdgpu_family: ${{ inputs.artifact_group }}
    python_version: "3.12"
    pytorch_git_ref: "nightly"
    rocm_package_find_links_url: ${{ needs.build_portable_linux_python_packages.outputs.package_find_links_url }}
  permissions:
    contents: read
    id-token: write

test_pytorch_wheels:
  needs: [build_pytorch_wheels]
  name: Test PyTorch
  if: >-
    ${{
      !failure() &&
      !cancelled() &&
      inputs.expect_failure == false &&
      inputs.test_runs_on != ''
    }}
  uses: ./.github/workflows/test_pytorch_wheels.yml
  with:
    amdgpu_family: ${{ inputs.artifact_group }}
    test_runs_on: ${{ inputs.test_runs_on }}
    package_find_links_url: ${{ needs.build_pytorch_wheels.outputs.package_find_links_url }}
    torch_version: ${{ needs.build_pytorch_wheels.outputs.torch_version }}
    pytorch_git_ref: "nightly"
    python_version: "3.12"
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

**`upload_python_packages.py` and shared directory:**
- Currently generates `index.html` from local `--input-packages-dir` contents only
- For shared directory, second upload (PyTorch) needs to regenerate index
  including already-uploaded ROCm packages
- Need to extend script to list S3 directory contents when regenerating index,
  OR pass multiple local directories, OR download existing index and merge

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

- **Option B:** Extend existing build workflow for both CI and release
- **Build workflow responsibility:** Build + upload to artifacts bucket only
- **Release workflow responsibility:** Matrix + staging + test + promote
- **CI workflow responsibility:** Build + test (no promotion)
- **Shared `python/` directory:** ROCm and PyTorch packages share the same S3
  subdirectory and `index.html`, simplifying `--find-links` URL to a single URL
- **CI scope defaults:** One Python version (3.12), 1-2 PyTorch refs (nightly + maybe latest stable)
- **CI opt-in:** `build:pytorch` PR label; always-on for postsubmit/nightly
- **`build_prod_wheels.py`:** Add `--find-links` flag to `add_common()` and
  use in `do_install_rocm()` alongside or instead of `--index-url`

## Next Steps

1. [ ] Add `--find-links` to `build_prod_wheels.py` (`add_common()` + `do_install_rocm()`)
2. [ ] Refactor `build_portable_linux_pytorch_wheels.yml`:
   - Remove `generate_target_to_run`, `test_pytorch_wheels`, `upload_pytorch_wheels` jobs
   - Remove staging upload steps from `build_pytorch_wheels` job
   - Add `upload_python_packages.py` step
   - Add `rocm_package_find_links_url` input
   - Add workflow-level outputs
3. [ ] Extend `upload_python_packages.py` to handle shared directory (regenerate
   index including existing S3 objects)
4. [ ] Update `test_pytorch_wheels.yml` to accept `package_find_links_url` input
5. [ ] Refactor `release_portable_linux_pytorch_wheels.yml` to include staging +
   test + promote (moved from build workflow)
6. [ ] Add `build_pytorch` output to `configure_ci.py` with label support
7. [ ] Add `build_pytorch_wheels` and `test_pytorch_wheels` jobs to `ci_linux.yml`
8. [ ] Repeat for Windows (`build_windows_pytorch_wheels.yml`, `ci_windows.yml`)
9. [ ] Update `docs/development/github_actions_debugging.md`
10. [ ] End-to-end CI test run
11. [ ] Review and iterate

## Open Questions

- **Release workflow matrix restructuring:** How to handle multi-job orchestration
  per matrix entry? Need intermediate "release single" workflow, or conditional
  logic in build workflow for release mode?
- **CI runtime impact:** PyTorch builds are expensive. Build caching (separate task)
  will help, but for now, opt-in via label + always-on for postsubmit keeps costs down.
- **Shared index regeneration:** Which approach for `upload_python_packages.py`?
  S3 listing seems cleanest but adds AWS API dependency to index generation.
- **PR #3261 status:** This task is blocked until python-packages-ci lands.
