---
repositories:
  - therock
---

# Multi-Arch Migration

- **Status:** In progress
- **Priority:** P1 (High)
- **Started:** 2026-03-25
- **Tracking:** #3337 (pre-submit enablement), parent #3336 (extend multi-arch CI)

## Overview

Close the remaining feature gaps between single-stage CI and multi-arch CI so that
multi-arch CI can replace the former. Two main gaps:

1. **Windows compiler cache** — multi-arch Windows builds have no ccache, leading to
   long builds and runner communication losses (#3622). Regular Windows CI uses
   `actions/cache` for ccache but hits the 10GB repo cache limit frequently. A remote
   cache server is being developed by other team members but isn't ready yet.

2. **Post-build uploads (logs, index pages)** — single-stage CI runs
   `post_build_upload.py` which uploads logs, artifacts, ninja log archives, and
   generates index.html pages. Multi-arch CI only runs `artifact_manager.py push`
   for per-stage artifact subsets, missing logs and index pages. #3331 tracks
   server-side index generation; until then, client-side workarounds are needed.

## Goals

- [ ] Add ccache to multi-arch Windows CI (local cache, enough to stabilize builds)
- [ ] Add log/file uploads to multi-arch CI stages
- [ ] Add index page generation (client-side workaround until #3331 lands)
- [ ] Get multi-arch CI stable enough for pre-submit default (#3337 checklist)

## Context

### Issue Checklist from #3337
- [x] Allow running multi-arch CI manually via `workflow_dispatch`
- [x] Run multi-arch CI on `push`
- [x] Allow explicit opt-in to running multi-arch CI on `pull_request`
- [ ] Add implicit opt-in based on files modified
- [ ] Run multi-arch CI by default for most changes
- [ ] #3340 (final step)

### Key Files
```
.github/workflows/multi_arch_ci.yml                          # orchestrator
.github/workflows/multi_arch_ci_linux.yml                     # Linux CI
.github/workflows/multi_arch_ci_windows.yml                   # Windows CI
.github/workflows/multi_arch_build_windows.yml                # Windows multi-stage builder
.github/workflows/multi_arch_build_windows_artifacts.yml      # Windows per-stage build job
.github/workflows/multi_arch_build_portable_linux.yml         # Linux multi-stage builder
.github/workflows/multi_arch_build_portable_linux_artifacts.yml # Linux per-stage build job
.github/workflows/build_windows_artifacts.yml                 # Regular Windows CI (has ccache)
build_tools/github_actions/post_build_upload.py               # Single-stage upload script
build_tools/artifact_manager.py                               # Multi-arch artifact push
```

### Related Issues/PRs
- #3336 — parent: extend and improve multi-arch CI
- #3337 — enable multi-arch CI on pre-submit
- #3331 — refactor post_build_upload.py (server-side index generation)
- #3622 — Windows runner communication losses (no ccache)
- #902 — ccache/sccache tracking

### Current State of Windows ccache (regular CI)
- `build_windows_artifacts.yml` installs ccache via choco, sets CCACHE_DIR/CCACHE_MAXSIZE
- Uses `actions/cache/restore@v5.0.3` keyed on amdgpu_families + commit SHA
- 10GB repo cache limit means frequent eviction; ~57% hit rate observed
- Even with cache: ~3h45m build times

### Current State of Uploads
- Single-stage CI: `post_build_upload.py` handles logs, artifacts, ninja archives,
  index.html generation, manifests, GHA summary
- Multi-arch CI: only `artifact_manager.py push` for artifact archives
- Missing: ninja log archives, build logs, resource profiling, index pages

## Investigation Notes

### 2026-03-25 - Initial Assessment

**Gap 1: Windows ccache**
- Multi-arch `multi_arch_build_windows_artifacts.yml` installs ninja, strawberryperl,
  pkgconfiglite but NOT ccache
- No CCACHE_DIR/CCACHE_MAXSIZE env vars, no actions/cache usage
- Approach: add local ccache (same pattern as regular CI). Won't solve the 10GB
  eviction problem but should reduce build times enough to prevent runner timeouts.
- Remote cache server work by other team members is the long-term fix.

**Gap 2: Post-build uploads**
- `post_build_upload.py` assumes all artifacts in one build dir — doesn't work for
  multi-arch stages which build subsets in separate jobs
- Per-stage upload of logs/ninja archives is straightforward
- Index page generation is the hard part: each stage only sees its own files
- Workaround idea: each stage uploads its files, then regenerates the index page.
  Race conditions between stages are acceptable if we only write (never delete) and
  regenerate the index enough times. Last writer wins → eventual consistency.

### 2026-03-25 - Build Performance Analysis

#### Linux CI vs Multi-Arch CI (with ccache + remote bazel-remote)

Linux has a **remote ccache backend** (bazel-remote) giving 98% hit rates. Both CI
and multi-arch CI use it via `setup_ccache.py` preset `github-oss-presubmit`.

| Metric | CI (monolithic) | Multi-Arch CI |
|--------|-----------------|---------------|
| gfx1151 build | 83-109 min | Foundation 5m + Compiler 37m + Math Libs 19m ≈ 61m critical path |
| gfx120X-all build | 77-99 min | Foundation 5m + Compiler 37m + Math Libs 36-46m ≈ 78-88m critical path |
| gfx94X-dcgpu build | 105-133 min | Foundation 5m + Compiler 37m + Math Libs 68-89m ≈ 110-131m critical path |
| gfx110X-all build | 77-114 min | Foundation 5m + Compiler 37m + Math Libs 26m ≈ 68m critical path |
| ccache hit rate | 98.3% (remote) | 98.3% (remote, same setup) |
| PyTorch | 21-47 min | 21-47 min (same) |

**Linux takeaway:** Multi-arch is comparable or slightly faster on wall time thanks to
stage parallelism. The remote cache makes builds fast on both pipelines. No action needed.

#### Windows CI vs Multi-Arch CI (no remote cache)

Windows CI uses GitHub Actions cache for ccache (4GB limit, frequently evicted).
Multi-arch Windows CI has **no ccache at all**.

| Metric | CI (with ccache) | Multi-Arch CI (no ccache) |
|--------|-----------------|--------------------------|
| gfx1151 build | 2h25m-3h57m | Foundation 5m + Compiler 42-69m + Math Libs 1h52m-2h23m ≈ 2h39-3h37m |
| gfx110X-all build | 3h04m-3h11m | Foundation 5m + Compiler 42m + Math Libs 2h13m-3h36m ≈ 3h00-4h23m |
| gfx120X-all build | 4h13m-4h20m | Foundation 5m + Compiler 42m + Math Libs 2h48m-4h37m ≈ 3h35-5h24m |
| ccache hit rate | 0-57% (cold=0%, warm=57%) | N/A (no ccache) |
| Cache full? | Yes - 4GB at 99.9%, 200 cleanups | N/A |
| PyTorch | 44m-1h10m | 1h12m-1h45m (slower, no cache) |

**Windows ccache stats (regular CI, warm run gfx1151):**
- 17,635 cacheable / 27,233 total calls (64.8% cacheable)
- 10,085 hits / 17,635 cacheable (57.2% hit rate)
- Cache 4.0/4.0 GB (99.9% full, 200 cleanups)

**Windows ccache stats (regular CI, cold run):** 0.4% hit rate

**Key observation:** The GitHub Actions cache is highly unreliable for Windows —
cold starts are common (0% hits) because the 10GB repo-wide limit evicts entries
constantly across variants. Warm runs get 57% but the cache is perpetually full at 4GB.

#### gfx120X-all is the stability bottleneck

All 3 recent multi-arch main runs failed on gfx120X-all Windows (runner lost
communication — likely OOM/timeout during math-libs). Build times range 2h48m-4h37m
for that stage alone.

### 2026-03-25 - Cache Strategy Analysis

**Cost of switching from CI to multi-arch CI today (Windows):**
- Wall time is roughly comparable when CI has warm cache (rare) and multi-arch has none
- Multi-arch is likely *slower* on average because CI occasionally gets cache hits
  while multi-arch never does
- gfx120X-all is the main failure mode — math-libs stage regularly exceeds runner limits
- PyTorch builds are 30-50% slower in multi-arch (no cache benefit at all)

**Potential incremental mitigations:**

1. **Add ccache with GitHub Actions cache to compiler-runtime stage only**
   - Compiler-runtime is ~42-69min, highly cacheable (LLVM is deterministic)
   - Cache key: `windows-multi-arch-compiler-v1-${{ github.sha }}`
   - LLVM changes infrequently → high reuse across runs even with 10GB eviction pressure
   - Small change, high leverage — compiler stage feeds all downstream stages

2. **Add ccache to all stages with per-stage cache keys**
   - Key pattern: `windows-multi-arch-${{ stage_name }}-${{ amdgpu_family }}-${{ github.sha }}`
   - Risk: many cache entries (stages × families) compete for 10GB repo limit
   - Math-libs caches would evict compiler caches since they're larger and more numerous
   - Could partially mitigate with lower CCACHE_MAXSIZE for math-libs

3. **ccache for compiler-runtime + reduced parallelism for gfx120X-all math-libs**
   - Address the OOM/timeout by limiting ninja parallelism for the problematic stage
   - e.g. `ninja -j <lower>` for gfx120X-all math-libs specifically

4. **Skip gfx120X-all Windows in multi-arch initially**
   - Only build gfx1151 and gfx110X-all (which are more stable)
   - gfx120X-all continues running in regular CI until cache situation improves
   - Pragmatic: unblocks migration for the stable variants

**Recommendation:** Start with mitigation #1 (compiler-runtime ccache only). It's
low-risk, the compiler stage is a bottleneck that feeds everything, and LLVM is the
most cache-friendly workload. Can experiment with #2 later if cache pressure allows.
Consider #4 as an escape valve if gfx120X-all keeps failing.

### 2026-03-25 - PR #4161 Review (Windows bazel-remote ccache)

External PR by subodh-dubey-amd adds bazel-remote ccache to all Windows workflows.
Reviewed at `reviews/pr_TheRock_4161.md`. Key findings:
- 50.5% remote cache hit rate on Windows (vs 0.4% with old GitHub Actions cache)
- Build time reduction: 24% cold, 39% warm (gfx1151 release_windows_packages)
- Multi-arch Windows CI gets ccache for the first time
- Hit rate ceiling at ~50% due to MSVC "unsupported compiler option" (98.5% of
  uncacheable calls) — fundamental ccache/MSVC limitation
- **APPROVED** — this directly addresses our Gap 1 and is better than our planned
  "compiler-runtime ccache only" approach

**Impact on this task:** Gap 1 (Windows compiler cache) is being handled by #4161.
We can focus entirely on Gap 2 (post-build uploads/index pages).

## Decisions & Trade-offs

- **Decision:** Let PR #4161 handle Gap 1 (Windows ccache)
  - **Rationale:** External team member already has a working implementation with
    bazel-remote that covers all Windows workflows including multi-arch. Better than
    our planned incremental approach.
  - **Alternatives considered:** Adding ccache with GitHub Actions cache for
    compiler-runtime stage only (our original plan) — PR #4161 is strictly better

## Next Steps

1. [ ] Draft ccache addition for compiler-runtime stage in multi_arch_build_windows_artifacts.yml
2. [ ] Send experimental PR to collect cache hit data
3. [ ] Analyze post_build_upload.py to identify what can be reused per-stage
4. [ ] Design client-side index page workaround for multi-arch CI
5. [ ] Implement upload refactoring
