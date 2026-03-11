---
repositories:
  - therock
---

# Multi-Arch Configure: Source-Aware CI Configuration

- **Status:** Not started
- **Priority:** P1 (High)
- **Started:** 2026-03-11
- **Target:** TBD

## Overview

Fork `configure_ci.py` into a new script purpose-built for multi-arch CI.
The current `configure_ci.py` grew organically for the single-arch pipeline
and has accumulated technical debt (295-line `matrix_generator`, untyped
`base_args` dict, 63% test coverage, multi-arch bolted on as an `if
multi_arch:` branch). Rather than continuing to extend it, we create a new
script designed from the ground up for multi-arch requirements:

1. **Source-set-aware stage selection** — map modified files to
   BUILD_TOPOLOGY.toml source sets → artifact groups → stages, to decide
   which stages need rebuilding vs. using prebuilt artifacts.
2. **Test selection** — determine which test suites to run based on which
   stages were rebuilt (don't test what didn't change).
3. **Clean data model** — dataclasses instead of untyped dicts, clear
   separation of concerns.

## Goals

- [ ] New script `configure_multi_arch_ci.py` that outputs the multi-arch
      matrix and per-stage build/skip decisions
- [ ] Source-set-aware stage selection: given changed files, determine which
      stages are affected and which can use prebuilts
- [ ] Test selection: given rebuilt stages, determine which tests to run
- [ ] Wire into `multi_arch_ci.yml` → `setup.yml` (or equivalent)
- [ ] High test coverage from the start (>90%)
- [ ] Deprecation path for the `multi_arch` codepath in `configure_ci.py`

## Context

### Background

`configure_ci.py` serves two masters: single-arch CI (`ci.yml`) and
multi-arch CI (`multi_arch_ci.yml`). Multi-arch was added by bolting
`generate_multi_arch_matrix()` onto the existing `matrix_generator()` via
an `if multi_arch:` branch. This approach has limits:

- **No source-set awareness.** The script treats CI as all-or-nothing — it
  can skip CI entirely for docs-only changes (`configure_ci_path_filters.py`)
  but can't say "only math-libs changed, skip foundation and compiler-runtime."
- **Test selection is coarse.** Tests are selected by PR labels or
  `workflow_dispatch` inputs, not by what actually changed.
- **The data model is shared.** Multi-arch needs different matrix fields
  (`matrix_per_family_json`, `dist_amdgpu_families`) than single-arch
  (`family`, `artifact_group`). Sharing `matrix_generator` forces both to
  carry each other's concerns.

The `multi-arch-prebuilt` task (Phase 1 complete) added `prebuilt_stages`
and `baseline_run_id` workflow inputs. This task provides the intelligence
to populate those inputs automatically.

### What Already Exists

**BUILD_TOPOLOGY.toml** already defines the full mapping:
- `source_sets.*` → submodules (e.g., `rocm-libraries` → `["rocm-libraries"]`)
- `artifact_groups.*` → `source_sets` (e.g., `math-libs` → `["rocm-libraries", "rocm-systems", "math-libs"]`)
- `build_stages.*` → `artifact_groups` (e.g., `math-libs` → `["math-libs", "ml-libs"]`)

**`configure_ci_path_filters.py`** already has:
- `get_git_modified_paths(base_ref)` — git diff file list
- `get_git_submodule_paths()` — submodule listing
- Binary `is_ci_run_required()` — but no stage-level granularity

**`configure_stage.py`** already parses BUILD_TOPOLOGY.toml for stage→feature
mapping and has helpers for reading the topology.

### Build Stage DAG (Linux)

```
foundation (generic)
  └─> compiler-runtime (generic)
        ├─> math-libs (per-arch)
        ├─> comm-libs (per-arch)
        ├─> debug-tools (generic)
        ├─> dctools-core (generic)
        ├─> iree-compiler (generic)
        ├─> profiler-apps (generic)
        └─> media-libs (generic)
              └─> fusilli-libs (generic, needs math-libs + iree-compiler)
```

### Source Set → Stage Mapping

A file change triggers a rebuild of a stage if ANY of these conditions hold:
1. The file is inside a submodule that belongs to a source set
2. That source set is referenced by an artifact group
3. That artifact group is in the stage's `artifact_groups` list

Example: changing `rocm-libraries/rocBLAS/...` →
source_set `rocm-libraries` → artifact_group `math-libs` → stage `math-libs`

But also: changing `rocm-systems/clr/...` →
source_set `rocm-systems` → artifact_groups `core-runtime`, `hip-runtime`,
`opencl-runtime`, `math-libs`, `comm-libs`, etc. → stages `compiler-runtime`,
`math-libs`, `comm-libs`, etc.

TheRock's own build files (CMakeLists.txt, cmake/, build_tools/, etc.)
should trigger a full rebuild since they affect all stages.

### Directories/Files Involved

```
# New script (to create)
build_tools/github_actions/configure_multi_arch_ci.py
build_tools/github_actions/tests/configure_multi_arch_ci_test.py

# Existing (to read, possibly extend)
build_tools/github_actions/configure_ci.py           # Fork source
build_tools/github_actions/configure_ci_path_filters.py  # Reuse git helpers
build_tools/github_actions/amdgpu_family_matrix.py   # Reuse family definitions
build_tools/github_actions/fetch_test_configurations.py  # Reuse test configs
build_tools/configure_stage.py                        # Topology parsing
BUILD_TOPOLOGY.toml                                   # Stage/source_set definitions

# Workflows to update
.github/workflows/multi_arch_ci.yml
.github/workflows/setup.yml
```

### Related Work

- `multi-arch-prebuilt` — Phase 1 (copy plumbing) complete; this task
  provides Phase 3 (source-set-aware stage selection)
- `configure-ci-refactor` — identified issues with the current script;
  this task is the "clean break" alternative for multi-arch
- `configure_ci_path_filters.py` — binary CI skip logic; we'll extend
  the concept to per-stage granularity

## Design

### High-Level Architecture

```
configure_multi_arch_ci.py
  ├── Data model (dataclasses)
  │   ├── CIConfig — top-level config (event type, inputs, labels)
  │   ├── StageDecision — per-stage build/skip with reason
  │   └── MatrixEntry — per-variant matrix row
  ├── Source analysis
  │   ├── get_modified_source_sets(changed_files, topology) → set[str]
  │   ├── get_affected_stages(source_sets, topology) → set[str]
  │   └── propagate_rebuilds(affected_stages, topology) → set[str]
  ├── Matrix generation
  │   ├── select_families(config) → list[FamilyInfo]
  │   ├── generate_matrix(families, config) → list[MatrixEntry]
  │   └── generate_stage_decisions(affected, all_stages) → dict[str, StageDecision]
  └── Output
      ├── write_github_outputs(matrix, decisions)
      └── write_step_summary(matrix, decisions)
```

### Key Design Decisions

**1. Fork, don't extend.** Multi-arch and single-arch pipelines have
different enough requirements that sharing `matrix_generator` creates
more coupling than it saves. The new script imports shared utilities
(family matrix, path filters, topology parsing) but owns its own
orchestration logic.

**2. BUILD_TOPOLOGY.toml is the source of truth.** Stage DAG, source
sets, and artifact group mappings all come from the topology file.
No hardcoded stage lists in Python.

**3. Rebuild propagation follows the DAG.** If `compiler-runtime` needs
rebuilding, all downstream stages (math-libs, comm-libs, etc.) must also
rebuild. The propagation is transitive through the stage dependency graph.

**4. TheRock-internal changes trigger full rebuild.** Changes to
CMakeLists.txt, cmake/, build_tools/, .github/workflows/ etc. (anything
not inside a submodule) conservatively trigger all stages. This can be
refined later.

**5. Labels and workflow_dispatch override automation.** PR labels like
`ci:rebuild-all` or `ci:prebuilt-stages=foundation,compiler-runtime`
take precedence over source-set analysis. `workflow_dispatch` inputs
provide explicit control for manual runs.

### Source-Set Analysis Algorithm

```python
def determine_stage_decisions(changed_files, topology, labels):
    # 1. Check for override labels
    if "ci:rebuild-all" in labels:
        return {stage: REBUILD for stage in all_stages}

    # 2. Classify changed files
    submodule_paths = get_git_submodule_paths()
    infra_changes = False
    modified_source_sets = set()

    for f in changed_files:
        submodule = find_containing_submodule(f, submodule_paths)
        if submodule is None:
            # File is in TheRock itself (build infra, cmake, etc.)
            if not is_skippable(f):  # docs, .md, etc.
                infra_changes = True
        else:
            # File is in a submodule — find its source sets
            for ss in topology.source_sets.values():
                if submodule in ss.submodules:
                    modified_source_sets.add(ss.name)

    # 3. If infra changed, rebuild everything
    if infra_changes:
        return {stage: REBUILD for stage in all_stages}

    # 4. Map source sets → artifact groups → stages
    affected_stages = set()
    for ag in topology.artifact_groups.values():
        if modified_source_sets & set(ag.source_sets):
            for stage in topology.build_stages.values():
                if ag.name in stage.artifact_groups:
                    affected_stages.add(stage.name)

    # 5. Propagate downstream (if a stage rebuilds, dependents must too)
    affected_stages = propagate_downstream(affected_stages, topology)

    # 6. Generate decisions
    return {
        stage: REBUILD if stage in affected_stages else PREBUILT
        for stage in all_stages
    }
```

### Test Selection

When only specific stages rebuild, we only need to run tests for the
affected artifact groups. The mapping:

- Stage `math-libs` rebuilt → run tests tagged with `math-libs`, `ml-libs`
  artifact groups (rocBLAS, hipBLAS, MIOpen, etc.)
- Stage `compiler-runtime` rebuilt → run tests for `core-runtime`,
  `hip-runtime`, etc.

This requires BUILD_TOPOLOGY.toml to eventually map test suites to
artifact groups (or we use the existing `fetch_test_configurations.py`
labels and create a mapping).

### Output Format

The script outputs to `GITHUB_OUTPUT`:

```
# Matrix (same format as current multi-arch output)
linux_variants=<JSON array of MatrixEntry>
windows_variants=<JSON array of MatrixEntry>

# Stage decisions (new)
linux_prebuilt_stages=foundation,compiler-runtime
linux_rebuild_stages=math-libs,comm-libs,debug-tools,...
windows_prebuilt_stages=foundation,compiler-runtime
windows_rebuild_stages=math-libs,comm-libs

# Test selection (new)
linux_test_labels=<JSON array of test labels>
windows_test_labels=<JSON array>

# Existing
enable_build_jobs=true
test_type=smoke
```

The `prebuilt_stages` output feeds directly into the multi-arch workflow's
`prebuilt_stages` input (from the `multi-arch-prebuilt` task).

## Open Questions

### Q1: Baseline run selection
Source-set analysis tells us WHICH stages to skip, but we still need a
baseline run_id to copy artifacts from. This is the `multi-arch-prebuilt`
Phase 2 problem. For now, this script outputs the stage decisions; the
baseline run lookup is a separate concern.

### Q2: Granularity of "infra changes"
Currently proposed: any non-submodule, non-skippable change = full rebuild.
Could refine: changes to `build_tools/github_actions/` only affect CI
plumbing, not the actual build. Changes to `cmake/` affect all stages.
Changes to `core/CMakeLists.txt` affect stages defined there.

### Q3: Per-arch stage decisions
If rocBLAS changes only affect gfx94X (e.g., a kernel tuning file), could
we prebuilt math-libs for gfx110X while rebuilding for gfx94X? This is
per-arch granularity within a per-arch stage. Probably not worth the
complexity initially.

### Q4: Shared code with configure_ci.py
Family selection, label parsing, and matrix field generation are shared
concerns. Options: (a) extract shared code to a common module, (b)
duplicate and simplify. Prefer (a) if the shared code is stable.

### Q5: When to wire in
This script needs to be wired into `setup.yml` or a new setup workflow.
The multi-arch CI currently goes through the same `setup.yml` as single-arch
with `MULTI_ARCH=true`. Should multi-arch get its own setup, or should
`setup.yml` dispatch to the right configure script based on `MULTI_ARCH`?

## Investigation Notes

### 2026-03-11 - Task Created

Analyzed the existing codebase to understand what we're working with:

**Current configure_ci.py (777 lines):**
- `matrix_generator()` (295 lines) — monolithic, handles all trigger types
  for both single-arch and multi-arch
- `generate_multi_arch_matrix()` (100 lines) — groups families by build
  variant, creates multi-arch matrix entries
- `main()` (145 lines) — orchestration, zero test coverage
- `base_args` — untyped dict with 12+ fields threaded through everything
- Multi-arch is an `if multi_arch:` branch inside `matrix_generator`

**BUILD_TOPOLOGY.toml has the full mapping chain:**
- 12 source_sets (base, compilers, rocm-systems, rocm-libraries, etc.)
- 17 artifact_groups with `source_sets` references
- 10 build_stages with `artifact_groups` references
- Stage DAG implicit through artifact group dependencies

**configure_ci_path_filters.py:**
- Has `get_git_modified_paths()` and `get_git_submodule_paths()` — reusable
- `is_ci_run_required()` — binary decision only, not stage-aware
- Skippable patterns (docs, .md, dockerfiles) — reusable

**Key insight:** The `rocm-systems` source set is referenced by nearly every
artifact group (core-runtime, hip-runtime, math-libs, comm-libs, etc.).
A change to rocm-systems triggers rebuilds of most stages. This is correct
because rocm-systems is a monorepo containing runtime, profiler, CLR, etc.
The granularity limitation is that we can't distinguish "changed CLR" from
"changed rocprofiler" within rocm-systems at the source_set level.

**Potential refinement:** Could add finer-grained source_sets that map to
subdirectories within rocm-systems (e.g., `rocm-systems/clr/` →
source_set `clr`). But this requires BUILD_TOPOLOGY.toml changes and is
a separate concern.

## Decisions & Trade-offs

- **Fork over refactor**: Multi-arch has different enough requirements that
  extending `configure_ci.py` further would increase coupling. The new
  script starts clean and shares utilities via imports.
- **Topology-driven over hardcoded**: All stage/source_set logic reads from
  BUILD_TOPOLOGY.toml. No hardcoded stage names in Python (except possibly
  for "all stages need rebuild" fallback).

## Blockers & Issues

### Dependencies
- `multi-arch-prebuilt` Phase 1 (PR #3801, merged) — copy subcommand exists
- `multi-arch-prebuilt` workflow wiring (PR #3856, draft) — prebuilt_stages
  input exists in workflows
- BUILD_TOPOLOGY.toml source_sets — already defined, may need refinement
  for finer granularity

## Resources & References

- [Issue #3399](https://github.com/ROCm/TheRock/issues/3399) — stage-aware prebuilt artifacts
- [BUILD_TOPOLOGY.toml](../TheRock/BUILD_TOPOLOGY.toml)
- [configure_ci.py](../TheRock/build_tools/github_actions/configure_ci.py)
- [configure_ci_path_filters.py](../TheRock/build_tools/github_actions/configure_ci_path_filters.py)
- [configure_stage.py](../TheRock/build_tools/configure_stage.py)
- [multi-arch-prebuilt task](multi-arch-prebuilt.md)
- [configure-ci-refactor task](configure-ci-refactor.md)

## Next Steps

1. [ ] Discuss design with Scott — validate fork approach, settle open questions
2. [ ] Extract shared utilities from configure_ci.py (family selection, label
       parsing) into a common module
3. [ ] Implement topology parsing for source_set → stage mapping
4. [ ] Implement source-set analysis (changed files → affected stages)
5. [ ] Implement rebuild propagation (affected stages → transitive closure)
6. [ ] Implement matrix generation (reusing family/variant logic)
7. [ ] Implement stage decision output (prebuilt_stages, rebuild_stages)
8. [ ] Wire into setup.yml / multi_arch_ci.yml
9. [ ] Test with real PRs (validate stage decisions against manual expectations)

## Branches

_(none yet)_

## Completion Notes

<!-- Fill this in when task is done -->
