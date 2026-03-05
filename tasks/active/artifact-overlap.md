---
repositories:
  - therock
---

# Artifact Overlap Testing & Fixes

- **Status:** In progress
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

- [x] Cross-artifact collision test (`tests/test_artifact_collisions.py`)
- [x] Basedir overlap unit test (`build_tools/tests/artifact_descriptor_overlap_test.py`)
- [ ] Within-artifact component collision test
- [ ] Fix mxDataGenerator overlap (blas vs support) — PR #3773
- [ ] Fix miopen within-artifact overlap — PR #3793 (external)
- [ ] CI workflow integration (`test_artifacts_structure.yml`)
- [ ] Documentation update (`docs/development/artifacts.md`)
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

**Approach 2 — Archive content collision test** (branch `artifact-overlap-testing-2`)

- `tests/test_artifact_collisions.py`
- Scans actual artifact archives (without extracting) and checks for
  flattened path collisions across different artifact names.
- Catches mxDataGenerator and any other spillover-based overlap.
- Tested against:

  | Artifact set | Archives | Collisions |
  |---|---|---|
  | Windows gfx110X-all (classic) | ~100 | 36 (all mxDataGenerator) |
  | Linux multi-arch, 5 families (classic) | ~500 | 36 (same, only in `_generic`) |
  | Linux kpack (generic + gfx942) | ~207 | 36 (same pattern) |

- Key finding: collisions are uniform across GPU families and artifact
  formats. Driven entirely by descriptor config, not build variation.

**Approach 3 — Within-artifact component collision test** (not yet implemented)

- Same archive scanning approach but checks for files appearing in
  multiple components of the SAME artifact.
- Would catch the miopen `bin/miopen_gtest` duplication.
- Components are supposed to be disjoint (enforced by `transitive_relpaths`
  in the scanner), but `test` has no extends chain so it bypasses this.

**Approach 4 — Target-specific content validation** (not yet implemented)

- Per-target archives (e.g., `blas_lib_gfx942`) should only contain
  target-namespaced files (`.kpack`, `.co`, `.hsaco`, `.dat`, `.model`).
- Validated manually: blas_lib_gfx942 has 1358 files (651 .dat, 650 .co,
  56 .hsaco, 1 .kpack). No headers, cmake configs, or shared libs.

### WS3: CI Integration

Plan: new reusable workflow `test_artifacts_structure.yml`

- CPU-only runner (no GPU needed)
- Fetches archives via `fetch_artifacts.py --no-extract`
- Runs `pytest tests/test_artifact_structure.py` (renamed from
  `test_artifact_collisions.py` to reflect broader scope)
- Called from three places in parallel with existing test jobs:

  | Workflow | New job | Parallel to |
  |---|---|---|
  | `ci_linux.yml` | `validate_linux_artifacts` | `test_linux_artifacts` |
  | `ci_windows.yml` | `validate_windows_artifacts` | `test_windows_artifacts` |
  | `multi_arch_ci_linux.yml` | `validate_multi_arch_artifacts` | `test_artifacts_per_family` |

### WS4: Documentation

`docs/development/artifacts.md` is missing critical information:

- Component inheritance chain (`lib -> run -> dbg -> dev -> doc`)
- Default patterns per component type
- The catch-all behavior (empty `includes` = match everything)
- How `test` stands alone (no extends, no transitive_relpaths sharing)
- `include` augments defaults rather than replacing them
- Auto-creation of intermediate components
- BUILD_DEPS spillover and mitigation strategies

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

## Next Steps

1. [ ] Verify PR #3773 CI results (exclude-based fix for mxDataGenerator)
2. [ ] Implement within-artifact component collision test (approach 3)
3. [ ] Rename test file to `test_artifact_structure.py`, add all test cases
4. [ ] Draft `test_artifacts_structure.yml` workflow
5. [ ] Update `docs/development/artifacts.md` with inheritance docs
6. [ ] Review PR #3793 findings with author (hipdnn fix unnecessary)
