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

## Feature Audit

Systematic review of every behavior in `configure_ci.py` and whether the
multi-arch fork needs it.

**Context:** `multi_arch_ci.yml` is about to replace `ci.yml` as *the* CI
workflow. All trigger types (push, pull_request, workflow_dispatch, schedule)
will be supported. `build_variant` is currently hardcoded to `"release"` but
other variants (ASAN, TSAN) may follow.

### DROP — not needed for multi-arch

| Feature | Lines | Why drop |
|---------|-------|----------|
| `determine_long_lived_branch` | 240-252 | Push = push. Same family set regardless of branch name. If certain branches shouldn't build certain families, handle via workflow `on.push.branches` filters, not runtime logic. |
| Single-arch matrix expansion | 467-556 | The new script IS multi-arch. No single-arch codepath. |
| `use_prebuilt_artifacts` boolean | 580-581, 749-753 | Replaced by per-stage `prebuilt_stages`. |
| `MULTI_ARCH` env var/flag | 774 | The new script is always multi-arch. No flag needed. |
| `test_runner:` kernel-specific runner override | 527-546 | Only used in single-arch expansion. If needed later, add as a proper step, not a mid-expansion mutation. |
| `additional_label_options` | 87-98, 521-526 | Only used for `test_runner:` labels. Goes with it. |
| ASAN `test-runs-on-sandbox` override | 548-554 | When ASAN is added to multi-arch, handle in variant config data, not as a runtime mutation. |
| Trigger type → family tier branching | 282-314, 415-443 | Simplify — see below. |

### SIMPLIFY — keep concept but redesign

| Feature | Current | Proposed |
|---------|---------|----------|
| **Family tier system** (presubmit/postsubmit/nightly) | Three tiers with trigger-type mappings. `determine_long_lived_branch` selects which tiers. PR labels can opt into higher tiers. | Single "default families" set for push and pull_request. Schedule gets all families. Workflow_dispatch selects from all known families. The tier *data* in `amdgpu_family_matrix.py` stays, but the selection logic simplifies: `push`/`pull_request` → presubmit+postsubmit, `schedule` → all, `workflow_dispatch` → explicit. |
| **`filter_known_names` validation** | Validates against trigger-type-specific subset, uses `assert`, generic `name_type`. | Validate against all known families. Raise proper exceptions. Separate functions for family vs test validation. |
| **Punctuation sanitization** (workflow_dispatch) | Replaces all punctuation with spaces. | Comma-split then strip. More explicit. |
| **Post-hoc matrix mutation** (lines 667-685) | `main()` mutates matrix rows after generation to clear `test-runs-on` based on `run-full-tests-only` and `nightly_check_only_for_family`. | Move into the matrix expansion step or test decision step — don't mutate after the fact. |

### KEEP — port to new script

| Feature | Lines | Notes |
|---------|-------|-------|
| **All trigger types** | throughout | push, pull_request, workflow_dispatch, schedule |
| **workflow_dispatch family + test label inputs** | 316-355 | Core functionality |
| **PR label: `skip-ci`** | 387-393 | Step 2 gate |
| **PR label: `run-all-archs-ci`** | 394-403 | Opt into all families |
| **PR label: `gfx*` opt-in** | 372-377 | Add specific families |
| **PR label: `test:*`** | 379-384 | Select specific tests, trigger full test mode |
| **`is_ci_run_required()` path filtering** | 651-660 | Step 2 gate for push/PR |
| **test_type: smoke vs full** | 637-686 | Submodule changed → full, test labels → full, schedule → full, otherwise → smoke |
| **Multi-arch matrix grouping** | 138-237 | One entry per build_variant with all families |
| **`expect_failure` / `expect_pytorch_failure`** | 223-224, 500-508 | Per-family/variant flags |
| **`build_pytorch` computation** | 507-508, 233 | Derived from expect_failure flags |
| **Step summary + GITHUB_OUTPUT** | 689-732 | Rewrite as standalone function |

### Per-family data flags (pass-through, not logic)

These are fields in `amdgpu_family_matrix.py` that flow through to
`matrix_per_family_json`. The new script doesn't need special logic for
most of them — they're data.

| Flag | Purpose | Needs logic? |
|------|---------|--------------|
| `sanity_check_only_for_family` | Limit test scope | No — data |
| `run-full-tests-only` | Only test when test_type=full | **Yes** — currently mutates matrix in main() |
| `nightly_check_only_for_family` | Force sanity-check on non-nightly | **Yes** — currently mutates matrix in main() |
| `bypass_tests_for_releases` | Skip tests for release builds | No — data |
| `test-runs-on` / multi-gpu / benchmark | Runner labels | No — data |
| `fetch-gfx-targets` | Per-target artifact fetching | No — data |

The two flags that need logic (`run-full-tests-only`,
`nightly_check_only_for_family`) currently live as post-hoc mutations in
`main()`. In the new script they belong in the test decision step.

### DEFER — not needed yet but design for

| Feature | When needed |
|---------|-------------|
| Non-release build variants (ASAN, TSAN) | When multi-arch gets variant workflows |
| `test_runner:` kernel-specific overrides | When multi-arch needs kernel-specific testing |

### Key simplification: push family selection

**Current:** Push to main → presubmit+postsubmit families. Push to other
branches → presubmit only. This is `determine_long_lived_branch`.

**Proposed:** Push → presubmit+postsubmit families, regardless of branch.
The postsubmit tier currently only adds gfx950. If you're pushing to
any branch that multi_arch_ci.yml triggers on, you want the same coverage.

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
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 1. Parse │───>│ 2. Check │───>│ 3. Pick  │───>│ 4. Stage │───>│ 5. Build │───>│ 6. Write │
│  Inputs  │    │  Skip CI │    │ Targets  │    │ Decisions│    │  Matrix  │    │ Outputs  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
 env vars →      skip-ci label,  trigger →       changed files   families ×      JSON →
 CIInputs        docs-only →     families +      → rebuild /     variants →      GITHUB_OUTPUT
                 early exit?     test names      prebuilt        MatrixEntry[]
```

**Step 2 is a gate.** If CI should be skipped (skip-ci label, docs-only
paths), the pipeline short-circuits: emit `enable_build_jobs=false`, empty
matrices, and a skip reason. Steps 3-6 don't run.

This is where the current code buries the `skip-ci` label check (inside
`matrix_generator`'s PR handler, line 387) and `is_ci_run_required()`
(inside `main()` at line 651, *after* matrix generation — wrong order).
Making it an explicit step means:
- One place for all "should we skip entirely?" logic
- All skip reasons (label, path filter, future heuristics) live together
- Steps 3-6 don't need to handle the "nothing to do" case

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

### Step 2: Check Skip CI → early exit or continue

Should we run CI at all? This is a gate — if the answer is no, we
short-circuit the pipeline and emit empty outputs.

```python
@dataclass(frozen=True)
class SkipDecision:
    """Whether to skip CI entirely."""
    skip: bool
    reason: str  # e.g. "skip-ci label", "only .md files changed", ""

def check_skip_ci(
    inputs: CIInputs,
    changed_files: list[str] | None,
) -> SkipDecision:
    """Check whether CI should be skipped entirely.

    Skip reasons:
    - 'skip-ci' PR label
    - Only skippable paths changed (docs, .md, .gitignore, etc.)
    - No files changed
    """
    ...
```

**Source config:** `configure_ci_path_filters.py` (skippable path patterns).

**Testability:** Pure function. Test with various combinations of labels
and file lists. Each skip reason is a distinct test case.

**What this replaces:** The `skip-ci` label check buried inside
`matrix_generator`'s PR handler (line 387) and `is_ci_run_required()`
called in `main()` after matrix generation (line 651).

### Step 3: Select Targets → `TargetSelection`

Given trigger type + inputs, determine which GPU families to build/test
on each platform.

```python
@dataclass(frozen=True)
class TargetSelection:
    """Which GPU families were selected and why."""
    linux_families: list[str]     # e.g. ["gfx94x", "gfx110x", "gfx1151", "gfx120x"]
    windows_families: list[str]
    test_names: list[str]         # Explicitly requested test names (from labels)

def select_targets(inputs: CIInputs) -> TargetSelection:
    """Determine target families based on trigger type and inputs."""
    ...
```

**Source config:** `amdgpu_family_matrix.py` (family definitions, trigger-type
grouping).

**Testability:** Pure function of `CIInputs`. Test each trigger type path
independently. Test label parsing (gfx labels, test labels,
run-all-archs-ci) with unit tests.

**What this replaces:** The trigger-type dispatch logic currently spread
across `matrix_generator` lines 270-465.

### Step 4: Decide Stages → `StageDecisions`

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

**What this replaces:** The `test_type` logic in `main()` lines 637-677.
Also provides the stage-level intelligence that doesn't exist in the
current script at all.

### Step 5: Expand Matrix → `list[MatrixEntry]`

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

### Step 6: Format Outputs

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
    changed_files = get_git_modified_paths(inputs.base_ref)

    # Step 2: Gate — should we skip CI entirely?
    skip = check_skip_ci(inputs, changed_files)
    if skip.skip:
        return CIOutputs.skipped(skip.reason)

    # Steps 3-5: Select targets, decide stages, expand matrix
    targets = select_targets(inputs)

    topology = load_topology()
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
        enable_build_jobs=True,
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
- "Skip CI for docs-only PRs" → add a check in `check_skip_ci`
- "New GPU family" → data change in `amdgpu_family_matrix.py`, nothing
  in the pipeline
- "Per-stage prebuilt decisions" → change in `decide_stages`
- "New output field" → add to `CIOutputs` + `write_outputs`
- "New PR label for target opt-in" → add to `select_targets` label parsing

**Each step is testable in isolation.** Construct the input dataclass,
call the function, assert on the output dataclass. No environment variable
mocking, no git operations, no file I/O (except Step 1 and Step 6).

**Data flows in one direction.** No step reaches back to modify a prior
step's output. The gate (Step 2) short-circuits cleanly instead of
clearing lists mid-computation. `format_variants` (currently a nested
function inside `main()`) becomes `format_summary`, a standalone pure
function.

## Implementation Plan

### Phase 1: Scaffold — dataclasses, pipeline shape, test patterns

Create the script with all pipeline steps defined but mostly stubbed.
The goal is to validate that the data flows cleanly between steps and
that every step is independently testable.

**Deliverables:**
- `configure_multi_arch_ci.py` with:
  - All dataclasses (`CIInputs`, `SkipDecision`, `TargetSelection`,
    `StageDecisions`, `MatrixEntry`, `CIOutputs`)
  - `configure()` orchestration function calling each step
  - Stub implementations that return hardcoded/trivial values
  - `CIInputs.from_environ()` and `write_outputs()` (the I/O edges)
- `tests/configure_multi_arch_ci_test.py` with:
  - Test for each step function showing the pattern (construct input
    dataclass → call function → assert on output dataclass)
  - At least one end-to-end test: construct `CIInputs` → call
    `configure()` → assert `CIOutputs` shape
- No workflow wiring yet — just the script and tests

**Why start here:** Establishes the architecture before filling in logic.
Makes it easy to review whether the step boundaries feel right. Tests
show exactly how each step is exercised.

### Phase 2: MVP logic — skip gate, target selection, matrix expansion

Fill in the real logic for Steps 2, 3, 5 (skip CI, select targets,
expand matrix). Step 4 (stage decisions) returns "rebuild all" for now.

**Step 2 (check_skip_ci):**
- `skip-ci` PR label
- `is_ci_run_required()` path filtering (reuse from `configure_ci_path_filters.py`)
- workflow_dispatch/schedule always proceed

**Step 3 (select_targets):**
- push / pull_request → presubmit+postsubmit families
- schedule → all families
- workflow_dispatch → parse explicit input
- PR labels: `gfx*` opt-in, `run-all-archs-ci`, `test:*`
- Validation against known families

**Step 5 (expand_matrix):**
- Port `generate_multi_arch_matrix` logic
- Group families by build variant, produce matrix entries

**Test coverage:** Each trigger type path, each label type, validation
of unknown families, the skip gate cases.

**Deliverable:** Script produces correct matrix output for all trigger
types. Can be tested locally by constructing `CIInputs` in tests.

### Phase 3: Wire into setup.yml, validate output

- `setup.yml` calls the new script when `MULTI_ARCH=true`
- Verify identical output to current `configure_ci.py` for the same inputs
- May need a comparison test or manual validation on a workflow_dispatch run

### Phase 4: Stage decisions + test type

Fill in Step 4 (`decide_stages`):
- Parse BUILD_TOPOLOGY.toml for source_set → artifact_group → stage mapping
- Classify changed files (submodule vs infra vs skippable)
- Propagate rebuilds downstream through stage DAG
- Handle explicit `prebuilt_stages` from workflow_dispatch
- Determine test_type (smoke vs full)
- Handle `run-full-tests-only` and `nightly_check_only_for_family` flags
  (which currently live as post-hoc mutations in `main()`)

Initially advisory — stage decisions appear in the step summary but
don't yet drive workflow behavior.

### Phase 5: Prebuilt integration + logging

Connect stage decisions to the multi-arch-prebuilt workflow plumbing:
- `prebuilt_stages` output feeds the copy job
- `rebuild_stages` gates stage jobs

Add quality-of-life logging:
- Structured step summary in GITHUB_STEP_SUMMARY (markdown table showing
  families, stages, rebuild/prebuilt decisions, test type, and *why* for
  each decision)
- Diagnostic logging to stdout for CI maintainers
- Both are testable: summary is a pure function, logging can be captured

### Phase 6: Test selection from rebuilt stages

Map rebuilt stages → test suites. Requires a mapping from artifact groups
or stages to test labels (either in BUILD_TOPOLOGY.toml or a new config).

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

1. [x] Design — pipeline architecture, feature audit
2. [ ] Phase 1: Scaffold — dataclasses, pipeline shape, test patterns
3. [ ] Phase 2: MVP logic — skip gate, target selection, matrix expansion
4. [ ] Phase 3: Wire into setup.yml, validate output parity
5. [ ] Phase 4: Stage decisions (topology parsing, source-set analysis)
6. [ ] Phase 5: Prebuilt integration + structured logging/summary
7. [ ] Phase 6: Test selection from rebuilt stages

## Branches

_(none yet)_

## Completion Notes

<!-- Fill this in when task is done -->
