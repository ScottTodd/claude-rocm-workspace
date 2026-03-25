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

## Design: Multi-Arch Stage Log Upload

### Problem

Multi-arch CI stages only upload artifact archives (`artifact_manager.py push`).
Unlike single-stage CI (`post_build_upload.py`), they don't upload build logs,
ninja log archives, or any other diagnostic files. This makes debugging failures
harder and blocks migration from single-stage CI.

### Proposed Solution: `post_stage_upload.py`

New script at `build_tools/github_actions/post_stage_upload.py`. Fork from
`post_build_upload.py` rather than extending it — the two scripts serve different
CI architectures with different assumptions.

**Responsibilities:**
1. Archive `.ninja_log` files from the build directory → `{build_dir}/logs/ninja_logs.tar.gz`
2. Upload `{build_dir}/logs/` to S3

**Not in scope (with rationale):**
- Artifact upload → `artifact_manager.py push` already handles this
- Manifest upload → broken by design (#1236), needs workflow-level generation
- Index page generation → server-side Lambda (#3331) handles this; a coworker
  is actively working on the Lambda
- Resource profiling (`therock-build-prof/`) → never designed for multi-arch CI
- GHA build summary → centralize in multi-arch configure or summary job, not
  per-stage. Can add a simple per-stage link later if needed.

### S3 Path Structure

**Current single-stage CI layout** (flat by artifact_group):
```
{run_id}-{platform}/logs/{artifact_group}/
  amd-llvm_build.log
  rocBLAS_build.log       ← all ~138 subproject logs in one dir
  ninja_logs.tar.gz
  index.html
  ...
```

**Proposed multi-arch layout** (structured by stage + family):
```
{run_id}-{platform}/logs/{stage_name}/                    # generic stages
{run_id}-{platform}/logs/{stage_name}/{amdgpu_family}/    # per-arch stages
```

Examples:
```
12345-linux/logs/foundation/                   # generic, no family
  rocm-cmake_build.log
  ninja_logs.tar.gz

12345-linux/logs/compiler-runtime/             # generic, no family
  amd-llvm_build.log
  ninja_logs.tar.gz

12345-linux/logs/math-libs/gfx1151/            # per-arch
  rocBLAS_build.log
  MIOpen_build.log
  ninja_logs.tar.gz

12345-linux/logs/math-libs/gfx110X-all/        # per-arch (parallel job)
  rocBLAS_build.log                            # same filename, different dir → no collision
  MIOpen_build.log
  ninja_logs.tar.gz
```

**Why this works without collisions:**
- Each multi-arch stage job has its own isolated build directory
- CMake writes per-subproject logs (`{target_name}_{build,configure,install}.log`)
  to `${BUILD_DIR}/logs/` (see `therock_subproject.cmake:126`)
- Per-arch stages (math-libs, comm-libs) run as parallel matrix jobs, each
  producing identically-named log files (e.g., `rocBLAS_build.log`)
- Uploading to `{stage_name}/{amdgpu_family}/` gives each job its own S3 directory

**Recommendation for Lambda index generation (#3331):**

The current single-stage CI layout puts ~250 log files in one flat directory.
That's noisy but great for Ctrl+F search (e.g., find `_install.log` to spot
which subproject failed). The nested multi-arch layout is cleaner for browsing
but makes cross-stage search harder. Two options for the Lambda:

1. **Per-directory indexes only** — each directory gets its own `index.html`
   listing only its direct contents. Simple, matches S3 structure 1:1.
   Downside: searching across stages requires opening each directory.

2. **Recursive index at `logs/index.html`** — lists all files across all
   subdirectories with relative paths like `math-libs/gfx1151/rocBLAS_build.log`.
   Preserves the "Ctrl+F across everything" workflow from single-stage CI while
   keeping the nested storage structure. Per-directory indexes can coexist.

We recommend option 2 (recursive) for the top-level `logs/` index. It gives
the best of both worlds: organized storage + flat searchability.

**Why per-job index pages are safe (future improvement):**
- Each job exclusively owns its upload directory
- Could generate `index.html` locally before uploading — no race conditions
- Deferred for now; the Lambda will handle all index generation

### WorkflowOutputRoot Changes

Add a `stage_log_dir()` method to `WorkflowOutputRoot`:

```python
def stage_log_dir(self, stage_name: str, amdgpu_family: str = "") -> StorageLocation:
    """Location for a multi-arch stage log directory."""
    if amdgpu_family:
        return StorageLocation(
            self.bucket, f"{self.prefix}/logs/{stage_name}/{amdgpu_family}"
        )
    return StorageLocation(self.bucket, f"{self.prefix}/logs/{stage_name}")
```

### CLI Interface

```
python post_stage_upload.py \
    --build-dir build \
    --stage-name math-libs \
    --amdgpu-family gfx1151 \
    --run-id ${{ github.run_id }} \
    --upload
```

Arguments:
- `--build-dir` — build directory containing `logs/` (default: `$BUILD_DIR` or `build`)
- `--stage-name` — stage name, required (e.g., `foundation`, `math-libs`)
- `--amdgpu-family` — GPU family, optional (e.g., `gfx1151`). Empty for generic stages.
- `--run-id` — GitHub run ID (default: `$GITHUB_RUN_ID`). Required when uploading.
- `--upload/--no-upload` — enable S3 upload (default: enabled if `$CI` is set)
- `--output-dir` — local directory for testing (bypasses S3)
- `--dry-run` — print actions without uploading

### Workflow Integration

Add steps to both `multi_arch_build_portable_linux_artifacts.yml` and
`multi_arch_build_windows_artifacts.yml`, after artifact push:

```yaml
- name: Upload stage logs
  if: ${{ !cancelled() }}
  run: |
    python build_tools/github_actions/post_stage_upload.py \
      --build-dir="${BUILD_DIR}" \
      --stage-name="${STAGE_NAME}" \
      --amdgpu-family="${AMDGPU_FAMILIES}" \
      --run-id=${{ github.run_id }} \
      --upload
```

The `if: !cancelled()` ensures logs are uploaded even on build failures (the most
important case for debugging).

### Alternatives Considered

1. **Extend `post_build_upload.py` with `--stage-name` flag**
   - Rejected: the existing script has too many single-stage assumptions (manifest
     upload, resource profiling, artifact upload, index generation). Adding flags
     to skip each one makes it harder to understand than a focused new script.

2. **Flatten all stage logs into a single directory with renamed files**
   - e.g., `math-libs-gfx1151_rocBLAS_build.log`
   - Rejected: ugly naming, harder to browse, doesn't compose well with index
     generation. Subfolders are natural and match the job structure.

3. **Stage name in the archive filename** (`ninja_logs_math-libs.tar.gz`)
   - Not needed: each stage uploads to its own directory, so `ninja_logs.tar.gz`
     is unambiguous within that directory. Would only matter if we wanted all
     archives in a single flat directory.

4. **Client-side index page generation per job**
   - Safe (each job owns its directory, no races) but deferred since the Lambda
     will handle all index generation. Could be added later as a quick improvement
     if the Lambda is delayed.

5. **Per-stage GHA build summary with log links**
   - Deferred. Each stage posting its own summary would produce duplicate/noisy
     output. Better to centralize in the multi-arch configure job or a dedicated
     summary job. Can add simple per-stage log links as a first pass if needed.

## Decisions & Trade-offs

- **Decision:** Let PR #4161 handle Gap 1 (Windows ccache)
  - **Rationale:** External team member already has a working implementation with
    bazel-remote that covers all Windows workflows including multi-arch. Better than
    our planned incremental approach.
  - **Alternatives considered:** Adding ccache with GitHub Actions cache for
    compiler-runtime stage only (our original plan) — PR #4161 is strictly better

- **Decision:** Fork into new `post_stage_upload.py` script
  - **Rationale:** `post_build_upload.py` has too many single-stage assumptions.
    A focused script is easier to understand and maintain.
  - **Alternatives considered:** Extending `post_build_upload.py` with flags to
    skip inapplicable functionality — rejected as it would accumulate complexity.

- **Decision:** Use `{stage_name}/{amdgpu_family}` S3 path structure
  - **Rationale:** Natural mapping to job structure, no file collisions, good for
    browsing and index generation.
  - **Alternatives considered:** Flat directory with prefixed filenames — ugly and
    doesn't compose well.

- **Decision:** No client-side index generation for now
  - **Rationale:** Server-side Lambda (#3331) is being actively developed. Per-job
    index pages are safe but unnecessary work if the Lambda lands soon.
  - **Note:** Can revisit if Lambda is delayed — per-job indexes are race-free.

## Next Steps

1. [x] ~~Pull build performance metrics~~ (done)
2. [x] ~~Review PR #4161~~ (done, APPROVED)
3. [x] ~~Analyze post_build_upload.py~~ (done)
4. [x] ~~Design multi-arch upload approach~~ (done, documented above)
5. [ ] Share design with team for feedback
6. [ ] Implement `post_stage_upload.py` + `WorkflowOutputRoot.stage_log_dir()`
7. [ ] Add tests for the new script
8. [ ] Wire into multi-arch workflow files (Linux + Windows)
9. [ ] Test on a fork run
10. [ ] Send PR
