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

### Open questions

1. **What is writing GUID-path entries?** 111 unique GUIDs in 3 days.
   The `C:\{GUID}\` pattern is characteristic of Azure DevOps Pipelines
   agents, NOT GitHub Actions (which uses `_work/{repo}/{repo}`).
   Something outside GitHub Actions may be writing to the cache.

2. **Why doesn't the cache self-heal?** Each manifest accumulates entries
   over time. GUID entries from the poisoner pile up. Even when a valid
   multi-arch entry exists, it's buried under dozens of GUID entries that
   each trigger "can't be read" failures. ccache iterates through ALL
   entries before falling through to preprocessed mode. If the valid entry
   happens to have the same result key, it might be found eventually, but
   typically the dependency checksums differ between commits anyway.

3. **Are Linux entries also affected?** Linux uses a different runner pool
   and likely different workspace paths. If Linux runs also write to the
   same bazelremote server with `therock-v1`, there could be cross-platform
   entry pollution (though different compiler hashes would produce different
   manifest keys, keeping them separate).

### Proposed fixes (prioritized)

1. **Find and stop the poisoner**: Identify what's writing GUID-path
   entries to the `therock-v1` namespace on the dev bazelremote server.
   This is the root cause — everything else is a workaround.
   - Check if other repos (forks, internal mirrors) use the same cache
   - Check if Azure Pipelines or other CI systems share the cluster
   - Add logging to the bazelremote server to track write sources

2. **Set `base_dir` in ccache config**: This makes ccache normalize
   absolute paths to relative before storing in manifests. Even if
   different runners have different workspace roots, the stored paths
   would be relative and thus portable. This defends against both the
   current poisoning AND any future workspace path changes.
   - `base_dir` only accepts ONE directory, so we'd need it to cover
     the common prefix of both source and build trees
   - On current multi-arch CI: source at `C:\home\runner\_work\TheRock\TheRock`,
     build at `B:\build` — these have no common prefix
   - Possible approach: symlink one under the other, or move build tree

3. **Bump namespace + namespace per workflow**: Change to `v2` and
   consider separate namespaces for old CI vs multi-arch CI to prevent
   cross-pollution. Won't help if the poisoner also picks up the new
   namespace from `setup_ccache.py`.

4. **Pin ccache version**: Move from dynamic `choco install` to a fixed
   version in the runner image.

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
