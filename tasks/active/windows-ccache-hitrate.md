# Windows ccache Hit Rate Investigation

**Issues:** [#4519](https://github.com/ROCm/TheRock/issues/4519), [#4195](https://github.com/ROCm/TheRock/issues/4195)
**Related PR:** [#4419](https://github.com/ROCm/TheRock/pull/4419) (merged)

## Investigation Log

### Setup

Investigating why Windows math-libs builds consistently get ~1.5% ccache hit
rates on CI, despite PR #4419 achieving 98%+ locally. Linux gets 40%+ on the
same stage.

Two CI runs used for analysis:
- **Run A**: 25465494022 (commit e55ebbc, 2026-05-07)
- **Run B**: 25496971293 (commit c640f2f, 2026-05-07)
Both are multi-arch CI runs on the `main` branch.

### Downloaded Files

All in `D:/scratch/claude/ccache-investigation/`:

```
gfx1151/                          # Extracted from Run A
  ccache.log                      # 1.6M lines, the main analysis target
  ccache_stats.log                # 118K lines

compiler-compare/
  run_25465494022/
    clang++.exe                   # 106,338,304 bytes (from amd-llvm_run_generic.tar.zst)
  run_25496971293/
    clang++.exe                   # 106,338,304 bytes (from amd-llvm_run_generic.tar.zst)
```

The ccache logs come from the S3 artifact at:
```
https://therock-ci-artifacts.s3.amazonaws.com/{RUN_ID}-windows/logs/math-libs/gfx1151/ccache_logs.tar.zst
```

The compiler binaries come from (streaming ~600MB, extracting just clang++.exe):
```
https://therock-ci-artifacts.s3.amazonaws.com/{RUN_ID}-windows/amd-llvm_run_generic.tar.zst
```

### Finding 1: Almost all misses are from clr/clang++.exe

From Run A ccache stats (gfx1151 math-libs):
```
Cacheable calls:    7935 / 8014 (99.01%)
  Hits:              118 / 7935 ( 1.49%)
  Misses:           7817 / 7935 (98.51%)
```

Parsed the 1.6M-line ccache.log to correlate compiler binary with hit/miss
per ccache session (each session starts with `=== CCACHE STARTED ===`):

| Compiler | Hits | Misses | Hit Rate |
|----------|------|--------|----------|
| cl.exe (MSVC) | 50 | 5 | 91% |
| clr/clang++.exe | 66 | 7640 | 0.9% |
| clr/clang.exe | 0 | 32 | 0% |
| amd-llvm/clang++.exe | 0 | 12 | 0% |

The 4 compilers used (full paths):
```
B:\build\core\clr\dist\lib\llvm\bin\clang++.exe     7872 compilations
C:\Program Files\...\MSVC\14.44.35207\...\cl.exe       87 compilations
B:\build\core\clr\dist\lib\llvm\bin\clang.exe          41 compilations
B:\build\compiler\amd-llvm\dist\...\clang++.exe        14 compilations
```

Run B shows nearly identical numbers: 126 hits / 7935 (1.59%).

### Finding 2: The amd-llvm compiler binary IS byte-identical across runs

Downloaded `clang++.exe` from the `amd-llvm_run_generic.tar.zst` artifact
of both runs. Both are exactly 106,338,304 bytes and are byte-for-byte
identical. This means `/Brepro` IS working for the compiler stage.

So the initial theory (compiler binary non-reproducibility) is WRONG for
the amd-llvm stage output. The `compiler_check = content` hash should be
stable.

**Open question:** Is the clang++.exe at `core/clr/dist/lib/llvm/bin/`
(used by math-libs) the same binary as `compiler/amd-llvm/dist/lib/llvm/bin/`?
The CLR stage redistributes the compiler — need to verify it's a straight
copy, not a rebuild. Haven't downloaded the core-stage artifact to check
this yet.

### Finding 3: /Brepro does reach the LLVM build

Checked the build system (via agent search of TheRock source):

- `/Brepro` is set in `cmake/therock_subproject.cmake` lines 824-829
- It's injected via `add_link_options("LINKER:/Brepro")` into every
  subproject's `project_init.cmake` on Windows
- The amd-llvm subproject is NOT excluded — it gets `/Brepro` too
- On Windows, the amd-llvm build uses MSVC's `link.exe` (not lld-link),
  which supports `/Brepro`
- Both `link.exe` and `lld-link` support `/Brepro`

### Finding 4: Remote cache has manifests, but result entries don't match

From the ccache.log:
```
remote_storage_read_hit:    6898   (manifests/results found on server)
remote_storage_hit:           53   (actually usable cache entries)
```

This means the remote cache server (bazelremote) has data from previous
runs. Manifests are found, but the result entries within them don't match
the current build context. Each manifest can contain multiple result entries
(for different compiler versions, different dependency checksums, etc.).

Across all 8014 sessions:
- 201,827 result entries were "considered" (checked against current context)
- Only 55 matched (the 55 direct hits, mostly from cl.exe)

### Finding 5: Session-level miss analysis

Parsed the log into 8014 individual ccache sessions. For "real" clr/clang++
misses (excluding CMake try-compiles), there are 2801 sessions:

| Entries considered | Count | Meaning |
|-------------------|-------|---------|
| 0 | 968 | No manifest found at all (direct hash differs completely) |
| 1-5 | 272 | Manifest found, few entries, none matched |
| 6-50 | 1082 | Manifest found, several stale entries |
| 50+ | 479 | Manifest found, many stale entries (accumulated over runs) |

**968 sessions with 0 entries**: The direct hash (source + command line +
compiler hash) didn't match anything. This suggests command-line arguments
or the working directory differ between runs. ccache has `hash_dir = true`
by default, but the build directory is consistently `B:\build\...` across
runners.

**1833 sessions with entries > 0**: Manifests were found on the remote
cache, but the result entries (which include dependency file checksums)
didn't match. This means some included header files have different content
between runs.

### Current Theories

**Theory A: Generated headers with embedded version/commit info.**
Many ROCm libraries generate version headers during CMake configure that
include git commit hashes, build dates, or version strings. These change
every run even if the actual source code is identical. This would explain
why manifests are found (same source file) but result entries don't match
(different header checksums).

**Theory B: The clr-redistributed clang++.exe differs from amd-llvm's.**
The math-libs stage uses `core/clr/dist/lib/llvm/bin/clang++.exe`, not the
amd-llvm dist directly. If CLR's dist produces a different binary (e.g.,
through a different copy/install mechanism), the `compiler_check = content`
hash would differ even though the amd-llvm source is identical. Haven't
verified this yet.

**Theory C: Source code changes between runs.**
The two analyzed runs are on different commits (e55ebbc vs c640f2f). If
source files changed, cache misses are expected. But the ~1.5% hit rate
is consistent even across runs on the same commit, so this alone doesn't
explain it.

**Theory D: Absolute paths in -D defines or -I include paths.**
If any compiler flags embed runner-specific paths (hostnames, workspace
paths), they'd change the direct hash. The workspace is at
`C:\home\runner\_work\TheRock\TheRock` — if different runners have different
paths, this would invalidate the direct hash. However, the working directory
and build dir (`B:\build`) appear consistent.

### Next Steps

1. **Verify Theory B**: Download the `core` stage artifact and compare
   `clr/dist/lib/llvm/bin/clang++.exe` against `amd-llvm/dist/lib/llvm/bin/clang++.exe`
   within the same run. If they differ, that's a major contributor.

2. **Verify Theory A**: Look at specific sessions where manifests were found
   (entries > 0) and identify which dependency files have different checksums.
   Need to trace a specific compilation from both runs to compare include
   file lists.

3. **Check command lines**: Compare the exact compiler command lines from
   two runs for the same source file. Any path or version differences in
   -D/-I flags would explain the "0 entries" sessions.

4. **Consider `base_dir` config**: ccache's `base_dir` setting can normalize
   absolute paths in the hash. If set to the build root, paths like
   `B:\build\...` would be made relative, improving cross-runner cache hits.
   Currently `base_dir` is not set (default empty).

## Analysis Tooling

Created in `scripts/`:

- `analyze_ccache_logs.py` — Downloads + parses ccache logs from S3 artifacts.
  Reports hit/miss rates broken down by compiler and project.
  ```
  python scripts/analyze_ccache_logs.py --run-id 25465494022 --stage math-libs --gfx gfx1151
  ```

- `compare_compiler_binaries.py` — Downloads amd-llvm archives from two runs,
  extracts just clang++.exe, and does byte-level comparison with PE header
  parsing.
  ```
  python scripts/compare_compiler_binaries.py --run-id1 25465494022 --run-id2 25496971293
  ```

Both scripts cache downloaded/extracted files in `D:/scratch/claude/ccache-investigation/`
so re-runs are fast.

## Reference

### S3 URL patterns
```
https://therock-ci-artifacts.s3.amazonaws.com/{RUN_ID}-windows/logs/{stage}/{gfx}/ccache_logs.tar.zst
https://therock-ci-artifacts.s3.amazonaws.com/{RUN_ID}-windows/logs/{stage}/{gfx}/index.html
https://therock-ci-artifacts.s3.amazonaws.com/{RUN_ID}-windows/amd-llvm_run_generic.tar.zst
```

### Checking ccache stats from a job
```bash
gh api repos/ROCm/TheRock/actions/jobs/{JOB_ID}/logs 2>/dev/null | grep -A 25 "Cacheable calls"
```

### Finding math-libs jobs
```bash
gh api repos/ROCm/TheRock/actions/runs/{RUN_ID}/jobs --paginate \
  -q '.jobs[] | select(.name | contains("math-libs") and contains("gfx1151") and contains("Windows")) | "\(.id) \(.conclusion)"'
```

### ccache config in effect (from log)
```
compiler_check = content
hash_dir = true               # working dir is part of hash
base_dir =                     # NOT set (absolute paths not normalized)
sloppiness = include_file_ctime, pch_defines, time_macros
namespace = therock-v1
remote_storage = http://bazelremote-svc.../|layout=bazel|connect-timeout=50
```
