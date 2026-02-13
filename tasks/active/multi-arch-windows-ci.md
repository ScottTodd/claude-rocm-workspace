---
repositories:
  - therock
---

# Multi-Arch Windows CI Workflows

- **Status:** Not started
- **Priority:** P1 (High)
- **Started:** 2026-02-11
- **Issue:** https://github.com/ROCm/TheRock/issues/3325
- **Parent issue:** https://github.com/ROCm/TheRock/issues/3323
- **Depends on:** Linux multi-arch pipeline (already landed)

## Overview

Create Windows equivalents of the Linux multi-arch CI workflows. The Linux
pipeline (`multi_arch_build_portable_linux.yml`, `multi_arch_ci_linux.yml`)
breaks the monolithic build into stages that flow artifacts between jobs via
S3, enabling per-architecture parallelism for the expensive math-libs stage.
Windows needs the same treatment.

## Goals

- [ ] Create `multi_arch_build_portable_windows.yml` (staged build pipeline)
- [ ] Create `multi_arch_ci_windows.yml` (orchestration: build + test)
- [ ] Uncomment and wire up Windows in `multi_arch_ci.yml`
- [ ] Verify `configure_ci.py` multi-arch output works for Windows variants
- [ ] End-to-end test via `workflow_dispatch` on a branch
- [ ] Trim redundant setup steps and align with style guides (both platforms)

## Context

### Linux Multi-Arch Pipeline (Reference)

The Linux pipeline splits the build into 7 stages with a DAG dependency structure:

```
foundation (generic)
├── compiler-runtime (generic)
│   ├── math-libs (per-arch)     ← main parallelism point
│   ├── comm-libs (per-arch)     ← parallel to math-libs
│   ├── dctools-core (generic)   ← parallel to math-libs
│   └── profiler-apps (generic)  ← parallel to math-libs
└── media (generic)              ← parallel to compiler-runtime
```

Each stage: checkout → fetch inbound artifacts → fetch sources → configure →
build → push artifacts. Artifacts flow via `artifact_manager.py` + S3.

### Windows Stage Subset

Many stages are disabled on Windows (`disable_platforms = ["windows"]` in
`BUILD_TOPOLOGY.toml`):

| Stage | Linux | Windows | Why disabled |
|-------|-------|---------|-------------|
| foundation | generic | generic | -- |
| compiler-runtime | generic | generic | -- |
| math-libs | per-arch | per-arch | -- |
| comm-libs | per-arch | **disabled** | RCCL disabled on Windows |
| dctools-core | generic | **disabled** | RDC disabled on Windows |
| profiler-apps | generic | **disabled** | rocprofiler-systems disabled |
| media | generic | **disabled** | Mesa/VA-API disabled on Windows |

**Windows pipeline is only 3 stages:**

```
foundation (generic)
└── compiler-runtime (generic)
    └── math-libs (per-arch)
```

This is significantly simpler than Linux. The DAG is linear until math-libs
fans out per architecture.

### Supporting Tool Readiness

All supporting scripts are Windows-ready:

| Tool | Windows Status | Notes |
|------|---------------|-------|
| `configure_stage.py` | Ready | Platform-agnostic; `BUILD_TOPOLOGY.toml` filters by platform |
| `artifact_manager.py` | Ready | Uses `platform.system().lower()` for S3 paths |
| `fetch_sources.py` | Ready | Has `is_windows()` checks, platform-aware submodule filtering |
| `setup_ccache.py` | Ready | Cross-platform; not currently called in Windows workflows |
| `health_status.py` | Ready | Extensive Windows-specific toolchain checks |

### Environment Differences from Linux

| Aspect | Linux | Windows |
|--------|-------|---------|
| Execution | Container (`manylinux`) | Native runner (`azure-windows-scale-rocm`) |
| Compiler | gcc/clang in container | MSVC via `ilammy/msvc-dev-cmd` |
| Tools | Pre-installed in container | Chocolatey install (ccache, ninja, perl, awscli, pkgconfiglite) |
| Python | `/opt/python/cp312-cp312/bin/python` | `actions/setup-python@v6` |
| Build dir | `build/` (workspace-relative) | `B:\build` (separate drive) |
| Cache | ccache + bazel-remote (via `setup_ccache.py`) | GitHub Actions cache (insufficient — migrate to `setup_ccache.py`) |
| AWS creds | Container volume mount (`-v /runner/config:/home/awsconfig/`) | Default credential chain + `special-characters-workaround` |
| Git config | `safe.directory` | `safe.directory` + `core.symlinks` + `core.longpaths` |
| DVC | Pre-installed in container | `iterative/setup-dvc@v2.0.0` action |

### Related Work

- **Linux multi-arch pipeline:** `multi_arch_build_portable_linux.yml` + `multi_arch_ci_linux.yml` (landed)
- **`multi_arch_ci.yml`:** Top-level entry point (has commented-out Windows section at lines 98-112)
- **`ci_windows.yml`:** Existing single-arch Windows orchestration (reference for job structure)
- **`build_windows_artifacts.yml`:** Existing single-arch Windows build (reference for env setup)
- **Task `pytorch-ci`:** Phase 3 will add PyTorch building to Windows CI — depends on this task's `ci_windows` orchestration
- **KPack on Windows:** Not yet implemented; `THEROCK_KPACK_SPLIT_ARTIFACTS` is non-functional on Windows
- **Issue #902:** Migrate ccache backend from GitHub to self-hosted (k8s) — tracks bazel-remote setup
- **PR #2415:** Draft PR to switch Windows builds to bazel-remote — stalled on config/path issues

### Directories/Files Involved

```
# New workflows
.github/workflows/multi_arch_build_portable_windows.yml  (NEW)
.github/workflows/multi_arch_ci_windows.yml               (NEW)

# Workflows to modify
.github/workflows/multi_arch_ci.yml   # Uncomment Windows section

# Reference workflows (templates)
.github/workflows/multi_arch_build_portable_linux.yml  # Linux staged build
.github/workflows/multi_arch_ci_linux.yml              # Linux orchestration
.github/workflows/build_windows_artifacts.yml          # Windows env setup patterns
.github/workflows/ci_windows.yml                       # Windows orchestration patterns

# Supporting tools (used as-is, already Windows-ready)
build_tools/configure_stage.py
build_tools/artifact_manager.py
build_tools/fetch_sources.py
build_tools/setup_ccache.py
build_tools/health_status.py
BUILD_TOPOLOGY.toml
```

## Design

### `multi_arch_build_portable_windows.yml` — Staged Build Pipeline

Three jobs in sequence: foundation → compiler-runtime → math-libs (per-arch).

Each job follows the same pattern, adapted from the Linux pipeline but with
Windows environment setup instead of container setup.

**Inputs** — same as Linux pipeline:

```yaml
inputs:
  artifact_group: { type: string }
  matrix_per_family_json: { type: string }
  dist_amdgpu_families: { type: string }
  build_variant_label: { type: string }
  build_variant_cmake_preset: { type: string }
  build_variant_suffix: { type: string }
  expect_failure: { type: boolean }
  use_prebuilt_artifacts: { type: string }
  rocm_package_version: { type: string }
  test_type: { type: string }
```

**Common steps per job** (Windows-specific env setup):

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: actions/setup-python@v6
    with: { python-version: "3.12" }
  - run: pip install -r requirements.txt
  - run: |  # Install build tools (winget or bake into base image)
      # ccache, ninja, strawberryperl, pkgconfiglite
      # (awscli replaced by boto3; choco replaced by winget)
  - uses: iterative/setup-dvc@v2.0.0
  - uses: ilammy/msvc-dev-cmd@v1.13.0
  - run: |  # Git config
      git config --global --add safe.directory $PWD
      git config --global core.symlinks true
      git config --global core.longpaths true
      git config fetch.parallel 10
  # Then stage-specific: setup_ccache → health_status → AWS creds → fetch artifacts → fetch sources → configure_stage → cmake configure → build → push artifacts
```

**Per-stage differences:**

| Stage | `needs` | Matrix | `--amdgpu-families` | `--bootstrap` |
|-------|---------|--------|---------------------|---------------|
| foundation | (none) | (none) | (none) | (no fetch) |
| compiler-runtime | foundation | (none) | (none) | yes |
| math-libs | compiler-runtime | `matrix_per_family_json` | per-family | yes |

### `multi_arch_ci_windows.yml` — Orchestration Layer

Mirrors `multi_arch_ci_linux.yml` structure: build stages → test per-family.

```yaml
jobs:
  build_multi_arch_stages:
    if: inputs.use_prebuilt_artifacts == 'false'
    uses: ./.github/workflows/multi_arch_build_portable_windows.yml
    # pass through all inputs

  test_artifacts_per_family:
    needs: [build_multi_arch_stages]
    if: >-
      !failure() && !cancelled() &&
      (inputs.use_prebuilt_artifacts == 'false' || inputs.use_prebuilt_artifacts == 'true') &&
      inputs.expect_failure == false
    strategy:
      matrix:
        family_info: ${{ fromJSON(inputs.matrix_per_family_json) }}
    uses: ./.github/workflows/test_artifacts.yml
    with:
      artifact_group: ${{ matrix.family_info.amdgpu_family }}
      amdgpu_families: ${{ matrix.family_info.amdgpu_family }}
      test_runs_on: ${{ matrix.family_info.test-runs-on }}
      # ...
```

**Inputs** — same as Linux orchestration workflow:

```yaml
inputs:
  artifact_group: { type: string }
  matrix_per_family_json: { type: string }
  dist_amdgpu_families: { type: string }
  build_variant_label: { type: string }
  build_variant_cmake_preset: { type: string }
  build_variant_suffix: { type: string }
  test_labels: { type: string }
  artifact_run_id: { type: string }
  expect_failure: { type: boolean }
  use_prebuilt_artifacts: { type: string }
  rocm_package_version: { type: string }
  test_type: { type: string }
```

### `multi_arch_ci.yml` — Uncomment Windows Section

The commented-out block at lines 98-112 references `ci_windows.yml`, but it
should call `multi_arch_ci_windows.yml` instead (matching the Linux pattern):

```yaml
windows_build_and_test:
  name: Windows::${{ matrix.variant.build_variant_label }}
  needs: setup
  if: >-
    ${{
      needs.setup.outputs.windows_variants != '[]' &&
      needs.setup.outputs.enable_build_jobs == 'true'
    }}
  strategy:
    fail-fast: false
    matrix:
      variant: ${{ fromJSON(needs.setup.outputs.windows_variants) }}
  uses: ./.github/workflows/multi_arch_ci_windows.yml
  secrets: inherit
  with:
    matrix_per_family_json: ${{ matrix.variant.matrix_per_family_json }}
    dist_amdgpu_families: ${{ matrix.variant.dist_amdgpu_families }}
    artifact_group: ${{ matrix.variant.artifact_group }}
    build_variant_label: ${{ matrix.variant.build_variant_label }}
    build_variant_suffix: ${{ matrix.variant.build_variant_suffix }}
    build_variant_cmake_preset: ${{ matrix.variant.build_variant_cmake_preset }}
    test_labels: ${{ needs.setup.outputs.windows_test_labels }}
    artifact_run_id: ${{ inputs.artifact_run_id }}
    expect_failure: ${{ matrix.variant.expect_failure == true }}
    use_prebuilt_artifacts: ${{ inputs.windows_use_prebuilt_artifacts == true && 'true' || 'false' }}
    rocm_package_version: ${{ needs.setup.outputs.rocm_package_version }}
    test_type: ${{ needs.setup.outputs.test_type }}
  permissions:
    contents: read
    id-token: write
```

Also update `ci_summary` to include `windows_build_and_test` in its `needs`.

### `configure_ci.py` — Verify Multi-Arch Windows Output

`configure_ci.py` already handles Windows in `generate_multi_arch_matrix()` —
same code path as Linux, filtered by platform. The output `windows_variants`
will contain `matrix_per_family_json` and `dist_amdgpu_families` fields when
`multi_arch=true`.

**Verify:**
- Run `configure_ci.py` with `multi_arch=true` and Windows families
- Confirm `windows_variants` output has correct structure
- Confirm `matrix_per_family_json` has correct Windows test runner labels

### Workflow Cleanup Opportunities

The multi-arch pipeline is a good opportunity to trim setup steps and align
with the style guides, for both Windows and Linux. Since each stage repeats
the setup boilerplate, getting it right once matters more.

**Redundant steps in `build_windows_artifacts.yml`:**

The base Windows runner image ([nod-ai/GitHub-ARC-Setup Dockerfile](https://github.com/nod-ai/GitHub-ARC-Setup/blob/main/windows-arc-runner/Dockerfile))
already includes Python 3.13, DVC 3.62.0, Git, CMake 3.31.0, and VS Build
Tools 2022 with C++ native desktop workloads. Yet the workflow redundantly:

| Workflow step | Base image | Action needed |
|--------------|------------|---------------|
| `actions/setup-python@v6` (3.12) | Python 3.13.7 installed | Remove if 3.13 is acceptable, or keep if 3.12 is specifically needed |
| `iterative/setup-dvc@v2.0.0` (3.62.0) | DVC 3.62.0 installed | Remove — already in image |
| `choco install awscli` | — | Remove — replacing awscli usage with boto3 |

**Package manager:** Switch from chocolatey to winget, consistent with what
we recommend to users in `README.md` and `windows_support.md`. The internal
choco proxy feed (`http://10.0.167.96:8081/...`) is another thing to eliminate.

**Packages not in base image (candidates for baking in):**
- `ccache` — used by every build, should be in base image
- `ninja` (pinned 1.12.1) — used by every build, should be in base image
- `strawberryperl` — needed for some builds (OpenSSL?)
- `pkgconfiglite` — needed for pkg-config on Windows
- ~~`awscli`~~ — replacing with boto3 (Python, already available)

Baking these into the base image would save ~1-2 min of chocolatey install
time per job, which compounds across multi-arch stages (3 stages x N families).

**Alignment opportunities across both platforms:**
- Move repeated environment setup into scripts (not composite actions yet —
  Linux doesn't use them either, do both together or neither)
- Ensure `setup_ccache.py` is called consistently on both platforms
- Standardize git config steps (Linux only does `safe.directory` + `fetch.parallel`;
  Windows adds `core.symlinks` + `core.longpaths`)
- The `ccache --zero-stats` in health status could be handled by `setup_ccache.py`
  (it already has `--reset-stats` flag, default true)

## Open Questions

1. **S3 path disambiguation:** `artifact_manager.py` uses `platform.system().lower()`
   for S3 paths, so Linux and Windows artifacts are already in separate S3
   prefixes. Is this sufficient, or do we need explicit `platform` in artifact
   group names?

2. **CCache approach for Windows:** The existing single-arch Windows workflow
   uses GitHub Actions cache (`actions/cache/restore` + `actions/cache/save`)
   with `CCACHE_DIR` env var and `CCACHE_MAXSIZE=4000M`. This is insufficient
   for these builds — limited cache size, low hit rates, and upload/download
   overhead on every run. The Linux multi-arch pipeline uses `setup_ccache.py`
   with `github-oss-presubmit` preset, which configures ccache's
   `secondary_storage` to hit a bazel-remote cache server
   (`bazelremote-svc.bazelremote-ns.svc.cluster.local:8080`).

   **Decision:** Use `setup_ccache.py` with `github-oss-presubmit` for the
   new Windows multi-arch pipeline. Don't perpetuate the GitHub Actions cache
   approach.

   **Network is confirmed reachable.** PR #2415 verified that Windows runners
   can reach the bazel-remote server (`curl` returns a valid error response,
   not a connection failure). However, PR #2415 stalled because the remote
   cache showed 0% hit rate — `setup_ccache.py` config wasn't being applied
   correctly on Windows, and the `B:\` build path caused ccache log upload
   issues. That PR is still an open draft.

   For our multi-arch pipeline, we should use `setup_ccache.py` and may need
   to fix the config/path issues that PR #2415 hit. See #902 and #2415 for
   full context on the compiler check cache and hit rate investigation.

3. **Build directory:** Use `B:\build` for all stages, same as the existing
   Windows workflow. Shorter paths are needed to stay under Windows MAX_PATH
   limits. Each stage is a separate job on a fresh runner, so there's no
   conflict between stages.

4. **KPack:** Not a prerequisite. Multi-stage builds without kpack are still
   useful (same as Linux). Getting CI in place now means build/test coverage
   is already there when we eventually flip the kpack flag on Windows.

5. **Timeouts:** Use same values as Linux for consistency. Tune later based
   on actual Windows run times.

## Alternatives Considered

### Extend `multi_arch_build_portable_linux.yml` to handle both platforms

**Idea:** Add platform conditionals to the Linux workflow so it handles both
Linux and Windows in the same file.

**Why rejected:** The per-job environment setup is fundamentally different
(container vs native, chocolatey vs pre-installed, MSVC vs gcc). Conditionals
in every step would make the workflow unreadable and fragile. Each stage would
need `if: platform == 'linux'` / `if: platform == 'windows'` on most steps.
The Linux workflow already has 789 lines for 7 stages — adding Windows
conditionals throughout would double the complexity.

**Better approach:** Separate workflow files, same supporting scripts. The
scripts (`configure_stage.py`, `artifact_manager.py`, `fetch_sources.py`) are
already cross-platform. Only the YAML plumbing (env setup, runner selection)
differs.

### Use a composite action for per-stage environment setup

**Idea:** Create a composite action that encapsulates the ~10 setup steps
(checkout, Python, chocolatey, MSVC, git config, ccache, health check, DVC)
so each stage job just calls the action.

**Why deferred (not rejected):** This is a good idea but adds a separate
concern. The immediate goal is getting the Windows pipeline working. Once it
works, DRYing up the repeated setup steps into a composite action is a natural
follow-up. The Linux pipeline also has repeated setup steps and doesn't use
composite actions yet — doing it for Windows first would create an asymmetry.
Better to do it for both platforms together.

## Workstreams

Three workstreams, intentionally sequenced:

### Workstream 1: Stand up the pipeline (do first)

Get multi-arch Windows CI running end-to-end. Copy existing patterns from
`build_windows_artifacts.yml` and `multi_arch_build_portable_linux.yml` — take
shortcuts, don't try to clean up at this stage. The goal is a working pipeline
that can be iterated on.

**PR 1: `multi_arch_build_portable_windows.yml` + `multi_arch_ci_windows.yml`**

New files:
- `.github/workflows/multi_arch_build_portable_windows.yml` — 3-stage build
- `.github/workflows/multi_arch_ci_windows.yml` — orchestration (build + test)

Modified files:
- `.github/workflows/multi_arch_ci.yml` — uncomment Windows section, update
  to call `multi_arch_ci_windows.yml`, add to `ci_summary` needs

Approach:
- Port the Linux pipeline structure to Windows
- Copy environment setup from `build_windows_artifacts.yml` as-is (including
  chocolatey, GitHub Actions cache, etc. — clean up in workstream 2)
- Use `configure_stage.py` for stage cmake args (same as Linux)
- Use `artifact_manager.py` for inter-stage artifacts (same as Linux)
- Stages disabled on Windows are handled automatically by `configure_stage.py`
  reading `BUILD_TOPOLOGY.toml`

Testing:
- `workflow_dispatch` of `multi_arch_ci.yml` on the branch with
  `linux_amdgpu_families: ""` (empty) and `windows_amdgpu_families: gfx110X`
  — this runs only Windows, skipping Linux
- Verify each stage completes and artifacts flow between stages
- Verify test job can fetch final artifacts and run

### Follow-up: Evaluate cmake preset vs `_get_windows_platform_cmake_args`

The `windows-release` cmake preset (inheriting `windows-base`) already sets
`CMAKE_C_COMPILER` to `cl.exe`. It may be possible to add `CMAKE_LINKER` to
the preset as well, which would make `_get_windows_platform_cmake_args()` in
`configure_stage.py` redundant. The preset approach is arguably cleaner since
it keeps compiler config in CMake-land rather than Python-land.

**To investigate:**
- Does `windows-release` preset set `CMAKE_LINKER`? If not, can we add it?
- Does preset `cl.exe` (bare name, relies on PATH) work as reliably as the
  full `VCToolsInstallDir` path that `_get_windows_platform_cmake_args` emits?
- If we re-add preset support to the multi-arch workflow, does it fully
  replace the Python-side platform args?

### Workstream 2: Refactor and clean up (interleave with CI wait times)

While waiting on multi-hour CI builds from workstream 1, chip away at
cleanup items. Each can be a separate PR. Applies to both Linux and Windows
workflows — don't create asymmetry by cleaning up only one platform.

**Candidates (roughly priority order):**

1. **Switch Windows ccache to `setup_ccache.py` + bazel-remote** — biggest
   impact on build times. Build on PR #2415's findings. Fix config/path
   issues for `B:\build`.

2. **Replace awscli with boto3** — eliminates a chocolatey dependency and
   aligns with Python-first tooling.

3. **Switch chocolatey to winget** — consistent with `README.md` and
   `windows_support.md` recommendations. Eliminates internal choco proxy
   feed dependency.

4. **Remove redundant setup steps** — DVC already in base image, Python
   version may not need `actions/setup-python`, etc.

5. **Bake ccache + ninja into base VM image** — saves ~1-2 min per job,
   compounded across stages. PR to `nod-ai/GitHub-ARC-Setup`.

6. **Move repeated env setup into scripts** — reduce YAML boilerplate.
   Do for both platforms together. (Composite actions are an option but
   Linux doesn't use them either — keep parity.)

7. **Standardize git config, ccache stats reset, health checks** — small
   alignment items across platforms.

### Workstream 3: Broader multi-arch feature work (separate tasks)

Not part of this task, but listed for context on what comes next:
- KPack integration on Windows
- Running tests on multi-arch CI
- Building multi-arch Python packages
- PyTorch CI on Windows (pytorch-ci Phase 3)

## Local Stage Builds (for debugging CI failures)

Build each stage locally to validate before pushing to CI. Uses
`configure_stage.py` for cmake args and `artifact_manager.py` with
`--local-staging-dir` to pass artifacts between stages instead of S3.

```bash
# Setup
THEROCK=D:/projects/TheRock
BUILD=B:/build          # or wherever you want the build dir
STAGING=B:/staging      # local artifact interchange directory
FAMILY=gfx1201          # or whichever family you're testing

cd $THEROCK

# List available stages
python build_tools/configure_stage.py --list-stages

# ── Stage 1: foundation (generic) ──
python build_tools/fetch_sources.py --stage foundation --jobs 12 --depth 1
cmake -B $BUILD -S . -GNinja \
  -DTHEROCK_PACKAGE_VERSION=ADHOCBUILD \
  -DCMAKE_C_COMPILER_LAUNCHER=ccache \
  -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
  $(python build_tools/configure_stage.py --stage foundation \
      --dist-amdgpu-families "$FAMILY" --print --oneline)
cmake --build $BUILD --target stage-foundation therock-artifacts -- -k 0
python build_tools/artifact_manager.py push \
  --stage foundation --build-dir $BUILD \
  --local-staging-dir $STAGING

# ── Stage 2: compiler-runtime (generic) ──
python build_tools/artifact_manager.py fetch \
  --stage compiler-runtime --output-dir $BUILD --bootstrap \
  --local-staging-dir $STAGING
python build_tools/fetch_sources.py --stage compiler-runtime --jobs 12 --depth 1
cmake -B $BUILD -S . -GNinja \
  -DTHEROCK_PACKAGE_VERSION=ADHOCBUILD \
  -DCMAKE_C_COMPILER_LAUNCHER=ccache \
  -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
  $(python build_tools/configure_stage.py --stage compiler-runtime \
      --dist-amdgpu-families "$FAMILY" --print --oneline)
cmake --build $BUILD --target stage-compiler-runtime therock-artifacts -- -k 0
python build_tools/artifact_manager.py push \
  --stage compiler-runtime --build-dir $BUILD \
  --local-staging-dir $STAGING

# ── Stage 3: math-libs (per-arch) ──
python build_tools/artifact_manager.py fetch \
  --stage math-libs --amdgpu-families $FAMILY --output-dir $BUILD --bootstrap \
  --local-staging-dir $STAGING
python build_tools/fetch_sources.py --stage math-libs --jobs 12 --depth 1
cmake -B $BUILD -S . -GNinja \
  -DTHEROCK_PACKAGE_VERSION=ADHOCBUILD \
  -DTHEROCK_AMDGPU_FAMILIES=$FAMILY \
  -DCMAKE_C_COMPILER_LAUNCHER=ccache \
  -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
  $(python build_tools/configure_stage.py --stage math-libs \
      --amdgpu-families $FAMILY --dist-amdgpu-families "$FAMILY" \
      --print --oneline)
cmake --build $BUILD --target stage-math-libs therock-artifacts -- -k 0
python build_tools/artifact_manager.py push \
  --stage math-libs --build-dir $BUILD \
  --local-staging-dir $STAGING
```

**Notes:**
- `--bootstrap` on fetch extracts artifacts into build dir so cmake finds them
- `--local-staging-dir` uses local filesystem instead of S3
- Each stage reconfigures cmake (different `THEROCK_ENABLE_*` flags per stage)
- On Windows, run from a VS Developer Command Prompt (or after `msvc-dev-cmd`)
- Inspect what a stage needs/produces: `python build_tools/artifact_manager.py info --stage math-libs --amdgpu-families $FAMILY`
- Inspect cmake args before running: `python build_tools/configure_stage.py --stage math-libs --amdgpu-families $FAMILY --dist-amdgpu-families "$FAMILY" --print --comments`

## Investigation Notes

### 2026-02-11 - Initial Analysis

**Windows stages from BUILD_TOPOLOGY.toml:**

Disabled on Windows: media (source set), comm-libs/RCCL, dctools-core/RDC,
profiler-apps/rocprofiler-systems, debug-tools, and several sysdeps
(expat, gmp, mpfr, ncurses, libpciaccess, hwloc). Also disabled:
core-rocr (runtime), core-amdsmi, core-runtime-tests.

This means the Windows pipeline has only 3 stages (foundation,
compiler-runtime, math-libs) vs Linux's 7. The linear dependency chain
(no parallel stages until math-libs fans out) keeps the pipeline simple.

**`configure_ci.py` multi-arch Windows support:**

`generate_multi_arch_matrix()` is platform-agnostic — it filters families by
platform via `lookup_matrix.get(target_name)` and only includes families that
have a platform entry. Windows variants already get `matrix_per_family_json`
and `dist_amdgpu_families` fields. The `build_pytorch` flag is computed but
not yet consumed by any Windows multi-arch workflow (separate task: pytorch-ci
Phase 3).

**Windows ccache / bazel-remote status (from #902, #2415):**

- bazel-remote server is accessible from Windows runners (confirmed via `curl`)
- PR #2415 attempted to call `setup_ccache.py` from the Windows workflow but
  the remote cache got 0% hit rate — config wasn't being applied correctly
- The `B:\build` path caused issues with ccache log file paths
- Compiler check cache has known cross-run invalidation issues on Linux too
  (bootstrapped clang shared libs change hashes between runs)
- The bazel-remote server already has Prometheus metrics enabled
  (`--enable_endpoint_metrics`)

**`artifact_manager.py` S3 path structure:**

Uses `{bucket}/{run_id}-{platform}/stages/{stage_name}/...` — platform is
already in the path, so Linux and Windows artifacts are naturally separated.
No additional disambiguation needed.

## Progress

### 2026-02-12 — Workstream 1 largely complete

**Branches:**
- `multi-arch-windows-ci-1` — main branch with all pipeline work
- `users/scotttodd/multi-arch-windows-ci-2` — experimental: cmake preset for
  compiler selection instead of Python-side VCToolsInstallDir logic

**Commits on `-1` branch (8 total):**
1. `8e127558` Add multi-arch staged build workflow for Windows
2. `b1007021` Add unit tests for configure_stage platform cmake args
3. `defec7fe` Remove configure_stage platform tests for now
4. `77731eec` Add Windows platform cmake args to configure_stage.py
5. `bbda81d0` Remove ccache and actions/cache from multi-arch Windows workflow
6. `511ba742` Remove unused build_variant_cmake_preset input
7. `eedaadbf` Add multi-arch Windows orchestration workflow
8. `84b512e6` Filter disabled-platform artifacts in configure_stage.py

**Commit on `-2` branch (on top of `-1`):**
- `f280da29` Use CMake preset for Windows compiler/linker selection

**Key fixes found during CI testing:**
- Compiler paths with spaces need quoting in `--oneline`/`--gha-output` mode
  (paths like `C:/Program Files/...` get word-split by bash)
- `get_stage_features()` wasn't filtering by platform — Linux-only artifacts
  like `sysdeps-expat` leaked into Windows builds. Fixed by checking
  `artifact.disable_platforms`.
- `GITHUB_PATH` appends were malformed (separate PR #3400, merged)

**CI test runs in flight (end of day 2026-02-12):**
- Run 21968103351 (`-1` branch) — platform filtering fix, no preset
- Run 21968150605 (`-2` branch) — same + cmake preset for compiler selection
- Both need to pass Foundation → Compiler Runtime → Math Libs to validate

**Open question:** Does the cmake preset (`windows-release` inheriting
`windows-base`) fully replace `_get_windows_platform_cmake_args()`? The `-2`
branch tests this. If it works, we can drop the VCToolsInstallDir Python code
entirely and just keep `THEROCK_BACKGROUND_BUILD_JOBS=4`.

**Related PR:** #3402 — adds `CMAKE_LINKER` to the `windows-base` preset and
drops explicit compiler options from `build_configure.py`, testing the preset
approach on the existing single-arch Windows workflows too.

## Next Steps

**Workstream 1 (stand up pipeline):**
1. [x] Draft `multi_arch_build_portable_windows.yml` (3 stages)
2. [x] Draft `multi_arch_ci_windows.yml` (build + test orchestration)
3. [x] Update `multi_arch_ci.yml` (wire up Windows, add to ci_summary)
4. [~] Test via `workflow_dispatch` on branch — **in progress, 2 runs queued**
5. [ ] Iterate on CI failures (check runs after weekend)
6. [ ] Decide preset vs Python compiler selection based on CI results
7. [ ] Squash/clean up commits for PR

## Job Timing Metrics

Tracking setup overhead vs build time per stage across test runs.
These metrics will support the eventual PR and workstream 2 optimization work.

### How to collect

From the GitHub Actions UI or `gh run view`, note the duration of key steps:
- **setup-python**: `actions/setup-python`
- **pip install**: `Install python deps`
- **choco installs**: `Install requirements`
- **setup-dvc**: `iterative/setup-dvc`
- **msvc**: `Configure MSVC`
- **git config**: `Adjust git config`
- **health status**: `Runner health status`
- **fetch sources**: `Fetch sources`
- **AWS creds + fetch artifacts**: (stages 2-3 only)
- **stage config**: `Get stage configuration`
- **configure**: `Configure` (cmake)
- **build**: `Build stage`
- **push artifacts**: `Push stage artifacts`

**Setup overhead** = total - build - configure - push artifacts
**Build time** = build step only

### Runs

#### Run 21968103351 (`-1` branch, no preset, gfx1151)

| Stage | Total | Build | Configure | Setup Overhead | Overhead % |
|-------|-------|-------|-----------|----------------|------------|
| foundation | 6m40s | 50s | | | ~85% |
| compiler-runtime | 20m | 11m47s | | | ~40% |
| math-libs (gfx1151) | | | | | |

#### Run 21968150605 (`-2` branch, with preset, gfx1151)

| Stage | Total | Build | Configure | Setup Overhead | Overhead % |
|-------|-------|-------|-----------|----------------|------------|
| foundation | | | | | |
| compiler-runtime | | | | | |
| math-libs (gfx1151) | | | | | |

### Averages

(Fill in once we have multiple runs)

| Stage | Avg Total | Avg Build | Avg Overhead | Avg Overhead % |
|-------|-----------|-----------|--------------|----------------|
| foundation | | | | |
| compiler-runtime | | | | |
| math-libs | | | | |

### Optimization targets

Per-job overhead breakdown (approximate, from run 21968103351 foundation):
- setup-python: ~1min
- pip install requirements.txt: ~1min
- choco installs (ninja, perl, awscli, pkgconfiglite): ~2min
- setup-dvc: ~20s
- MSVC + git config + health: ~30s
- fetch sources: ~40s

Biggest wins:
1. Bake ninja, perl, pkgconfiglite into base VM image (~2min saved)
2. Drop setup-dvc (already in base image) (~20s saved)
3. Drop setup-python if 3.13 is acceptable (~1min saved)
4. Cache or bake pip dependencies (~1min saved)

## S3 Artifacts and Index Pages

The multi-arch jobs upload stage artifacts to S3 but do **not** generate index
pages yet. For local testing of uploaded artifacts, we'll need to infer S3
paths from logs or `artifact_manager.py` conventions.

**Index page generation:** Currently each job generates its own index page
before upload. This is fragile for multi-arch CI where multiple stages and
architecture shards upload artifacts concurrently — the index page would need
continuous updating as artifacts arrive, with potential race conditions between
overlapping jobs.

**Server-side index generation** (#3331) would fix this: instead of each job
rebuilding the index, the server regenerates it as artifacts land. This is
especially important for multi-arch CI where the upload pattern is:
- foundation uploads (generic)
- compiler-runtime uploads (generic)
- math-libs uploads (per-arch, potentially concurrent for multiple families)

Until #3331 lands, we can test locally by fetching artifacts directly from S3
without relying on index pages.

**Workstream 2 (refactor, interleave with CI waits):**
8. [ ] Fix `setup_ccache.py` for Windows / `B:\build` paths
9. [ ] Replace awscli usage with boto3
10. [ ] Switch chocolatey to winget
11. [ ] Remove redundant setup steps (DVC, Python, etc.)
12. [ ] PR to bake ccache + ninja into base VM image
13. [ ] Move repeated env setup into scripts (both platforms)
