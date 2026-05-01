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
- [ ] Multi-arch release workflows call test workflows after build
- [ ] Script to generate the pytorch test matrix (families, runners, python/torch versions)
- [ ] Multi-arch CI workflows optionally call test workflows

## Context

### Issue and PR references

- Issue: https://github.com/ROCm/TheRock/issues/3332
- PR #4996: `multi_arch` input for test workflows (step 1, in review)

### Related work

- `tasks/active/multi-arch-releases.md` - multi-arch release pipelines
- `tasks/active/pytorch-ci.md` - PyTorch CI integration
- Issue #2156 - stabilize PyTorch release workflows
- Issue #3291 - build/test PyTorch in CI
- Issue #4889 - smoke test runner crash on Windows gfx120X (blocks all gfx120X pytorch tests)

### Key files

```
.github/workflows/test_pytorch_wheels.yml          # basic test (smoketest + subset)
.github/workflows/test_pytorch_wheels_full.yml      # full test suite (sharded)
.github/workflows/multi_arch_release_linux_pytorch_wheels.yml
.github/workflows/multi_arch_release_windows_pytorch_wheels.yml
.github/workflows/multi_arch_release_linux.yml      # parent, has test_artifacts_per_family pattern
.github/workflows/build_portable_linux_pytorch_wheels.yml  # old per-family, has test+promote pattern
build_tools/github_actions/amdgpu_family_matrix.py  # runner labels per family
build_tools/github_actions/configure_target_run.py  # old per-family runner lookup
build_tools/github_actions/promote_wheels_based_on_policy.py
```

## Completed work (PR #4996)

Added `multi_arch` boolean input to both test workflows. When true:
- `expand_amdgpu_families.py --output-mode=device-extras` expands family to
  device extras and writes to GITHUB_OUTPUT
- `setup_venv.py` installs `torch[device-gfx942]==$VERSION --index-url=$URL`
  (no `--index-subdir`)
- `rocm[devel,device-gfx942]` installed from same index (full test only)
- `summarize_test_pytorch_workflow.py` handles both args independently

### Validation

- Linux gfx942: tests passed, no regressions from multi-arch packaging
  (run 25233709159)
- Windows gfx1151: queued (testing 2.11.0+rocm7.13.0a20260501 from
  whl-staging-multi-arch)

## Design decisions

### Package promotion for multi-arch

**Decision:** Drop the staging-to-promoted index split for multi-arch.
Publish directly to `whl-multi-arch`.

**Rationale:** The shared host `torch` wheel and independent device wheels
make clean promotion impossible:
- Publishing `torch` before its device packages breaks `pip install torch[device-gfxNNN]`
- Partial promotion (gfx1100 passes, gfx942 fails) requires the host wheel
  to already be in the index
- Waiting for all targets blocks on the slowest runner (70+ min queues observed)

**Signal instead of gating:** The HUD at therock-hud-dev.amd.com shows test
status. Stable releases provide the "known good" install path. Nightlies can
be more permissive.

See discussion: https://github.com/ROCm/TheRock/issues/3332#issuecomment-4361527784

### Test matrix generation

**Decision:** New Python script (similar to `configure_ci.py`,
`configure_target_run.py`) that constructs the test matrix.

**What it needs to produce per entry:**
- `amdgpu_family` (e.g. `gfx94X-dcgpu`)
- `test_runs_on` (runner label from `amdgpu_family_matrix.py`)
- `torch_version` (from build outputs)
- `pytorch_git_ref` (which pytorch branch to test)
- `python_version`
- Platform (linux/windows)

**Policy control:** The script should define policy for what to test vs what
to build. Not every (python_version x pytorch_git_ref) combination needs
testing. For example, if pytorch upstream doesn't test python 3.13, we
shouldn't overburden ourselves testing it downstream. The script is the right
place for this policy since it's easy to update and test.

**Data source:** `amdgpu_family_matrix.py` already has `test-runs-on` per
family per platform. The script reads that plus the semicoloned
`amdgpu_families` input.

### Inline matrix vs separate dispatched jobs

**Trade-offs:**

| Approach | Pros | Cons |
|----------|------|------|
| Inline matrix (strategy.matrix in the release workflow) | See all families in one workflow run | Can't cancel/retrigger individually |
| Separate dispatched jobs (workflow_dispatch per family) | Cancel/retrigger individually, feeds into HUD as separate entries | Harder to see cross-GPU picture, more dispatch plumbing |

**Leaning toward:** Separate dispatched jobs, matching the pattern at
`release_portable_linux_pytorch_wheels.yml` run history. Individual jobs
are more practical when runners are scarce and queues are long.

### Torch version extraction

The multi-arch build matrix is `python_version x pytorch_git_ref`. Each cell
produces a torch version like `2.10.0+rocm7.13.0a20260501`. The test needs
this version string.

**Options:**
1. Add `write_torch_versions.py` to multi-arch build jobs, output per cell
2. Pick one representative cell (e.g. py3.12) and test that
3. Have the test install latest from the index without pinning a version

**Not decided yet.** Depends on whether we test multiple python versions and
how we structure the test dispatch.

## Windows test signal (as of 2026-05-01)

Investigated the `release_windows_pytorch_wheels.yml` run history:

| Target | Runners? | torch 2.9 | torch 2.10 | torch 2.11+ |
|--------|----------|-----------|------------|-------------|
| gfx110X-all | Yes | Segfault | 15,539 passed (0501) | Cancelled |
| gfx1151 | Yes | 1,924 failed + 36,950 errors | py3.11 passed, rest segfault | Failed |
| gfx120X-all | Yes | Failed | Blocked by #4889 (smoke test bug) | Cancelled |
| Others (8 families) | No runners | Skipped | Skipped | Skipped |

**Only clean signal:** gfx110X-all + torch 2.10 on 20260501.
This was segfaulting on 0425 and 0430, fixed between 0430 and 0501.

## Next steps

1. [ ] Confirm PR #4996 passes review, merge
2. [ ] Write the test matrix generation script
3. [ ] Add test jobs to `multi_arch_release_linux_pytorch_wheels.yml`
4. [ ] Add test jobs to `multi_arch_release_windows_pytorch_wheels.yml`
5. [ ] Validate end-to-end on a nightly release run
6. [ ] Update RELEASES.md note about testing ("we'll recommend 'whl-multi-arch'
       instead of 'whl-staging-multi-arch' as soon as we automate tests")
