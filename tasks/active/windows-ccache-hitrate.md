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

### ROOT CAUSE FOUND: GUID-based workspace paths

Credit to @amd-nicknick for the key log excerpt in
[issue #4519 comment](https://github.com/ROCm/TheRock/issues/4519#issuecomment-4401521644).

Each Windows CI runner gets a unique workspace directory:
```
C:\B109CE3D-03D2-40EB-AD46-20E30992D028\build\...
C:\1CADE95B-7057-4C0D-9D47-8E810A59CE46\build\...
C:\6B7AEB7B-990F-47CB-BB17-C789587A37E2\build\...
```

ccache's direct mode records the absolute paths of ALL included files in
the manifest. When a subsequent run on a different runner tries to verify
a manifest entry, it checks whether each dependency file exists and has
matching content. Since the paths point to `C:\{GUID}\...` directories
that don't exist on the current runner, the check immediately fails with
"can't be read (No such file or directory)".

Evidence from our analyzed run (25465494022):
- **184,058 "can't be read" entries** in the ccache log
- **1,752 unique GUID-based workspace paths** from previous runs
- Every result entry from every previous run is unusable

This explains:
- Why Linux works: consistent `/__w/TheRock/TheRock/` path on all runners
- Why local builds work: same path every time
- Why manifest keys sometimes match but entries never do
- Why the hit rate is ~1.5% (only cl.exe compilations hit, because system
  headers at `C:\Program Files\...` have stable paths)

### Finding 9: GUID entries are ACTIVELY being written (post-namespace)

The `CCACHE_NAMESPACE_VERSION = "v1"` namespace was added in PR #4419,
merged May 4. Our analyzed runs are from May 7 — only 3 days later — and
already have **111 unique GUID-based workspace paths** in the cache.

This means something is **actively writing** entries with `C:\{GUID}\`
paths to the `therock-v1` namespace RIGHT NOW. Bumping the namespace
alone won't fix this — the poisoner will follow.

### Finding 10: The GUIDs aren't from TheRock's own CI

Checked both `build_windows_artifacts.yml` (old CI) and
`multi_arch_build_windows_artifacts.yml` (multi-arch CI):
- Both use `runs-on: azure-windows-scale-rocm`
- Both resolve `github.workspace` to `C:\home\runner\_work\TheRock\TheRock`
- Both use `BUILD_DIR: B:\build`
- Neither produces GUID-based paths

The old CI run (25464518294, ci.yml) uses `C:\home\runner\_work\...` and
gets **71% hit rate** (but that's amortized across all stages including
the easy-win compiler-runtime, not just math-libs).

The GUID paths look like Azure DevOps agent workspace directories or
a different GitHub Actions runner configuration. The bazelremote cache
server at `http://bazelremote-svc.bazelremote-ns.svc.cluster.local:8080`
is accessible to anything on the cluster with no auth, so any other
workflow/repo/tool using the same server with the same namespace could
be writing poisoned entries.

### Finding 11: Multiple repos share the same cache

Searched ROCm org for `azure-windows-scale-rocm`. At least these repos
share the same runner pool AND the same bazelremote cache:

| Repo | Workflows | Workspace path |
|------|-----------|---------------|
| ROCm/TheRock | ci, multi-arch | `C:\home\runner\_work\TheRock\TheRock` |
| ROCm/SPIRV-LLVM-Translator | ci, multi-arch | `C:\home\runner\_work\SPIRV-LLVM-Translator\SPIRV-LLVM-Translator` |
| ROCm/rocm-libraries | stinkytofu-ci, therock-ci | (skipped in recent runs) |
| ROCm/rocm-systems | therock-ci-windows | (logs expired) |
| ROCm/rocMLIR | build_windows_artifacts | (no Windows jobs found recently) |

All use `setup_ccache.py` → same namespace `therock-v1` → same bazelremote.
Each gets a different `C:\home\runner\_work\{repo}\{repo}` workspace path.

SPIRV-LLVM-Translator is confirmed to use the same ccache config preset
(`github-oss-dev`) and namespace. Its entries would pollute TheRock's cache
with `C:\...\SPIRV-LLVM-Translator\...` paths — not GUIDs, but still
unreachable from TheRock's workspace.

### Finding 12: B:\ is a mount/junction to C:\{GUID}\ — TheRock is the source

`B:\build` is a mount point or junction that resolves to `C:\{GUID}\build\`
where the GUID is unique per runner VM. When CMake/clang resolves paths,
it sometimes uses the REAL path (`C:\{GUID}\...`) instead of the mount
point (`B:\...`). This resolved path leaks into compiler flags.

Proof from the CURRENT run's own command line (MIOpen compilation):
```
-DHIP_COMPILER_FLAGS= ... C:/8A0235BC-8248-4249-82CE-CFF4055BEC2F/build/core/clr/dist/lib/llvm/lib/clang/23/lib/windows/clang_rt.builtins-x86_64.lib
```

The GUID `8A0235BC-...` is THIS runner's real path behind `B:\build`.
This means:
1. TheRock's OWN CI writes entries with GUID paths (not an external system)
2. The `-DHIP_COMPILER_FLAGS` define bakes in the resolved path
3. Since each runner has a different GUID, the command line differs
4. Different command line → different manifest key → no cache reuse

This also explains why clang resource headers (`__stdarg_va_copy.h` etc.)
appear with GUID paths in the manifest entries — clang resolves its own
resource directory through the real path, not the `B:\` mount.

The GUIDs are NOT from:
- Azure DevOps Pipelines
- External repos
- An older runner configuration

They're from TheRock's own CI, every run, on every runner.

### Open questions (resolved)

1. ~~What is writing GUID-path entries?~~ **Resolved:** TheRock's own CI.
   `B:\` is a volume mount point that resolves to `C:\{GUID}\`. Clang and
   CMake resolve through it.

2. ~~Why doesn't the cache self-heal?~~ **Resolved:** Every runner has a
   different GUID, so every run writes entries with unique absolute paths
   that no other runner can read.

3. Linux is unaffected — consistent workspace path `/__w/TheRock/TheRock/`
   on all runners, no volume mount indirection.

### Finding 13: base_dir doesn't fix the problem

Tested `base_dir` on CI (run 25527972656). Results:
- `base_dir = C:\8AA8C79D-...\build` (resolved from `B:\build`) — correct
- `namespace = therock-v2` — clean namespace, no old entries
- Still 1.5% hit rate

The v2 namespace is clean (only 1 foreign GUID: `497E179D` from
another gfx family's job in the same run). But entries written by
runner `497E179D` use absolute paths like `C:\497E179D-...\build\...`,
and `base_dir` on runner `8AA8C79D` only normalizes paths starting
with `C:\8AA8C79D-...\build`. Different GUIDs = different prefixes =
`base_dir` can't help.

The fundamental issue: `base_dir` normalizes paths relative to the LOCAL
resolved path, but every runner resolves `B:\build` to a DIFFERENT
`C:\{GUID}\build`. The stored entries use the writer's resolved GUID,
not `B:\build`.

### Finding 14: subst doesn't reproduce the problem locally

Local test using `subst J: {guid-dir}` showed cache hits across
"runners" — `subst` is transparent to path resolution (ccache sees
`J:\build\...` not the underlying path). Real CI uses NTFS volume
mount points which DO resolve, causing the GUID leak.

### Finding 15: base_dir only affects HASHING, not stored paths

Confirmed via CI test (run 25527972656). Runners with different GUIDs
(`497E179D` and `8AA8C79D`) both had base_dir set. The manifest key
hash IS shared (second runner found first runner's manifest). But
the dependency paths stored in result entries are ABSOLUTE with the
original runner's GUID:

```
C:\497E179D-...\build\compiler\amd-llvm\dist\lib\llvm\lib\clang\23\include\__stdarg_va_copy.h
```

If base_dir rewrote stored paths, we'd see `C:\8AA8C79D-...\...`
(reconstructed from our base_dir), not `C:\497E179D-...\...`.

From the ccache docs: "ccache converts absolute paths to relative
paths before hashing" — this is about hash computation only. Stored
manifest entries retain the original absolute paths. `base_dir` is
the wrong tool for this problem.

### Revised understanding

The B:\ drive on CI runners is an NTFS volume mount point (not a
`subst` or symlink). When clang resolves paths (e.g., its resource
directory for `stdarg.h`), Windows resolves through the mount point
to the underlying `C:\{GUID}\` path. This resolved path gets:
1. Embedded in `-DHIP_COMPILER_FLAGS` by CMake
2. Recorded by ccache as include file paths in manifests
3. Used by clang for resource directory headers

`base_dir` can't fix this because each runner's resolved path has
a different GUID prefix.

### Finding 16: ccache issue #1607 confirms base_dir limitation

Found ccache/ccache#1607 — the Conan team has the exact same problem
(varying path prefixes with identical content). The ccache maintainer
(jrosdahl) confirms:
- `base_dir` only rewrites paths for hash computation, not stored paths
- Manifest result entries store the ORIGINAL absolute paths
- When verifying, ccache reads files at the STORED path (no remapping)
- Workaround: use symlinks (or `subst` on Windows) to create stable paths
- A `CCACHE_REMAP_HEADERS` feature was discussed but doesn't exist yet

### Proposed fix: subst drive in CI workflow

Since `subst` is transparent to path resolution (proven locally), we can
interpose a `subst` drive between ccache and the `B:\` volume mount:

```yaml
- name: Stabilize build drive path for ccache
  shell: cmd
  run: subst R: B:\build

env:
  BUILD_DIR: R:\build
```

All downstream tools (cmake, clang, ccache) see `R:\build\...` paths.
`subst` doesn't resolve to `C:\{GUID}\...`, so ccache stores `R:\build\...`
in manifests. Every runner uses the same `R:\build\...` paths regardless
of GUID. `base_dir` is NOT needed with this approach.

Note: `R:\build` means the build tree is at `R:\build` (subst root is
`B:\build`, so `R:\build` = `B:\build\build`). Need to adjust either the
subst target or BUILD_DIR to match. E.g., `subst R: B:\` then
`BUILD_DIR: R:\build`, or `subst R: B:\build` then `BUILD_DIR: R:\`.

### Experiment results

**Experiment 0: base_dir only (no subst, no resource-dir)**
- [Run 25527972656](https://github.com/ROCm/TheRock/actions/runs/25527972656), full math-libs
- Jobs: [75068617048](https://github.com/ROCm/TheRock/actions/runs/25527972656/job/74936470686),
  [74946855786](https://github.com/ROCm/TheRock/actions/runs/25527972656/job/74946855786)
- Result: 1.5% hit rate — base_dir doesn't fix stored manifest paths

**Experiment 1: subst only (no resource-dir)**
- [Run 25571517906](https://github.com/ROCm/TheRock/actions/runs/25571517906) (attempt 1 + 2),
  [Run 25571986552](https://github.com/ROCm/TheRock/actions/runs/25571986552), rocRAND subset
- Jobs: [75068617048](https://github.com/ROCm/TheRock/actions/runs/25571517906/job/75068617048) (attempt 1, 0%),
  [75071771107](https://github.com/ROCm/TheRock/actions/runs/25571517906/job/75071771107) (attempt 2, 25%),
  [75070798414](https://github.com/ROCm/TheRock/actions/runs/25571986552/job/75070798414) (25%)
- Result: 25% hit rate (50/197)
- cl.exe: 92% hits. clr/clang++: 0.8% hits
- subst fixed command-line paths but clang still resolves its resource
  directory through the volume mount via `getMainExecutable()`

**Experiment 2: subst + `-resource-dir` override**
- [Run 25574538486](https://github.com/ROCm/TheRock/actions/runs/25574538486) (prebuilt, rocRAND subset),
  [Run 25574503612](https://github.com/ROCm/TheRock/actions/runs/25574503612) (non-prebuilt, rocRAND subset)
- Job: [75081701707](https://github.com/ROCm/TheRock/actions/runs/25574538486/job/75081701707) (attempt 2, 83%)
- Result: **83% hit rate** (164/197)
- cl.exe: 92% hits. clr/clang++: **80.6% hits**
- Zero "can't be read" entries in ccache log
- ALL 33 misses are CMake TryCompile probes (randomized directory names,
  expected to always miss). **100% hit rate on actual source files.**

**Experiment 3: subst + resource-dir, full math-libs**
- [Run 25576559806](https://github.com/ROCm/TheRock/actions/runs/25576559806) (full math-libs, in progress)

**Changes that worked:**
1. `subst D: B:\` — maps stable drive letter over the volume mount
2. `BUILD_DIR: D:\build` — all tools use the stable path
3. `-resource-dir` in toolchain CXX_FLAGS_INIT — prevents clang from
   resolving its resource dir through the mount
4. `CCACHE_NAMESPACE_VERSION = "v2"` — clean cache, no stale entries

### Remaining work

- [ ] Validate with full math-libs build (not just rocRAND subset)
- [ ] Validate non-prebuilt run (building clang from source)
- [ ] Apply same changes to `build_windows_artifacts.yml`
- [ ] Clean up experimental commits into a proper PR
- [ ] Consider whether TryCompile misses can be reduced (low priority)
- [ ] File issue for cross-repo cache pollution (SPIRV-LLVM-Translator etc.)

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
