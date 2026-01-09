---
repositories:
  - therock
---

# Submodule Bisect Tooling

**Status:** In progress
**Priority:** P1 (High)
**Started:** 2026-01-09
**Target:** TBD

## Overview

Build tooling to bisect regressions in ROCm super-repos (rocm-libraries/rocm-systems) using pre-built CI artifacts instead of rebuilding TheRock at each commit. This will reduce bisection time from hours/days to minutes.

**Current Phase:** Prototype & Validation (Phase 1)

## Goals

- [ ] Complete RFC design refinement
- [ ] Implement Phase 1: Working prototype
  - [ ] `workflow_mapper.py` - GitHub API integration with `InMemoryRunStore`
  - [ ] `artifact_manager.py` - Basic artifact download and caching
  - [ ] `setup_test_env.py` - Environment setup
  - [ ] `bisect_submodule.py` - Basic orchestrator (manual mode)
  - [ ] Cache directory structure
  - [ ] Manual end-to-end test with a known regression
- [ ] Validate design with real-world usage
- [ ] Plan Phase 2: Git Bisect Integration

## Context

### Background

When test regressions occur in ROCm super-repos, developers need to identify which commit introduced the failure. Traditional `git bisect` requires rebuilding TheRock at each commit (hours per commit), making it prohibitively expensive.

The super-repos already run TheRock CI workflows that:
- Build TheRock for every commit on develop branch
- Upload artifacts to S3 buckets
- Run component tests

These artifacts can be leveraged for fast bisection without rebuilds.

### Related Work

- RFC: `../TheRock/docs/rfcs/RFC0009-Submodule-Bisect-Tooling.md`
- Discussion: https://github.com/ROCm/TheRock/issues/2608
- Inspiration: IREE bisect tools (https://github.com/iree-org/iree/tree/main/build_tools/pkgci/bisect)

### Directories/Files Involved

```
/d/projects/TheRock/build_tools/bisect/           # New directory for bisect tooling
/d/projects/TheRock/build_tools/fetch_artifacts.py  # Existing artifact fetcher (reuse)
/d/projects/TheRock/docs/rfcs/RFC0009-Submodule-Bisect-Tooling.md  # Design doc
```

## Investigation Notes

### 2026-01-09 - Design Refinement

**Changes to RFC:**
- Restructured "Detailed Design" to focus on high-level components first, then implementation details
- Introduced pluggable `RunMappingStore` protocol for commit→run_id mappings
- Specified `InMemoryRunStore` as initial implementation (no SQLite dependency)
- Moved persistent storage (SQLite/remote DB) to Phase 4 enhancements
- Updated implementation plan to focus on phases rather than fixed timelines

**Key Design Decisions:**
- Start simple with in-memory storage to validate the approach
- Build abstraction layer early to enable future storage backends
- Keep `<commit_sha>` in cache directory structure for clarity
- Phase 1 focuses on manual mode; Phase 2 adds `git bisect run` integration

### 2026-01-09 - Prototype Work Log: Real-World Test Case

**Test Scenario:**
- TheRock PR: https://github.com/ROCm/TheRock/pull/2812
- Bumps rocm-systems submodule from `2789ea4` → `050e88e`
- Test failures in TheRock CI: https://github.com/ROCm/TheRock/actions/runs/20792676051/job/59834206182?pr=2812
- Goal: Bisect through rocm-systems commits to find which one caused the failure

**rocm-systems Commit Range (19 commits):**

Repository: `ROCm/rocm-systems`
Base: `2789ea429a8f0f32ff68e21858a21f4b04be9e82`
Head: `050e88ee710f0d8580e2df31425c9fd03e8f1a77`

Commits (oldest to newest):

1. `3568e0df02c7f8d203de29b9e175ac87f7da337f` - "SWDEV-563487 - Fix catch tests failures on Windows (#2097)"
2. `0f0504d79dae96269631a21af3636bfe00044894` - "SWDEV-564412-Fix soft hang in HIP sub-test hipMemVmm_Uncached (#2223)"
3. `88f4bb19883f04524c32564792bb411a7050b440` - "SWDEV-564412 - fix test failure on hipSetValidDevices_with_hipMemcpyPeer (#2150)"
4. `7871f53563e7747daaca113d3d2a08b3fcaaf087` - "Add gfx950 support to ValuPipeIssueUtil counter (#2396)"
5. `11d9472e5fae5b5efc3703eca4a4db3b4a75d6dd` - "Bump TheRock SHA for CI 20251230 (#2466)"
6. `39d84328932de5b9fbc26f958c0467d479072831` - "SWDEV-566854 - Improve memory object handling (#1939)"
7. `1d5a6e9bfefb937ae9cfc15bcae9cc8786b691d5` - "Update rocprofiler workflows to use new mi325 runner names (#2467)"
8. `9e4d1c31c7da2c7cd56651b4bb46b842e64e8e9f` - "fix: prevent static initialization deadlock in thread_data (#2474)"
9. `7fcea905f34a5c74be45a6b88c96eda59437cee6` - "[rocprofiler-sdk] Fix double-buffering emplace and flush synchronization (#2334)"
10. `e005f8487b84fe1aba4ee91acd4e126028c72892` - "[rocprofiler-compute] Add gfx arch. based pre-processor guards and runtime checks in rocflop.cpp (#2487)"
11. `637b0d71f0ea7da409d7126b5828cc1982f02d92` - "SWDEV-569319 Replace ScopedAcquire with stdcpp wrappers (#2146)"
12. `6c98c49362f3dbb76a6f8814c7dc90a889d14175` - "[SWDEV-568731] Updated example code in amdsmi-py-api.md file (#2311)"
13. `c6b7448227aee6ca449241f1b8bde6a9d02b3d2f` - "Add support for get and set APIs for CPUISOFreqPolicy and DFCState Control (#1901)"
14. `32fde0f73d79d699c2b9de1573652cca40898af6` - "[SWDEV-568613] Add gpu_metrics 1.0 support for older GPUs (#2444)"
15. `50644f5aef0358eb2808483159d754c2f0b18611` - "SWDEV-508225 remove assertions when loading fat binary (#2013)"
16. `cb372748f8112ca5951e18e8f43a231d640053c8` - "[ROCM-SMI] [SWDEV-569731] rsmi tests failing on Frequency/Power/GpuMetrics ReadOnly Fix (#2303)"
17. `81eed26ec6fcbb0ed41865c168c471d6042f1749` - "[amdsmi] Add include dirs for libdrm. (#2504)"
18. `1ef6a86ee3ad85b97070c27b631ed0aceec31611` - "SWDEV-549711 - Improve graph DEBUG dot print for segments (#2205)"
19. `050e88ee710f0d8580e2df31425c9fd03e8f1a77` - "Remove unused python packages (#2437)"

**Workflows to Check:**
- `.github/workflows/therock-ci.yml`
- `.github/workflows/therock-ci-linux.yml`
- `.github/workflows/therock-ci-windows.yml`

**Prototype Results** (2026-01-09):

Created `prototypes/query_workflow_runs.py` to query GitHub API for workflow runs.

Key findings:
- ✓ **All 19 commits have therock-ci.yml workflow runs!**
- ✓ All runs completed successfully (status: completed, conclusion: success)
- ✓ Successfully mapped each commit to its run_id
- ✓ GitHub API `head_sha` parameter works perfectly for filtering runs by commit
- ✓ Used `gh` CLI for authenticated access (no token management needed)

Example mapping:
- Commit `3568e0df` → Run ID `20723767265`
- Commit `050e88ee` → Run ID `20784068010`

**Design Validation:**
- The RFC's approach of querying workflow runs by commit SHA is validated
- The `head_sha` filter makes queries efficient (no need to paginate through all runs)
- 100% coverage: Every commit in our test range has artifacts available for bisection

**S3 Artifact Structure:**

Artifacts are uploaded to S3, not GitHub artifacts:
- Bucket: `therock-ci-artifacts-external` (for external repos like rocm-systems)
- Path structure: `ROCm-rocm-systems/{run_id}-{platform}/`
- Artifact index: `index-{artifact_group}.html` (e.g., `index-gfx94X-dcgpu.html`)

Example URL:
```
https://therock-ci-artifacts-external.s3.amazonaws.com/ROCm-rocm-systems/20723786674-linux/index-gfx94X-dcgpu.html
```

**Components Built (rocm-systems therock-ci.yml):**

From run 20723786674, artifact group `gfx94X-dcgpu`:
- AMD LLVM (compiler toolchain)
- Base (core system libraries)
- Core-HIP, Core-OCL, Core-Runtime
- Core-HIPTests (GPU-specific tests for gfx94X)
- ROCProfiler (compute, SDK, systems variants)
- Third-party deps (FFTW3, Flatbuffers, Fmt, Nlohmann-JSON, Spdlog)

**CRITICAL GAP IDENTIFIED:**

rocm-systems CI builds only a **subset** of ROCm components. The failing tests mentioned in PR #2812 are for rocprim, which is **not** included in rocm-systems artifacts.

This means:
- We can bisect rocm-systems commits that affect the components actually built (HIP, runtime, profiler, etc.)
- We **cannot** bisect regressions in downstream components like rocprim using only rocm-systems artifacts
- Need to determine if TheRock's CI builds the full stack including rocprim

**Next Steps:**
- [x] Query GitHub API for workflow runs for each commit
- [x] Build commit→run_id mapping
- [x] Check if all 19 commits have workflow runs
- [x] Explore S3 artifact structure and what's built
- [ ] Determine how to get full-stack artifacts that include failing components
- [ ] Check if TheRock CI runs build rocprim
- [ ] Design solution for partial vs. full artifact coverage

### Next Investigation Areas

- [ ] Study existing `fetch_artifacts.py` to understand artifact download patterns
- [ ] Explore GitHub Actions API for workflow run queries
- [x] Identify a real regression in rocm-libraries or rocm-systems for testing
- [ ] Prototype workflow mapper with real API calls

## Decisions & Trade-offs

### In-Memory vs Persistent Storage (Phase 1)

**Decision:** Use in-memory `InMemoryRunStore` for initial implementation

**Rationale:**
- Simplifies initial development (no SQLite dependency)
- Faster iteration during prototyping
- Still provides abstraction for future migration
- Single bisect session can query GitHub API once and cache in memory

**Alternatives considered:**
- SQLite from the start: More complexity, harder to test, overkill for prototype
- No abstraction: Would make future migration harder

### Cache Directory Structure

**Decision:** Use `~/.therock/bisect/<repo>/<commit_sha>/` structure

**Rationale:**
- Commit SHA is more intuitive for debugging
- Easier to manually inspect cached artifacts
- Aligns with git workflow (users think in commits, not run IDs)

**Alternatives considered:**
- Using `run_<run_id>`: Less intuitive, harder to correlate with git history

## Code Changes

### Files to Create (Phase 1)

- `build_tools/bisect/workflow_mapper.py` - Commit→run_id mapping
- `build_tools/bisect/artifact_manager.py` - Artifact download and caching
- `build_tools/bisect/setup_test_env.py` - Test environment setup
- `build_tools/bisect/bisect_submodule.py` - Main orchestrator
- `build_tools/bisect/__init__.py` - Package initialization

### Files to Modify

- None yet (Phase 1 is net-new code)

### Testing Strategy

Phase 1:
1. Unit tests for each component
2. Manual end-to-end test with a known regression

Phase 2+:
3. Automated end-to-end tests with CI artifacts
4. Integration tests with `git bisect run`

## Blockers & Issues

### Active Blockers

None currently

### Questions to Resolve

- [ ] Which super-repo should we use for initial testing?
- [ ] Do we need a test ROCm environment with actual GPUs for validation?
- [ ] Should Phase 1 include basic logging/debugging output?

## Resources & References

- [RFC0009](../TheRock/docs/rfcs/RFC0009-Submodule-Bisect-Tooling.md)
- [IREE bisect tools](https://github.com/iree-org/iree/tree/main/build_tools/pkgci/bisect)
- [GitHub Actions Workflow Runs API](https://docs.github.com/en/rest/actions/workflow-runs)
- [fetch_artifacts.py](../TheRock/build_tools/fetch_artifacts.py)
- [BUILD_TOPOLOGY.toml](../TheRock/BUILD_TOPOLOGY.toml)

## Next Steps

1. [ ] Review updated RFC with user
2. [ ] Study `fetch_artifacts.py` implementation
3. [ ] Prototype `InMemoryRunStore` class
4. [ ] Prototype GitHub API integration for workflow queries
5. [ ] Create basic `workflow_mapper.py` with unit tests

## Completion Notes

<!-- Fill this in when task is done -->
