---
repositories:
  - therock
---

# Multi-Arch PyTorch Testing

- **Status:** In progress
- **Priority:** P1 (High)
- **Started:** 2026-05-01

## Overview

Enable running PyTorch tests on multi-arch packages (kpack-split wheels with
device extras like `torch[device-gfx942]`) as part of both release and CI
workflows. Related to issue #3332 and the multi-arch-releases task.

## Goals

- [x] Test workflows support `multi_arch=true` install path
- [x] Drop whl-staging-multi-arch, publish directly to whl-multi-arch
- [ ] Upfront manifest generation (freeze commits + compute versions)
- [ ] Restructure release workflow: orchestrator + reusable per-cell workflow
- [ ] Add test jobs that read from manifest
- [ ] Test matrix policy script
- [ ] Multi-arch CI workflows optionally call test workflows

## Context

### Issue and PR references

- Issue: https://github.com/ROCm/TheRock/issues/3332
- Issue: https://github.com/ROCm/TheRock/issues/5110 (manifest + workflow architecture)
- Issue: https://github.com/ROCm/TheRock/issues/1236 (commit manifests)
- PR #4996: `multi_arch` input for test workflows (in review)
- PR #5107: drop whl-staging, publish directly to whl-multi-arch (in review)

### Related work

- `tasks/active/multi-arch-releases.md` - multi-arch release pipelines
- `tasks/active/pytorch-ci.md` - PyTorch CI integration
- Issue #2156 - stabilize PyTorch release workflows
- Issue #3291 - build/test PyTorch in CI
- Issue #4889 - smoke test runner crash on Windows gfx120X

### Key files

```
# Test workflows
.github/workflows/test_pytorch_wheels.yml
.github/workflows/test_pytorch_wheels_full.yml

# Multi-arch release workflows (to be restructured)
.github/workflows/multi_arch_release_linux_pytorch_wheels.yml
.github/workflows/multi_arch_release_windows_pytorch_wheels.yml
.github/workflows/multi_arch_release_linux.yml      # parent, dispatches pytorch

# Old per-family (reference pattern for build→test→promote)
.github/workflows/release_portable_linux_pytorch_wheels.yml  # orchestrator
.github/workflows/build_portable_linux_pytorch_wheels.yml    # reusable per-cell

# Manifest generation
build_tools/github_actions/generate_pytorch_manifest.py      # current (post-build)
build_tools/github_actions/manifest_utils.py

# Supporting scripts
build_tools/github_actions/amdgpu_family_matrix.py
build_tools/github_actions/determine_version.py
build_tools/github_actions/publish_pytorch_to_release_bucket.py
external-builds/pytorch/build_prod_wheels.py
external-builds/pytorch/pytorch_torch_repo.py
```

## Completed work

### PR #4996 -- multi_arch input for test workflows

Added `multi_arch` boolean input to both test workflows. When true:
- `expand_amdgpu_families.py --output-mode=device-extras` expands family to
  device extras and writes to GITHUB_OUTPUT
- `setup_venv.py` installs `torch[device-gfx942]==$VERSION --index-url=$URL`
  (no `--index-subdir`)
- `rocm[devel,device-gfx942]` installed from same index (full test only)
- `summarize_test_pytorch_workflow.py` handles both args independently

Validation:
- Linux gfx942: tests passed, no regressions (run 25233709159)

### PR #5107 -- drop whl-staging, publish directly to whl-multi-arch

- Renamed `publish_pytorch_to_staging.py` -> `publish_pytorch_to_release_bucket.py`
- `v4/whl-staging` -> `v4/whl` (per-family v3 staging unchanged)
- RELEASES.md: removed staging, added multi-device/device-all examples,
  nightly instability warning, merged device-all into extras table
- external-builds/pytorch/README.md: rewrote gating section

## Design decisions

### Package promotion for multi-arch

**Decision:** Drop the staging-to-promoted index split for multi-arch.
Publish directly to `whl-multi-arch`. Tests run post-publish as signal
(HUD), not as a gate.

**Rationale:** Shared host `torch` wheel + independent device wheels make
clean promotion impossible. See #3332 discussion.

### Workflow architecture: orchestrator + reusable per-cell workflow

**Decision:** Mirror the per-family pattern. The orchestrator owns the
matrix; each cell is a reusable workflow containing build + test jobs.

**Why:** Tests should start as soon as their build cell finishes, not wait
for the entire build matrix. A reusable workflow per `(pytorch_ref,
python_version)` cell achieves this — the inner test job has `needs: build`
scoped to that cell only.

The inner test job fans out per-family (different GPU runners) using its
own `strategy.matrix` over families.

### Upfront manifest generation

**Decision:** Generate manifests BEFORE building, not after. Freeze
commits and compute versions in a lightweight job, write to S3. Build
and test jobs read from the manifest.

**Manifest format:** Same as existing manifests (see #5110), extended
with version info:

```json
{
  "pytorch": {
    "commit": "1a2700743c...",
    "repo": "https://github.com/ROCm/pytorch.git",
    "branch": "release/2.10",
    "version": "2.10.0"
  },
  "pytorch_audio": { ... },
  "pytorch_vision": { ... },
  "triton": { ... },
  "apex": { ... },
  "therock": { ... },
  "rocm_version": "7.13.0a20260501",
  "version_suffix": "+rocm7.13.0a20260501"
}
```

**Version derivation:** For torch, torchaudio, torchvision, and apex the
pattern is `version.txt + version_suffix`. The base version can be fetched
from the repo at the resolved commit via GitHub API (one file, no clone).
Triton is more complex (git hash in nightly versions) but gets pulled in
as a dependency — we don't need its version for testing.

**Checkout from manifest:** New entry point script that reads a manifest
and delegates to the existing `pytorch_*_repo.py checkout` scripts with
explicit commit SHAs. Single command to reproduce CI checkouts locally.

### Test matrix policy

**Decision:** A Python script (`configure_pytorch_test_matrix.py`)
generates the test matrix, controlling which `(pytorch_ref,
python_version, family, test_level)` combinations to test.

**Policy examples:**
- Test latest stable pytorch on py3.12 with full suite for gfx942
- Test other pytorch versions with smoketests only
- Skip python versions that pytorch upstream doesn't test
- Skip families with no test runners

**Data sources:**
- `amdgpu_family_matrix.py` for runner labels
- Manifest for versions
- Policy defined in the script itself (easy to update and test)

## PR sequencing

### PR 3: Upfront manifest generation

- New/extended `generate_pytorch_manifest.py`: resolve refs -> commits
  via GitHub API, fetch `version.txt` per repo, compute versions
- New checkout-from-manifest script
- Add `generate_manifest` job to orchestrator
- Build job reads manifest for checkouts and version info
- Upload manifest to S3

### PR 4: Test matrix + test jobs

- New `configure_pytorch_test_matrix.py` with test policy
- Split orchestrator + reusable per-cell workflow
- Inner test job calls `test_pytorch_wheels.yml` with `multi_arch: true`
- Per-family fan-out inside the reusable workflow

### Later: Windows, CI integration

- Same pattern for `multi_arch_release_windows_pytorch_wheels.yml`
- Wire into CI workflows for pre-submit testing (#3291)

## Windows test signal (as of 2026-05-01)

| Target | Runners? | torch 2.9 | torch 2.10 | torch 2.11+ |
|--------|----------|-----------|------------|-------------|
| gfx110X-all | Yes | Segfault | 15,539 passed (0501) | Cancelled |
| gfx1151 | Yes | 1,924 failed + 36,950 errors | py3.11 passed, rest segfault | Failed |
| gfx120X-all | Yes | Failed | Blocked by #4889 (smoke test bug) | Cancelled |
| Others (8 families) | No runners | Skipped | Skipped | Skipped |

**Only clean signal:** gfx110X-all + torch 2.10 on 20260501.
