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

## Design Considerations

### Key Challenge: ROCm Package Source

Release workflows install ROCm from a cloudfront URL (`--index-url`). CI needs to install ROCm from the same run's artifacts (`--find-links`).

**`build_prod_wheels.py` currently uses `--install-rocm` with `--index-url`.**
Need to investigate whether it can accept `--find-links` for ROCm installation,
or whether we need to pre-install ROCm packages before invoking it.

### Option A: Separate CI Workflow

Create a new `build_ci_pytorch_wheels.yml` that accepts `rocm_package_find_links_url` as input, builds PyTorch, and uploads to CI artifacts.

**Pros:** Clean separation, CI-specific logic doesn't pollute release workflow.
**Cons:** Code duplication between CI and release build workflows; divergence risk (the very thing we're trying to fix).

### Option B: Extend Existing Build Workflow

Add CI-mode inputs to `build_portable_linux_pytorch_wheels.yml` so it can source ROCm packages from either a release index (`--index-url`) or CI artifacts (`--find-links`).

**Pros:** Single source of truth for how PyTorch is built; release and CI share the same code path.
**Cons:** More complex workflow with conditional logic; risk of accidentally breaking release workflow.

### Option C: Hybrid — Shared Composite Action + Separate Orchestration

Extract the core build/upload steps into a reusable composite action or shared workflow fragment. Both CI and release workflows call the same building block but with different inputs.

**Pros:** Shared code, clean separation of orchestration concerns.
**Cons:** Composite actions have limitations (no `container:` support); may need to use reusable workflow instead.

### Recommendation

Leaning toward **Option B** — the user's stated goal is that CI and release should share building blocks and that CI passing should give confidence in release. This argues for making the build workflow flexible enough to serve both purposes, with the release workflow being a thin matrix wrapper around it.

**Open question for user:** What's the preferred approach? Option B seems aligned with the stated goal of "configurable CI" but adds complexity to the existing release workflow.

### S3 Layout for PyTorch CI Wheels

Following the pattern from python-packages-ci:

```
s3://therock-ci-artifacts/
└── {run_id}-{platform}/
    ├── python/{artifact_group}/        # ROCm packages (from python-packages-ci)
    │   ├── *.whl
    │   └── index.html
    └── pytorch/{artifact_group}/       # PyTorch packages (NEW)
        ├── torch-*.whl
        ├── torchvision-*.whl
        ├── torchaudio-*.whl
        ├── triton-*.whl               # Linux only
        └── index.html                 # flat index for --find-links
```

### Test Workflow Compatibility

`test_pytorch_wheels.yml` currently expects `package_index_url` (PEP-503 base URL). For CI:
- Need to support `package_find_links_url` as alternative input
- `setup_venv.py` already has `--find-links-url` support (from PR #3242)
- Both ROCm and PyTorch packages need to be findable during test install:
  - ROCm packages: from CI `python/{artifact_group}/` path
  - PyTorch packages: from CI `pytorch/{artifact_group}/` path
  - May need multiple `--find-links` URLs, or a combined index

### CI Workflow Orchestration

Proposed job chain in `ci_linux.yml`:

```
build_portable_linux_artifacts
  ↓
build_portable_linux_python_packages → outputs: rocm_package_find_links_url
  ↓
test_rocm_wheels (existing)
  ↓
build_pytorch_wheels → outputs: pytorch_package_find_links_url, torch_version
  ↓
test_pytorch_wheels
```

### Configurability

The CI workflow should be configurable for:
- `pytorch_git_ref` — which PyTorch branch to build (nightly, release/2.7, etc.)
- `python_version` — which Python version(s) to build for
- Whether to build PyTorch at all (opt-in per run or per-PR)
- Which components (torch only vs torch+audio+vision+triton)

### Documentation Updates

- `docs/development/github_actions_debugging.md` — "Testing PyTorch release workflows" section needs updating to reflect that CI can now validate most changes, and when you should still use the release workflow
- Potentially add a "CI workflow reference" section showing the full CI pipeline

## Investigation Notes

### 2026-02-06 - Initial Analysis

**Dependency chain analysis:**
- PyTorch build needs ROCm packages → must wait for `build_portable_linux_python_packages` to complete
- PyTorch test needs both ROCm and PyTorch packages + GPU runner
- Total chain: artifacts → rocm packages → pytorch wheels → pytorch tests
- This is a long chain; CI runtime will increase significantly

**`build_prod_wheels.py` ROCm installation:**
- Uses `--install-rocm` flag which triggers `pip install` from `--index-url`
- Need to check if it can accept `--find-links` instead, or if we pre-install

**`test_pytorch_wheels.yml` compatibility:**
- Currently uses `package_index_url` (PEP-503 `--index-url` with `--index-subdir`)
- CI artifacts use flat `--find-links` format
- `setup_venv.py` already supports `--find-links-url` (PR #3242)
- Need to add `package_find_links_url` input to `test_pytorch_wheels.yml`
- For testing, both ROCm and PyTorch packages need to be accessible

**Release vs CI workflow divergence points:**
- ROCm package source: cloudfront (release) vs S3 CI artifacts (CI)
- S3 bucket: `therock-{release_type}-python` (release) vs `therock-ci-artifacts` (CI)
- Index format: PEP-503 with `manage.py` (release) vs flat with `indexer.py` (CI)
- Promotion: staging→release flow (release) vs none (CI)
- Orchestration: inline in build workflow (release) vs ci_linux.yml (CI)

## Next Steps

1. [ ] Deep-dive into `build_prod_wheels.py` to understand ROCm package installation
2. [ ] Decide on Option A vs B vs C (discuss with user)
3. [ ] Prototype changes to build workflow to accept CI artifact URLs
4. [ ] Update `test_pytorch_wheels.yml` to accept `--find-links` input
5. [ ] Integrate pytorch build job into `ci_linux.yml`
6. [ ] Integrate pytorch test job into `ci_linux.yml`
7. [ ] Repeat for Windows (`ci_windows.yml`)
8. [ ] Update documentation
9. [ ] End-to-end CI test run
10. [ ] Review and iterate

## Open Questions

- **Option A vs B vs C?** How much should we share between CI and release workflows?
- **CI runtime impact?** PyTorch builds are expensive. Should this be opt-in per PR?
- **Python version matrix in CI?** Release builds all of 3.11/3.12/3.13. CI might only need one.
- **PyTorch ref in CI?** Should CI default to `nightly` or track a specific release branch?
- **Combined index?** How to make both ROCm and PyTorch packages findable during test install?
- **PR #3261 status?** This task is blocked until python-packages-ci lands.
