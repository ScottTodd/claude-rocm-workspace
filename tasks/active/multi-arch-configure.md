---
repositories:
  - therock
---

# Multi-Arch Configure: Source-Aware CI Configuration

- **Status:** Not started (design phase)
- **Priority:** P1 (High)
- **Started:** 2026-03-11
- **Target:** TBD

## Overview

Create a new `configure_multi_arch_ci.py` script that replaces the
multi-arch codepath in `configure_ci.py`. The core idea: "Configure CI"
is a **sequence of data transformations**. Each transformation takes
structured input, produces structured output, and is independently testable.

This replaces the current approach where `configure_ci.py` mixes input
parsing, trigger dispatch, family selection, matrix expansion, test
decisions, and output formatting in a 777-line script with a 295-line
monolithic function.

## Goals

- [ ] New script `configure_multi_arch_ci.py` with a pipeline architecture
- [ ] Each transformation step is a pure function with typed inputs/outputs
- [ ] Source-set-aware stage selection (changed files → stages to rebuild)
- [ ] Test selection driven by which stages rebuilt
- [ ] Wire into multi-arch CI workflows
- [ ] High test coverage from the start (>90%)
- [ ] Deprecation path for the `if multi_arch:` branch in `configure_ci.py`

## Design: Pipeline of Data Transformations

### Mental Model

```
Inputs (environment)         Source Config (code/data)         Outputs (GITHUB_OUTPUT)
─────────────────────        ────────────────────────         ─────────────────────────
• GITHUB_EVENT_NAME          • amdgpu_family_matrix.py        • linux_variants (JSON)
• PR_LABELS                  • BUILD_TOPOLOGY.toml            • windows_variants (JSON)
• BASE_REF                   • skip patterns                  • prebuilt_stages
• INPUT_*_AMDGPU_FAMILIES    • trigger type defaults          • rebuild_stages
• *_TEST_LABELS              • test_matrix                    • test_labels (JSON)
• BRANCH_NAME                                                 • enable_build_jobs
• BUILD_VARIANT                                               • test_type
```

The script is a pipeline of pure transformations between these:

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  1. Gather   │───>│  2. Select   │───>│  3. Decide   │───>│  4. Expand   │───>│  5. Format   │
│    Inputs    │    │   Targets    │    │    Stages    │    │    Matrix    │    │   Outputs    │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
  env vars →          trigger type →      changed files →     families ×          JSON arrays →
  CIInputs            families +          stages to            variants →          GITHUB_OUTPUT
                      labels              rebuild/prebuilt     MatrixEntry[]       + step summary
```

### Step 1: Gather Inputs → `CIInputs`

Parse environment variables and PR context into a typed dataclass. This is
the only step that touches `os.environ`. Everything downstream is pure.

```python
@dataclass(frozen=True)
class CIInputs:
    """All external inputs to the CI configuration pipeline."""
    event_name: str                    # push, pull_request, schedule, workflow_dispatch
    branch_name: str
    base_ref: str                      # For git diff (PR base, or HEAD^1)
    build_variant: str                 # release, asan, tsan
    pr_labels: list[str]               # Parsed from PR_LABELS JSON
    # Per-platform workflow_dispatch overrides
    linux_amdgpu_families: str         # Raw comma-separated input
    windows_amdgpu_families: str
    linux_test_labels: str
    windows_test_labels: str
    additional_label_options: list[str]
    # Prebuilt configuration (from workflow_dispatch)
    prebuilt_stages: str               # Comma-separated stage names
    baseline_run_id: str

    @staticmethod
    def from_environ() -> "CIInputs":
        """Parse from environment variables. Only place os.environ is read."""
        ...

    @property
    def is_pull_request(self) -> bool: ...
    @property
    def is_push(self) -> bool: ...
    @property
    def is_schedule(self) -> bool: ...
    @property
    def is_workflow_dispatch(self) -> bool: ...
    @property
    def is_long_lived_branch(self) -> bool: ...
```

**Source config:** None — this is pure environment parsing.

**Testability:** Construct `CIInputs` directly in tests. No env var mocking needed
downstream.

### Step 2: Select Targets → `TargetSelection`

Given trigger type + inputs, determine which GPU families to build/test
on each platform.

```python
@dataclass(frozen=True)
class TargetSelection:
    """Which GPU families were selected and why."""
    linux_families: list[str]     # e.g. ["gfx94x", "gfx110x", "gfx1151", "gfx120x"]
    windows_families: list[str]
    test_names: list[str]         # Explicitly requested test names (from labels)
    enable_build_jobs: bool       # False only for docs-only / skip-ci
    skip_reason: str | None       # Why builds disabled, if applicable

def select_targets(inputs: CIInputs) -> TargetSelection:
    """Determine target families based on trigger type and inputs."""
    ...
```

**Source config:** `amdgpu_family_matrix.py` (family definitions, trigger-type
grouping), `configure_ci_path_filters.py` (skip patterns for `enable_build_jobs`).

**Testability:** Pure function of `CIInputs`. Test each trigger type path
independently. Test label parsing (gfx labels, test labels, skip-ci,
run-all-archs-ci) with unit tests.

**What this replaces:** The trigger-type dispatch logic currently spread
across `matrix_generator` lines 270-465.

### Step 3: Decide Stages → `StageDecisions`

Given changed files and topology, determine which stages need rebuilding
vs. using prebuilt artifacts.

```python
@dataclass(frozen=True)
class StageDecision:
    action: Literal["rebuild", "prebuilt", "skip"]
    reason: str  # Human-readable explanation

@dataclass(frozen=True)
class StageDecisions:
    """Per-stage build/prebuilt/skip decisions."""
    decisions: dict[str, StageDecision]  # stage_name → decision
    test_type: str                       # "smoke" or "full"
    test_type_reason: str

    @property
    def prebuilt_stages(self) -> list[str]: ...
    @property
    def rebuild_stages(self) -> list[str]: ...

def decide_stages(
    inputs: CIInputs,
    targets: TargetSelection,
    topology: BuildTopology,
    changed_files: list[str] | None,
) -> StageDecisions:
    """Determine per-stage rebuild/prebuilt decisions."""
    ...
```

**Source config:** `BUILD_TOPOLOGY.toml` (source_sets → artifact_groups →
build_stages), submodule paths.

**Algorithm:**
1. If `inputs.prebuilt_stages` explicitly set (workflow_dispatch) → use those
2. If schedule → rebuild all
3. Classify changed files:
   - Inside a submodule → map to source_sets → artifact_groups → stages
   - Non-submodule, non-skippable → infra change → rebuild all
   - Skippable (docs, .md) → ignore
4. Propagate downstream: if stage X rebuilds, all stages that depend on
   X's artifact groups must also rebuild
5. Everything else → prebuilt (if baseline available) or rebuild (if not)

**Test type decision:**
- Schedule → full
- Test labels specified → full
- Submodule changed → full
- Otherwise → smoke

**Testability:** Pure function. Build `BuildTopology` from test fixtures.
Provide fake `changed_files` lists. Verify stage decisions without
touching git or the filesystem.

**What this replaces:** The binary `is_ci_run_required()` check and the
`test_type` logic in `main()` lines 637-677. Also provides the stage-level
intelligence that doesn't exist in the current script at all.

### Step 4: Expand Matrix → `list[MatrixEntry]`

Given families, build variant, and stage decisions, produce the GitHub
Actions matrix JSON.

```python
@dataclass(frozen=True)
class MatrixEntry:
    """One row of the GitHub Actions matrix."""
    matrix_per_family_json: str    # JSON array of per-family info
    dist_amdgpu_families: str      # Semicolon-separated
    artifact_group: str
    build_variant_label: str
    build_variant_suffix: str
    build_variant_cmake_preset: str
    expect_failure: bool
    build_pytorch: bool

def expand_matrix(
    families: list[str],
    platform: str,
    build_variant: str,
    lookup_matrix: dict,
) -> list[MatrixEntry]:
    """Expand families into matrix entries for one platform."""
    ...
```

**Source config:** `amdgpu_family_matrix.py` (platform info per family,
build variant configs).

**Testability:** Pure function. No environment, no git.

**What this replaces:** `generate_multi_arch_matrix()`.

### Step 5: Format Outputs

Write results to `GITHUB_OUTPUT` and `GITHUB_STEP_SUMMARY`. This is the
only step with side effects.

```python
@dataclass
class CIOutputs:
    """All outputs from the CI configuration pipeline."""
    linux_variants: list[MatrixEntry]
    windows_variants: list[MatrixEntry]
    linux_test_labels: list[str]
    windows_test_labels: list[str]
    enable_build_jobs: bool
    test_type: str
    # Stage decisions (new for multi-arch)
    linux_prebuilt_stages: str       # Comma-separated
    linux_rebuild_stages: str
    windows_prebuilt_stages: str
    windows_rebuild_stages: str

def write_outputs(outputs: CIOutputs):
    """Write to GITHUB_OUTPUT and GITHUB_STEP_SUMMARY."""
    ...

def format_summary(outputs: CIOutputs) -> str:
    """Generate human-readable markdown summary. Pure, testable."""
    ...
```

**Testability:** `format_summary` is pure. `write_outputs` is thin enough
to not need much testing (or mock the file writes).

### Orchestration

```python
def configure(inputs: CIInputs) -> CIOutputs:
    """Main pipeline. Each step feeds the next."""
    targets = select_targets(inputs)

    topology = load_topology()
    changed_files = get_git_modified_paths(inputs.base_ref)

    stage_decisions = decide_stages(inputs, targets, topology, changed_files)

    linux_matrix = expand_matrix(
        targets.linux_families, "linux", inputs.build_variant, ...
    )
    windows_matrix = expand_matrix(
        targets.windows_families, "windows", inputs.build_variant, ...
    )

    return CIOutputs(
        linux_variants=linux_matrix,
        windows_variants=windows_matrix,
        linux_test_labels=targets.test_names,
        windows_test_labels=targets.test_names,
        enable_build_jobs=targets.enable_build_jobs,
        test_type=stage_decisions.test_type,
        linux_prebuilt_stages=...,
        ...
    )

def main():
    inputs = CIInputs.from_environ()
    outputs = configure(inputs)
    write_outputs(outputs)
```

The `configure()` function is fully testable end-to-end by constructing
a `CIInputs` and asserting on the returned `CIOutputs`.

### Why This Architecture

**Adding a new behavior = adding/modifying one step.** Examples:
- "Skip CI for docs-only PRs" → change in `select_targets`
- "New GPU family" → data change in `amdgpu_family_matrix.py`, nothing
  in the pipeline
- "Per-stage prebuilt decisions" → change in `decide_stages`
- "New output field" → add to `CIOutputs` + `write_outputs`
- "New PR label" → add to `select_targets` label parsing

**Each step is testable in isolation.** Construct the input dataclass,
call the function, assert on the output dataclass. No environment variable
mocking, no git operations, no file I/O (except Step 1 and Step 5).

**Data flows in one direction.** No step reaches back to modify a prior
step's output. `format_variants` (currently a nested function inside
`main()`) becomes `format_summary`, a standalone pure function.

## Implementation Plan

### Phase 0: Shared Utilities

Extract from `configure_ci.py` the pieces both scripts need:
- Family selection by trigger type (already in `amdgpu_family_matrix.py`)
- Label parsing (`get_pr_labels`, `filter_known_names`)
- Path filtering (already in `configure_ci_path_filters.py`)
- `github_actions_utils` (already separate)

Evaluate: should label parsing move to a small shared module, or just
be reimplemented in the new script? If it's <50 lines, reimplementing
may be cleaner than introducing a shared module for legacy code.

### Phase 1: Scaffold + Steps 1, 2, 4, 5

Create the script with the pipeline skeleton. Steps 1/2/4/5 reproduce
the current `if multi_arch:` behavior without source-set awareness.
Step 3 returns "rebuild all" (matching current behavior).

Wire into `setup.yml` behind `MULTI_ARCH=true`. Run configure_ci.py
for single-arch, configure_multi_arch_ci.py for multi-arch.

Deliverable: multi-arch CI produces identical matrix output as before.

### Phase 2: Step 3 (Source-Set-Aware Stage Decisions)

Implement `decide_stages` with BUILD_TOPOLOGY.toml parsing:
- Source set → artifact group → stage mapping
- Downstream propagation through stage DAG
- Integration with `prebuilt_stages`/`baseline_run_id` outputs

Deliverable: for PRs, the script outputs which stages to rebuild vs.
prebuilt. Initially advisory-only (logged in step summary but not
plumbed to skip stages) until validated.

### Phase 3: End-to-End Integration

Connect stage decisions to the multi-arch-prebuilt workflow plumbing:
- `prebuilt_stages` output feeds `multi_arch_ci_linux.yml` copy job
- `rebuild_stages` output gates stage jobs
- Automated baseline run selection (or manual via workflow_dispatch)

### Phase 4: Test Selection

Map rebuilt stages → test suites. This requires either:
- Adding artifact_group → test mapping to BUILD_TOPOLOGY.toml, or
- Mapping test_matrix entries to stages via a new config

## Open Questions

### Q1: Topology loading
`configure_stage.py` already parses BUILD_TOPOLOGY.toml. Should we import
its parsing logic, or write a lighter-weight parser that only extracts
source_sets, artifact_groups, and build_stages? The configure_stage.py
parser is oriented around generating CMake args, which is more than we need.

### Q2: Granularity of rocm-systems
`rocm-systems` is a monorepo containing CLR, profiler, runtime, etc.
A change to any file in rocm-systems triggers rebuilds of nearly every
stage. Could add sub-source-sets (e.g. `rocm-systems/clr/` → source_set
`clr`) but that requires BUILD_TOPOLOGY.toml changes. Defer for now?

### Q3: Test label → stage mapping
The current `test_matrix` in `fetch_test_configurations.py` has test
labels like "hip-tests", "rocprim", etc. These correspond roughly to
artifact groups but there's no formal mapping. Where should this live?

### Q4: setup.yml dispatch
When `MULTI_ARCH=true`, should setup.yml call the new script instead of
configure_ci.py? Or should we have a thin dispatcher that routes based on
mode? Simplest: just call the right script based on an `if:`.

### Q5: Per-platform stage decisions
Stage lists might differ by platform (e.g. `media-libs` disabled on Windows).
Should `decide_stages` be called once with a platform parameter, or once
globally? The topology already has `disable_platforms` on source_sets.

## Investigation Notes

### 2026-03-11 - Task Created

Analyzed the current codebase:

**configure_ci.py structure (777 lines):**
- `__main__` block (lines 726-767): Reads env vars into `base_args` dict
- `main()` (lines 568-723): Orchestration, test_type logic, output writing
- `matrix_generator()` (lines 255-560): Monolithic — trigger dispatch,
  family selection, label parsing, matrix expansion all interleaved
- `generate_multi_arch_matrix()` (lines 138-237): Groups families by variant
- Helper functions: `get_pr_labels`, `filter_known_names`, etc.

**Key coupling problems:**
- `base_args` is an untyped dict threaded through 4 functions with 12+ fields
- `matrix_generator` handles both single-arch and multi-arch via an `if`
- Test type decision happens in `main()` after matrix generation, but needs
  information from step 2 (which submodules changed)
- `format_variants` is nested inside `main()` — untestable

**BUILD_TOPOLOGY.toml mapping chain:**
- 12 source_sets → submodules
- 17 artifact_groups → source_sets (e.g. math-libs → [rocm-libraries, rocm-systems, math-libs])
- 10 build_stages → artifact_groups
- Stage DAG implicit through artifact_group_deps

**rocm-systems fan-out:** Nearly every artifact group references
`rocm-systems` as a source_set. This means a change to any file in the
rocm-systems submodule triggers rebuilds of: compiler-runtime, math-libs,
comm-libs, profiler-apps, media-libs, etc. This is correct but coarse.

## Decisions & Trade-offs

- **Pipeline of pure transformations**: Each step takes typed input, produces
  typed output. Side effects only at the edges (env read, output write).
- **Fork over extend**: Multi-arch needs stage decisions, different matrix
  fields, and will grow test selection. Bolting these onto the existing
  295-line function would make both harder to maintain.
- **Topology-driven**: All stage/source_set logic reads from BUILD_TOPOLOGY.toml.
  No hardcoded stage names in Python.
- **Dataclasses over dicts**: `CIInputs`, `TargetSelection`, `StageDecisions`,
  `MatrixEntry`, `CIOutputs` — each step's interface is explicit.

## Blockers & Issues

### Dependencies
- `multi-arch-prebuilt` PR #3856 (workflow wiring) — provides the
  `prebuilt_stages` input that this script will populate
- BUILD_TOPOLOGY.toml source_sets — already defined, may need refinement

## Resources & References

- [Issue #3399](https://github.com/ROCm/TheRock/issues/3399) — stage-aware prebuilt artifacts
- [BUILD_TOPOLOGY.toml](../TheRock/BUILD_TOPOLOGY.toml)
- [configure_ci.py](../TheRock/build_tools/github_actions/configure_ci.py)
- [configure_ci_path_filters.py](../TheRock/build_tools/github_actions/configure_ci_path_filters.py)
- [amdgpu_family_matrix.py](../TheRock/build_tools/github_actions/amdgpu_family_matrix.py)
- [configure_stage.py](../TheRock/build_tools/configure_stage.py)
- [fetch_test_configurations.py](../TheRock/build_tools/github_actions/fetch_test_configurations.py)
- [multi-arch-prebuilt task](multi-arch-prebuilt.md)
- [configure-ci-refactor task](configure-ci-refactor.md)

## Next Steps

1. [ ] Discuss design — settle open questions, validate pipeline approach
2. [ ] Phase 0: Evaluate shared utilities (extract vs. reimplement)
3. [ ] Phase 1: Scaffold with Steps 1/2/4/5, matching current behavior
4. [ ] Phase 1: Wire into setup.yml, validate identical output
5. [ ] Phase 2: Implement Step 3 (topology parsing, source-set analysis)
6. [ ] Phase 2: Validate stage decisions against real PRs (advisory mode)
7. [ ] Phase 3: Connect to multi-arch-prebuilt workflow plumbing
8. [ ] Phase 4: Test selection from rebuilt stages

## Branches

_(none yet)_

## Completion Notes

<!-- Fill this in when task is done -->
