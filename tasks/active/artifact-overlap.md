---
repositories:
  - therock
---

# Artifact Overlap Testing & Fixes

- **Status:** PR drafted, awaiting CI
- **Priority:** P1 (High)
- **Started:** 2026-03-04
- **Tracking:** https://github.com/ROCm/TheRock/issues/3796

## Overview

Artifact archives can contain files that collide when extracted together.
This causes silent overwrites or race conditions during parallel extraction
(see #3758, #2784). We need tests to prevent regressions and fixes for the
known overlaps.

Two classes of collision:

1. **Cross-artifact**: Different artifact names produce files that flatten to
   the same path (e.g., `blas_dev` and `support_dev` both contain
   `include/mxDataGenerator/*.hpp`).
2. **Within-artifact component**: Different components of the same artifact
   contain the same file (e.g., `miopen_run` and `miopen_test` both contain
   `bin/miopen_gtest`).

## Goals

- [x] Cross-artifact collision test (`tests/test_artifact_structure.py`)
- [x] Within-artifact component collision test (`tests/test_artifact_structure.py`)
- [x] Basedir overlap unit test (`build_tools/tests/artifact_descriptor_overlap_test.py`)
- [x] CI workflow for manual testing (`test_artifacts_structure.yml` with workflow_dispatch)
- [x] Wire workflow into `ci_linux.yml`, `ci_windows.yml`, `multi_arch_ci_linux.yml`, `multi_arch_ci_windows.yml`
- [ ] Fix mxDataGenerator overlap (blas vs support) — PR #3773
- [ ] Fix miopen within-artifact overlap — PR #3793 (external)
- [x] Fix systemic `test` component extends issue — `test extends doc`
- [x] Fix within-artifact overlaps via descriptor excludes (miopen, rocprofiler-sdk, rocrtst, base)
- [x] Documentation update (`docs/development/artifacts.md`)
- [ ] Target-specific archive content validation (kpack namespacing)

## Workstreams

### WS1: Fixing Known Overlaps

**mxDataGenerator (blas vs support)** — Issue #3770, PR #3773

- Root cause: rocRoller has mxDataGenerator as BUILD_DEPS. mxDataGenerator's
  headers and cmake files spill into `math-libs/BLAS/rocRoller/stage/`.
  Both `artifact-blas.toml` (which includes rocRoller's stage) and
  `artifact-support.toml` (which includes mxDataGenerator's stage) package
  these files.
- First fix attempt used `include` patterns on rocRoller entries in
  `artifact-blas.toml`. Failed because `include` lists are **augmented** with
  component defaults (e.g., dev defaults add `**/include/**`) — see
  `artifact_builder.py:249-254`.
- Working fix: `exclude` patterns on rocRoller's dev entry:
  ```toml
  exclude = ["include/mxDataGenerator/**", "lib/cmake/mxDataGenerator/**"]
  ```
- PR #3773 has two commits (include attempt, then exclude fix). Needs CI
  verification of the second commit.

**miopen run/test overlap** — Issue #2784, PR #3793 (external)

- Root cause: `miopen_run` has no explicit patterns, so `includes=[]` acts as
  catch-all — everything not claimed by `lib` goes into `run`, including
  `bin/miopen_gtest`. Meanwhile `test` has `include = ["bin/miopen_gtest*"]`
  and no extends chain, so it re-claims the same file.
- PR #3793 adds `exclude = ["bin/miopen_gtest*"]` to miopen's `run` component.
  The miopen half is correct.
- PR #3793 also adds `exclude = ["bin/*hipdnn_*_test*"]` to hipdnn's `lib`
  component. This is harmless but unnecessary — `lib` defaults (`**/*.so*`)
  never match those executables anyway. No actual overlap exists for hipdnn
  in current builds.

### WS2: Tests

**Approach 1 — Basedir overlap unit test** (PR #3765, merged)

- `build_tools/tests/artifact_descriptor_overlap_test.py`
- Parses all `artifact-*.toml` files and checks that no stage directory
  appears in two different descriptors.
- Catches the original #3758 case (aqlprofile stage in both
  rocprofiler-sdk and aqlprofile-tests descriptors).
- Does NOT catch BUILD_DEPS spillover (different stage dirs, same files).

**Approach 2 — Archive content tests** (branch `artifact-overlap-testing-2`)

- `tests/test_artifact_structure.py` (renamed from `test_artifact_collisions.py`)
- Two tests in `TestArtifactStructure`:
  - `test_no_cross_artifact_collisions` — flags paths in 2+ different artifacts
  - `test_no_within_artifact_component_collisions` — flags pairwise component overlap
- Scans actual artifact archives (without extracting) using shared
  `archive_index` fixture (`list[ArchiveInfo]` dataclass).
- Tested locally and via CI workflow_dispatch:

  | Artifact set | Archives | Cross-artifact | Within-artifact |
  |---|---|---|---|
  | Windows gfx110X-all (classic) | ~100 | 36 (mxDataGenerator) | ~4,700 (10 artifacts) |
  | Linux multi-arch, 5 families (classic) | ~500 | 36 (same, `_generic` only) | same pattern |
  | Linux kpack (generic + gfx942) | ~207 | 36 (same) | 4,777 (10 artifacts) |

- Key finding: collisions are uniform across GPU families and artifact
  formats. Driven entirely by descriptor config, not build variation.
- Within-artifact collisions ALL involve `test` component. Worst offenders:
  rocprofiler-compute (4,162 files), rocprofiler-sdk (480), rocrtst (89).
  Root cause: `test` has no extends chain (commit 6282bd46), so it
  re-claims files already taken by other components.

**Approach 4 — Target-specific content validation** (not yet implemented)

- Per-target archives (e.g., `blas_lib_gfx942`) should only contain
  target-namespaced files (`.kpack`, `.co`, `.hsaco`, `.dat`, `.model`).
- Validated manually: blas_lib_gfx942 has 1358 files (651 .dat, 650 .co,
  56 .hsaco, 1 .kpack). No headers, cmake configs, or shared libs.

### WS3: CI Integration

**Workflow file:** `.github/workflows/test_artifacts_structure.yml`

Initial implementation (PR #3802, merged):

- CPU-only runner (`azure-linux-scale-rocm` on ROCm org, `ubuntu-24.04` on forks)
- `workflow_dispatch` for manual testing + `workflow_call` for CI integration
- Inputs: `artifact_group`, `amdgpu_targets`, `artifact_run_id`
- Fetches archives via `fetch_artifacts.py --no-extract`
- Runs `pytest tests/test_artifact_structure.py -v --log-cli-level=info --timeout=300`
- Note: had `--run-github-repo=ROCm/TheRock` hardcoded for fork testing

**CI test runs (2026-03-05):**

| Run | Format | Fetch | Validate | Result |
|---|---|---|---|---|
| [22743296445](https://github.com/ScottTodd/TheRock/actions/runs/22743296445) | classic `.tar.xz` | 74s | 169s | 2 FAILED |
| [22743345907](https://github.com/ScottTodd/TheRock/actions/runs/22743345907) | kpack `.tar.zst` | 12s | 18s | 2 FAILED |

The ~8x performance difference is due to xz vs zstd decompression during archive listing.

**Changes on PR #3830:**

- Removed unused `amdgpu_targets` input
- Added `platform` input (linux/windows) — always runs on Linux runners, even
  for Windows artifacts (just inspecting files, not running project code)
- Passes `--platform=${PLATFORM}` to `fetch_artifacts.py`
- Wired `workflow_call` into all four CI orchestration workflows:

  | Workflow | New job | Notes |
  |---|---|---|
  | `ci_linux.yml` | `validate_linux_artifact_structure` | `platform: linux` |
  | `ci_windows.yml` | `validate_windows_artifact_structure` | `platform: windows` |
  | `multi_arch_ci_linux.yml` | `validate_artifact_structure` | Single job (not per-family matrix) |
  | `multi_arch_ci_windows.yml` | `validate_artifact_structure` | `platform: windows` |

### WS4: Documentation

`docs/development/artifacts.md` was missing critical information:

- Component inheritance chain (`lib -> run -> dbg -> dev -> doc`)
- Default patterns per component type
- The catch-all behavior (empty `includes` = match everything)
- How `test` stands alone (no extends, no transitive_relpaths sharing)
- `include` augments defaults rather than replacing them
- Auto-creation of intermediate components
- BUILD_DEPS spillover and mitigation strategies

**Added on PR #3830:**

- Extends chain diagram (`lib -> run -> dbg -> dev -> doc -> test`)
- Default patterns table per component type
- WARNING callout about `run` catch-all behavior
- Two concrete routing approaches with real examples (rocBLAS, rocSPARSE, MIOpen, rocrtst)
- Guidance on when to use `exclude` vs `default_patterns = false`

## Key Technical Findings

### Component Inheritance Model

```
lib -> run -> dbg -> dev -> doc     (extends chain)
test                                (standalone, no extends)
```

Processing order follows extends. Each component skips files already in
`transitive_relpaths` from parent components, making them disjoint. But
`test` doesn't participate — it can re-claim files already taken by others.

### Default Patterns

| Component | Includes | Extends |
|---|---|---|
| lib | `**/*.so*`, `**/*.dll`, `**/*.dylib*` | — |
| run | (none — catch-all) | lib |
| dbg | `.build-id/**/*.debug` | run |
| dev | `**/*.a`, `**/cmake/**`, `**/include/**`, `**/pkgconfig/**`, etc. | dbg |
| doc | `**/share/doc/**` | dev |
| test | (none) | (none) |

When `includes` is empty, `MatchPredicate.matches()` skips the include
check — everything passes. This makes `run` a catch-all for anything not
matched by `lib`.

### `include` Augments Defaults

`artifact_builder.py:249-254`:
```python
includes = _dup_list_or_str(record.get("include"))
if use_default_patterns:
    includes.extend(defaults.includes)
```

Explicit `include` lists get default patterns appended (e.g., dev defaults
add `**/include/**`). Use `exclude` or `default_patterns = false` to
restrict instead.

### BUILD_DEPS Spillover

When subproject A lists B as a BUILD_DEPS, B's installed files appear in
A's stage directory. If both A's artifact and B's own artifact package
those files, they collide after flattening. Fix with `exclude` patterns
in the descriptor that claims A's stage dir.

## Artifacts on Disk

Test data in `D:/scratch/claude/artifacts/`:

| Directory | Source | Contents |
|---|---|---|
| `22681848469-linux-gfx94X-dcgpu` | Classic CI | ~100 `.tar.xz` archives |
| `22703255745-linux-multi` | Multi-arch CI (5 families) | ~500 `.tar.xz` archives |
| `22684449108-linux-kpack` | Kpack CI (generic + gfx942) | ~207 `.tar.zst` archives |
| `22696910967-linux-gfx94X-dcgpu` | PR #3773 CI run | For verifying fix |

## Descriptor Fix Details

Each fix below was needed because `test extends doc` changed which component
claims files first. Before: `test` processed independently and could re-claim
files. After: `test` is last in the extends chain and only gets leftovers.

### Fixes where `run` catch-all steals from `test`

These descriptors have a bare `[components.run."..."]` (no includes = catch-all)
that grabs everything not in `lib`. Previously `test` independently re-claimed
its files (an overlap). Now `run` wins and `test` gets nothing unless we exclude.

**miopen** (`ml-libs/artifact-miopen.toml`)
- File: `bin/miopen_gtest*`
- Before: in both `_run` (catch-all) and `_test` (`include = ["bin/miopen_gtest*"]`)
- Fix: `exclude = ["bin/miopen_gtest*"]` on `run`
- Why: test binaries belong in `_test`. Test infra fetches `miopen_test`.
- Alternative: could add `miopen_run` to install script instead, but
  semantically these are test files.

**rocprofiler-sdk** (`profiler/artifact-rocprofiler-sdk.toml`)
- Files: `share/rocprofiler-sdk/tests/**`
- Before: in both `_run` (catch-all) and `_test` (`include = ["share/rocprofiler-sdk/tests/**"]`)
- Fix: `exclude = ["share/rocprofiler-sdk/tests/**"]` on `run`
- Why: test data belongs in `_test`. Test infra fetches `rocprofiler-sdk_test`.

**rocprofiler-register in base** (`base/artifact.toml`)
- Files: `share/rocprofiler-register/tests/**`
- Before: in both `_run` and `_test` (`include = ["share/rocprofiler-register/tests/**"]`)
- Fix: `exclude = ["share/rocprofiler-register/tests/**"]` on `run`
- Why: same pattern as rocprofiler-sdk.

**rocrtst** (`core/artifact-core-rocrtst.toml`)
- Files: `bin/**` (test binaries like `bin/gfx*/rocrtst`)
- Before: in both `_run` (catch-all) and `_test` (bare, also catch-all)
- Fix: `exclude = ["bin/**"]` on `run`
- Why: rocrtst is a test-only artifact. All bin/ content is test executables.
- Note: `test` also excludes `lib/rocrtst/lib/libhwloc.so*` and
  `lib/rocrtst/lib/LICENSE` which belong in `_lib`.

**aqlprofile** (`profiler/artifact-aqlprofile.toml`)
- Files: `share/hsa-amd-aqlprofile/**` (test scripts + hsaco test data)
- Before: in both `_run` (catch-all) and `_test` (`include = ["share/hsa-amd-aqlprofile/**"]`)
- Fix: `exclude = ["share/hsa-amd-aqlprofile/**"]` on `run`
- Why: test infra fetches `aqlprofile_test` and expects `run_tests.sh` there.
  CI failure confirmed: `FileNotFoundError: ... run_tests.sh` in
  [job 66104473133](https://github.com/ROCm/TheRock/actions/runs/22782491222/job/66104473133).
- Alternative: could add `aqlprofile_run` to install script, but these
  are clearly test files (test scripts, `gfx90a_simple_convolution.hsaco`).

### Fixes where `dev` defaults steal from `test`

The `dev` component has default includes like `**/include/**` and `**/cmake/**`
that can match files inside test directories. Previously `test` processed
independently so it also claimed them (overlap). Now `dev` processes first
(earlier in extends chain) and wins.

**rocgdb** (`debug-tools/artifact-rocgdb.toml`)
- Files: `tests/rocgdb/include/dwarf2.h`, `tests/rocgdb/include/dwarf2.def`
- Before: in both `_dev` (`**/include/**` default) and `_test` (`include = ["tests/**"]`)
- Fix: `exclude = ["tests/**"]` on `dev`
- Why: the rocgdb testsuite references `../../include/dwarf2.h` relative to
  `tests/rocgdb/gdb/testsuite/`. Test infra fetches `rocgdb_test` but not
  `rocgdb_dev`. CI failure confirmed: `couldn't open ... dwarf2.h` in
  [job 66104473158](https://github.com/ROCm/TheRock/actions/runs/22782491222/job/66104473158).
- Alternative: could add `rocgdb_dev` to install script, but header files
  inside `tests/` clearly belong in `_test`.

**hipSPARSE in blas** (`math-libs/BLAS/artifact-blas.toml`)
- File: `share/hipsparse/test/hipsparse_clientmatrices.cmake`
- Before: in both `_dev` (explicit `include = ["**/*.cmake"]` + default
  `**/cmake/**`) and `_test` (`include = ["share/hipsparse/test/**"]`)
- Fix: `exclude = ["share/hipsparse/test/**"]` on hipSPARSE's `dev`
- Why: this cmake script is a test client tool for downloading test matrices
  (referenced in `hipsparse/clients/include/utility.hpp:74`). Belongs in
  `_test`. No CI failure yet but would break if hipsparse tests need it.
- Alternative: could add `blas_dev` to install script, but this is test
  tooling that happens to be a `.cmake` file.

**rocdecode** (`media-libs/artifact-rocdecode.toml`) — NO FIX NEEDED
- Files: `share/rocdecode/cmake/Find*.cmake`
- Before: in both `_dev` (`**/cmake/**` default) and `_test` (`include = ["share/rocdecode/**"]`)
- Now: `dev` wins, files move to `_dev`
- Why no fix: test infra already fetches `rocdecode_dev` (line 408 of
  `install_rocm_from_artifacts.py`), so the files are available either way.

### Install script change

**rocprofiler-compute** (`build_tools/install_rocm_from_artifacts.py`)
- The `rocprof-compute` CLI executable is in `bin/` → goes to `_run` component
  (explicit `include = ["bin/**", "share/rocprofiler-compute/**"]`).
- Before: `test` had no extends, bare `test` = catch-all, so `_test` also
  had `bin/rocprof-compute`. Test infra fetched `_lib` + `_test` and found it.
- After: `test` extends the chain, `run` already claimed it, `_test` is empty.
- Fix: `argv.append("rocprofiler-compute_run")` in install script.
- Why not descriptor fix: the executable genuinely belongs in `_run` (it's a
  CLI tool, not a test binary). The install script just needs to fetch it.
- CI failure confirmed: `FileNotFoundError: ... 'rocprof-compute'` in
  [job 66104473155](https://github.com/ROCm/TheRock/actions/runs/22782491222/job/66104473155).

## Next Steps

1. [ ] Wait for CI results on PR #3830 (structure tests + functional tests)
2. [ ] Rebase onto main (has mxDataGenerator fix from 723748cd) if needed
3. [ ] Check if `ci_summary` jobs need updating to include validation jobs in dependency/result checks
4. [ ] Verify PR #3773 CI results (exclude-based fix for mxDataGenerator)
5. [ ] Review PR #3793 findings with author (hipdnn fix unnecessary)
6. [ ] Target-specific content validation test (approach 4)
7. [ ] Audit bare `[components.run."..."]` entries across all descriptors
       (catch-all steals from dev/test — see run warning in artifact_builder.py)
8. [ ] Fix pre-existing `_format_component_overlaps` return type annotation on main
       (`-> str` should be `-> tuple[int, str]`)

**Branches:**
- `artifact-overlap-testing-2`: structure tests + CI workflow (merged as PR #3802)
- `users/scotttodd/artifact-overlap-fixes`: test extends doc + descriptor fixes + docs + CI wiring

**PRs:**
- https://github.com/ROCm/TheRock/pull/3802 (structure tests + CI workflow) — **merged**
- https://github.com/ROCm/TheRock/pull/3830 (test extends doc + descriptor fixes + CI wiring) — **draft, awaiting CI**
