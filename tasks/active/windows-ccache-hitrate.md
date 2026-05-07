# Windows ccache Hit Rate Investigation

**Issues:** [#4519](https://github.com/ROCm/TheRock/issues/4519), [#4195](https://github.com/ROCm/TheRock/issues/4195)
**Related PR:** [#4419](https://github.com/ROCm/TheRock/pull/4419) (merged — fixed foundation/compiler, NOT math-libs)

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

### Theories: Investigated and Eliminated

**Theory A: Generated headers with embedded version/commit info.**
ELIMINATED. Downloaded `hip_version.h` and `rocm_version.h` from both runs.
Both contain `HIP_VERSION_GITHASH "79e85e14"` and `ROCM_BUILD_INFO
"7.13.0.0-9999-79e85e14"` — the submodule commit hash didn't change between
runs, so these headers are identical.

**Theory B: The clr-redistributed clang++.exe differs from amd-llvm's.**
ELIMINATED. Locally, both paths are hardlinked (34 links, same inode):
```
SHA256: 8b9bb99b70872985c5e8ba3fc7fe536f35e5151a1f433d839e9beaa268dfe62d
```

**Theory C: Source code changes between runs.**
PARTIALLY ELIMINATED. 705 out of 1021 common source files have IDENTICAL
manifest keys (same command line + compiler hash + source content), yet
693 of those still miss on both runs. Source code changes explain some
misses but not the bulk.

**Theory D: Absolute paths in -D defines or -I include paths.**
ELIMINATED. Paths are consistent across runners:
- Build tree: `B:/build/...` (always)
- Source tree: `C:/home/runner/_work/TheRock/TheRock/...` (always)
- Working dir: `B:\build\math-libs\...\build` (always)

### Finding 6: The critical clue — same manifest key, both miss

705 source files have IDENTICAL manifest keys across two runs, meaning:
- Same source file content
- Same compiler command line
- Same compiler binary hash (from `compiler_check = content`)

Yet **693 of those 705 miss on BOTH runs**. Of those:
- 591 have entries > 0 in the manifest (remote cache has data, but no entry matches)
- 89 mixed (entries in one run but not the other)
- 13 have 0 entries in both (no manifest on remote cache yet)

For a result entry to match, ALL included file checksums must match.
Since the manifest key is the same, something in the included headers
that changes is NOT related to the command line or compiler — it's a
header file whose CONTENT differs between runs despite identical source.

### Finding 7: Linux vs Windows — ccache version difference

| | Linux | Windows |
|---|---|---|
| ccache version | **4.11.2** (baked into manylinux container) | **4.13.6** (choco install, latest) |
| compiler_check | Custom Python script (posix_ccache_compiler_check.py) | `content` |
| clr/clang++ hit rate | **97.1%** | **0.9%** |
| Key format | Base36-like (`cc40f2u...`) | Hex SHA-1 (`5ab169...`) |

The different key formats confirm the cache entries from one version
CANNOT be used by the other. But within Windows, the version is stable
(4.13.6 in both runs checked).

Linux uses `compiler_check = <python_script>` which hashes the compiler
binary + shared libraries via sha256sum. Windows uses `compiler_check =
content`. Both should produce stable hashes since the binaries are
identical between runs.

### Active Theories

**Theory E: Non-deterministic header in the dependency chain.**
Something in the include tree has different content between runs despite
the source and version headers being identical. Checked `clang/Config/config.h`
and CMake export headers — no embedded build paths found so far. Need
`debug_level=3` to see which specific dependency checksum doesn't match.

**Theory F: ccache 4.13 behavior change vs 4.11.**
The different ccache versions produce different key formats (base36 vs hex
SHA-1). While entries within the same platform version should be compatible,
a ccache version upgrade (from choco) could have wiped all accumulated
entries. Also, a behavior change in manifest matching between 4.11 and
4.13 could explain why the same setup works on Linux but not Windows.

### Proposed Next Steps (ranked by impact)

1. **Enable `debug_level = 3` on one Windows CI run**: Add
   `debug = true` to the ccache config for a single run. This would log
   exactly which dependency file doesn't match in the manifest. This is
   the single most direct diagnostic step.
   - Modify `setup_ccache.py` to accept `--debug` flag
   - Or just add `debug = true` to the generated config for one run

2. **Pin ccache version on Windows**: Install ccache 4.11.2 (same as Linux)
   to test if version is a factor. Also eliminates the risk of future
   version changes silently invalidating the cache.

3. **Write a Windows `compiler_check` script**: Even if the compiler hash
   is stable, having parity with the POSIX approach provides consistency
   and makes it easier to reason about cache key stability across platforms.

4. **Test `base_dir` locally**: While paths appear consistent across
   runners, setting `base_dir` is cheap and could help with edge cases.

### Finding 8: PR #4419 never fixed math-libs

Checked CI runs on the `users/nicknick/win-ccache-repro` branch. The PR
author's claimed "98.31% hit rate" was from the **foundation** stage, not
math-libs. On the same branch, math-libs gfx1151 had **1.50% hit rate** —
identical to main. The PR successfully fixed:
- Foundation stage: 98.31% (uses cl.exe / gcc)
- Compiler-runtime: improved (uses cl.exe for LLVM build)

But math-libs (which uses clr/clang++) was never addressed.

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
