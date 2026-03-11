---
repositories:
  - therock
---

# Multi-Arch Configure: Source-Aware CI Configuration

- **Status:** Phase 1 complete, reviewing scaffold
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

Parse GitHub context into a typed dataclass. This is the only step that
touches external state. Everything downstream is pure.

The script reads from two sources:
- `GITHUB_EVENT_PATH` — JSON file with the full event payload (PR info,
  workflow_dispatch inputs, etc.). Replaces the chain of individual env
  vars that setup.yml currently passes.
- A few standard GitHub env vars (`GITHUB_EVENT_NAME`, `GITHUB_OUTPUT`,
  `GITHUB_STEP_SUMMARY`, `GITHUB_REF_NAME`)

PR labels come from the event payload (for `pull_request` triggers, the
payload includes `pull_request.labels`). No separate `gh pr view` step
needed — the label fetching that currently lives in setup.yml YAML
moves into Python where the format handling can be tested.

```python
@dataclass(frozen=True)
class CIInputs:
    """All external inputs to the CI configuration pipeline."""
    event_name: str                    # push, pull_request, schedule, workflow_dispatch
    branch_name: str
    base_ref: str                      # For git diff (PR base, or HEAD^1)
    build_variant: str                 # release, asan, tsan
    pr_labels: list[str]               # From event payload
    # Per-platform workflow_dispatch overrides
    linux_amdgpu_families: str         # Raw comma-separated input
    windows_amdgpu_families: str
    linux_test_labels: str
    windows_test_labels: str
    # Prebuilt configuration (from workflow_dispatch)
    prebuilt_stages: str               # Comma-separated stage names
    baseline_run_id: str

    @staticmethod
    def from_environ() -> "CIInputs":
        """Parse from GitHub event context. Only place external state is read."""
        ...

    @property
    def is_pull_request(self) -> bool: ...
    @property
    def is_push(self) -> bool: ...
    @property
    def is_schedule(self) -> bool: ...
    @property
    def is_workflow_dispatch(self) -> bool: ...
```

**Source config:** None — this is pure context parsing.

**Testability:** Construct `CIInputs` directly in tests. No env var mocking
needed downstream. The `from_environ()` factory is the only thing that
touches the environment.

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

### Phase 3: Wire into workflow, validate output

Fork `setup.yml` → `setup_multi_arch.yml`:
- Checkout (stays in YAML)
- Call `configure_multi_arch_ci.py` — no env var pass-through chain,
  script reads `GITHUB_EVENT_PATH` directly
- Compute package version (independent, stays)

The `gh pr view` label-fetching step goes away — labels come from
the event payload, parsed in Python.

`multi_arch_ci.yml` calls the new setup workflow instead of `setup.yml`.

Validate: workflow_dispatch run produces equivalent matrix output to
current configure_ci.py for the same inputs.

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

### Q4: Fork setup.yml too

The current `setup.yml` does three things the Python script could own:

1. **PR label fetching** (lines 68-74) — `gh pr view` shell step writes
   `PR_LABELS` to `GITHUB_ENV`. The script could do this itself given
   `GITHUB_TOKEN` and the event context, removing a shell/Python boundary.
2. **Env var pass-through** (lines 79-87) — 8 env vars that are just
   `github.event.inputs.*` piped to the script. If the script reads the
   GitHub event JSON directly (via `GITHUB_EVENT_PATH`), most of these
   go away.
3. **The `MULTI_ARCH` flag** — a forked setup workflow just calls the
   new script. No flag needed.

**Proposed:** Fork to `setup_multi_arch.yml` that does:
- Checkout (stays in YAML — needs `actions/checkout`)
- Call `configure_multi_arch_ci.py` with minimal env vars
- Compute package version (independent, stays)

The script itself handles label fetching and reads inputs from
`GITHUB_EVENT_PATH` instead of relying on a chain of env var pass-throughs.

This means fewer places where data format assumptions live (currently:
YAML step formats labels → `GITHUB_ENV` → env var → Python parses JSON)
and the script becomes more self-contained and testable.

**Alternative:** Keep `setup.yml` shared, branch on `inputs.multi_arch`
to call the right script. Simpler initially but keeps the env var coupling.

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

### 2026-03-11 - Phase 1 scaffold committed

Commit `657c8618` on branch `multi-arch-configure`:

**`configure_multi_arch_ci.py` (~280 lines):**
- 7 frozen dataclasses: `CIInputs`, `SkipDecision`, `TargetSelection`,
  `StageDecision`, `StageDecisions`, `MatrixEntry`, `CIOutputs`
- `CIInputs.from_environ()` reads `GITHUB_EVENT_PATH` for event payload
  (PR labels, workflow_dispatch inputs, push `before` SHA)
- 5 stub step functions, each with TODO markers
- `configure()` orchestrator wires steps together with skip gate short-circuit
- `write_outputs()` uses `gha_set_output` / `gha_append_step_summary`

**`tests/configure_multi_arch_ci_test.py` (~310 lines, 19 tests):**
- `TestCIInputs` — construction, properties (is_pull_request, etc.), defaults
- `TestCIInputsFromEnviron` — event payload fixtures via tempfile for
  workflow_dispatch, pull_request (with labels), push (with before SHA)
- `TestCheckSkipCI` — stub returns no-skip
- `TestSelectTargets` — stub returns TargetSelection
- `TestDecideStages` — stub returns StageDecisions, prebuilt/rebuild partitioning
- `TestExpandMatrix` — empty families, MatrixEntry.to_dict()
- `TestFormatSummary` — skipped and normal summary output
- `TestConfigurePipeline` — skip gate short-circuit, all-steps-called (mocked)

**Design choices made during implementation:**
- `StageDecision.action` uses `Literal["rebuild", "prebuilt"]` (dropped "skip"
  from the design doc — a skipped stage is just absent from the decisions dict)
- `CIOutputs` uses `prebuilt_stages`/`rebuild_stages` as `list[str]` rather than
  per-platform strings — simpler for now, can split later if needed
- `changed_files` computed in `configure()` only for push/PR events (not
  schedule/workflow_dispatch) to avoid unnecessary git operations
- `BUILD_VARIANT` comes from `os.environ` (workflow_call input), not from
  `GITHUB_EVENT_PATH` — it's set by the calling workflow, not the event

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

## Design Considerations

### Workflow ↔ script input contract

The script reads workflow_dispatch inputs and PR labels from
`GITHUB_EVENT_PATH` (a JSON file GitHub provides to every Actions step)
instead of having setup.yml pass each value as an individual env var.
This eliminates boilerplate (10+ env vars → 2-3) but makes the dataflow
between the YAML workflow and the Python script less visible.

**Risk:** A workflow input is added/removed in YAML but the corresponding
read in Python is forgotten, or vice versa. Silent mismatch — the input
is ignored or the script reads a field that no longer exists.

**Mitigations:**
- `CIInputs.from_environ()` is the only function that reads the event
  JSON. It validates expected fields per event type and fails fast on
  missing required fields.
- A contract test defines the set of event payload fields the script
  expects per trigger type. If the set changes in code but not in the
  test (or vice versa), the test fails with a clear message.
- A comment block in the setup workflow documents which fields the script
  reads, so the YAML side of the contract is visible to workflow authors.

**Note:** The explicit env var approach has the same drift risk (add an
env var in YAML, forget to read it in Python), just in a more visible
format. The contract test catches both directions regardless.

### PR labels: event payload vs `gh pr view`

For `pull_request` events, labels are included in the event payload at
`event.pull_request.labels`. No `gh pr view` step needed. However, if
labels are added *after* the event fires (e.g., the `labeled` activity
type), the payload reflects the state at event time. The current setup.yml
uses `gh pr view` which fetches live labels. In practice this rarely
matters since the workflow re-triggers on `labeled` events anyway, but
it's worth noting.

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
2. [x] Phase 1: Scaffold — dataclasses, pipeline shape, test patterns
3. [ ] Review and refine scaffold (current)
4. [ ] Phase 2: MVP logic — skip gate, target selection, matrix expansion
5. [ ] Phase 3: Wire into workflow, validate output parity
6. [ ] Phase 4: Stage decisions (topology parsing, source-set analysis)
7. [ ] Phase 5: Prebuilt integration + structured logging/summary
8. [ ] Phase 6: Test selection from rebuilt stages

### Review checklist for Phase 1 scaffold

- [ ] Do the step boundaries feel right? Should anything merge or split?
- [ ] Are the dataclass fields complete for MVP, or are any missing/extra?
- [ ] Is the `CIInputs.from_environ()` approach (reading `GITHUB_EVENT_PATH`)
      working well? Any ergonomic issues with the test fixtures?
- [ ] Does `configure()` orchestration read cleanly?
- [ ] Test patterns — are the test classes showing the right style for each step?
- [ ] Anything in the task file design that doesn't match the implemented code?

### Phase 2 priorities (after review)

When moving to MVP logic, implement in this order:
1. **`select_targets`** — highest value, needed for any real output.
   Import family data from `amdgpu_family_matrix.py`. Handle all 4 trigger
   types. PR label parsing for `gfx*`, `test:*`, `run-all-archs-ci`.
2. **`expand_matrix`** — port `generate_multi_arch_matrix` logic so the
   script produces actual matrix JSON.
3. **`check_skip_ci`** — integrate `is_ci_run_required()` from
   `configure_ci_path_filters.py`. Check `skip-ci` label.
4. **`decide_stages`** — initially just test_type logic (smoke vs full).
   Stage rebuild/prebuilt decisions come in Phase 4.

## Branches

- `multi-arch-configure` — branched from `multi-arch-prebuilt-3`

## Completion Notes

<!-- Fill this in when task is done -->
