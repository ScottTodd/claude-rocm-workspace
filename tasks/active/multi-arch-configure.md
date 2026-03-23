---
repositories:
  - therock
---

# Multi-Arch Configure: Source-Aware CI Configuration

- **Status:** Ready to send upstream PR
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

### 2026-03-13 - Scaffold review + select_targets implementation

**Scaffold refinements (5e1c23c5, 3eaaf719, a3914256):**
- `StageDecisions` → job graph model: `JobGroupDecision` base with
  `BuildRocmDecision` (per-stage granularity) and `TestRocmDecision`
  (test type) subclasses. `JobDecisions` has explicit named fields for
  each job group node in the DAG.
- Renamed `enable_build_jobs` → `is_ci_enabled` internally (output key
  unchanged for workflow compat).
- Style guide compliance: removed `from __future__ import annotations`,
  moved imports to top, named args on multi-param calls.
- Reordered steps: decide_jobs (3) before select_targets (4) so target
  selection and matrix expansion are adjacent.
- Test cleanup: shared `_run_from_environ` helper, inline CIInputs
  construction, collapsed property tests.

**select_targets implementation (6b401588):**
- 588 lines script, 553 lines tests (28 tests, 1 skipped)
- Trigger-type dispatch: workflow_dispatch (per-platform), pull_request
  (presubmit + label opt-ins), push (presubmit+postsubmit), schedule (all)
- PR labels: `gfx*` adds family, `run-all-archs-ci` selects all
- Input parsing at boundary: `CIInputs.linux_amdgpu_families` is `list[str]`
- Fail-fast validation: unknown families raise `ValueError`
- Platform filtering: families without platform entry excluded

**Key design decisions:**
- PR defaults to presubmit only (not postsubmit) — matches original configure_ci.py
- Dropped `determine_long_lived_branch` — push always gets presubmit+postsubmit
- Prebuilt only for PRs (version embedding makes prebuilt risky for push/schedule)

### 2026-03-16 — Phase 2 + 3 complete (MVP)

Implemented all pipeline steps and wired into workflows. 13 commits on
`multi-arch-configure` branch.

**expand_build_configs (was expand_matrix):**
- Simplified from variant-grouping loop to flat membership check (single
  build_variant per workflow run)
- `expand_build_configs()` returns `BuildConfigs` dataclass with
  `linux: BuildConfig | None`, `windows: BuildConfig | None`
- Removed matrix array output — per-platform JSON object instead
- Added `amdgpu_family_matrix_test.py` for data invariant validation
  (no duplicate families, required fields, non-empty build_variants)

**check_skip_ci:**
- skip-ci PR label (priority), then delegates to `is_ci_run_required()`
- Mocks `is_ci_run_required` in tests to avoid duplicating path filter coverage

**decide_jobs:**
- test_type: quick (default) → comprehensive (schedule) → full (submodule
  change or test labels). `test_filter:` PR label overrides any level.
- Adopted test type names from PR #3992 (quick/standard/comprehensive/full)
- Early returns with explicit priority order, fail-fast on invalid test_filter
- prebuilt_stages parsed into `BuildRocmDecision.stage_decisions`
- baseline_run_id on `BuildRocmDecision` (passthrough for now, will derive
  automatically later)

**GitContext dataclass:**
- Separated git-derived data (changed_files, submodule_paths) from CIInputs
- `configure()` is fully pure — takes CIInputs + GitContext, no git calls
- Tests construct GitContext directly, no git dependency

**Workflow integration:**
- New `setup_multi_arch.yml`: checkout, configure_multi_arch_ci.py, package version
- Script reads GITHUB_EVENT_PATH directly (no env var pass-through chain)
- `multi_arch_ci.yml` calls setup_multi_arch.yml, uses `fromJSON()` property
  access on per-platform build config objects instead of matrix strategy

**Code quality:**
- Structured logging via `log()` methods on all pipeline dataclasses
- Explicit field access everywhere (no getattr)
- Structural tests (not change-detector) for expand_build_configs
- 919 lines script, 322 statements, 90% coverage, 43 tests
- All uncovered code is I/O boundary (from_environ, from_repo, write_outputs, main)

### 2026-03-17 — Validation, logging, and summary formatting

Validated on fork with multiple workflow_dispatch runs. Fixed input case
normalization (lowercase at parse boundary). Iterated through 5 rounds
of summary format design (v1-v5 in reviews/).

**Summary format (configure_multi_arch_ci_summary.py):**
- Structure: one-liner trigger, non-default callout (GitHub alert syntax),
  fixed DAG, ### sections per job group node
- test-rocm: per-family table with Platform, Family, Runner Label, Scope
- build-rocm: families table + prebuilt stage details
- Non-default callouts highlight labels, explicit families, prebuilt stages
- Empty families case handled ("No GPU families selected")
- Skipped case shows changed files + link to path filter source

**Logging improvements:**
- Phase headers in configure() ("=== Inputs ===", "=== Checking if CI
  should run ===", etc.)
- All CIInputs fields printed unconditionally (empty values informative)
- check_skip_ci logs "Checking N files against path filters..."
- baseline_run_id added to CIInputs.log()

**Analysis of related PRs:**
- PR #3653 (amdgpu_family_matrix dataclass rewrite): low switching cost,
  concerns about BuildConfig name collision and test_scope naming
- PR #1732 (weekly CI): recommends migrating to multi-arch instead of
  parallel single-arch pipeline. Gaps: benchmarks, release tasks

### 2026-03-18 — Output consolidation, workflow plumbing, cleanup

Rebased onto main (picked up #3992 test filter, #3938 prebuilt_stages,
#4039 ci:run-multi-arch label gate). Major refactoring session.

**Output consolidation:**
- Replaced 7+ individual BuildConfig inputs on multi_arch_ci_linux.yml
  and multi_arch_ci_windows.yml with a single `build_config` JSON string.
  Downstream workflows unpack with `fromJSON(inputs.build_config).field`.
- Renamed `matrix_per_family_json` (double-encoded JSON string) to
  `per_family_info` (native list) — eliminates `fromJSON(fromJSON(...))`
- Folded `prebuilt_stages` and `baseline_run_id` into BuildConfig —
  setup_multi_arch.yml outputs reduced from 11 to 9
- Added BuildConfig contract tests: regex-extracts
  `fromJSON(inputs.build_config).FIELD` references from workflow YAML
  and asserts they match `dataclasses.fields(BuildConfig)`. Linux checks
  exact match (all fields used), Windows checks subset (no unknown).

**configure_ci.py cleanup:**
- Removed `generate_multi_arch_matrix` function (~110 lines)
- Removed `multi_arch` parameter from `matrix_generator` and `main()`
- Removed `ci:run-multi-arch` label check (now in our script)
- Removed 6 multi-arch tests and helper from configure_ci_test.py
- Net -500 lines from configure_ci.py + tests

**Label gate in new script:**
- `check_skip_ci` now requires `ci:run-multi-arch` PR label for
  pull_request triggers — opt-in during transition (#3337)
- push/schedule/workflow_dispatch unaffected

**Parallel work (separate branches, some merged):**
- `ci-label-rename` branch: `skip-ci` → `ci:skip`, `run-all-archs-ci`
  → `ci:run-all-archs` (merged as #4038)
- `multi-arch-pr-enable` branch: uncomment pull_request trigger +
  label gate in configure_ci.py (PR #4039)
- `users/scotttodd/s3-auth-simplification`: fix artifact_backend.py
  S3 client to use boto3 default credential chain instead of manually
  checking env vars + UNSIGNED fallback (PR #4040)
- `IS_PR_FROM_FORK` env var added to multi-arch artifact build workflows

### PR #3653 Analysis: new_amdgpu_family_matrix dataclass rewrite

**What it does:** Replaces the nested dict format in `new_amdgpu_family_matrix.py`
with typed dataclasses: `MatrixEntry` → `PlatformConfig` → `BuildConfig` /
`TestConfig` / `ReleaseConfig`. Auto-discovers entries from module-level
`_GFX*` variables. Case-insensitive key lookup, family-level defaults,
group resolution via `get_entries_for_groups()`.

**What it changes for us:** Our `select_targets` and `expand_build_configs`
currently import from the old `amdgpu_family_matrix.py` and work with
raw dicts (`all_families[family_name][platform]["family"]`, etc.). After
#3653 lands, we'd switch to the new typed API.

**Switching cost for configure_multi_arch_ci.py (low):**

- `select_targets`: Replace `get_all_families_for_trigger_types(["presubmit"])`
  with `matrix.get_entries_for_groups(["amdgpu_presubmit"])`. The group
  names use family-level keys (e.g. "gfx94X-dcgpu") instead of our current
  target names (e.g. "gfx94x"). `_validate_family_names` and
  `_filter_families_by_platform` become simpler — the new API handles
  case-insensitive lookup and reports unmatched keys.

- `expand_build_configs` / `_expand_build_config_for_platform`: Replace
  dict indexing (`platform_info["family"]`, `platform_info["test-runs-on"]`)
  with typed field access (`entry.linux.test.runs_on.test`,
  `entry.linux.build.build_variants`). The `all_build_variants` dict
  import goes away — variant info lives on `BuildVariantInfo` dataclass.

- `TargetSelection` stays the same — it's our pipeline boundary, not tied
  to the matrix format.

**Architectural feedback for PR #3653:**

Strengths:
- Typed fields with defaults — less boilerplate per entry, harder to
  get wrong
- Auto-discovery of entries — adding a GPU is just a new variable
- `get_entries_for_groups` with `GroupLookupResult` (entries + unmatched_keys)
  is exactly what we need for fail-fast validation
- `is_family_default` for family-level lookup is clean

Concerns to raise:
- **Name collision:** PR #3653 defines `BuildConfig` in
  `new_amdgpu_family_matrix_types.py`. Our pipeline also defines
  `BuildConfig` in `configure_multi_arch_ci.py` (the per-platform build
  configuration output). These are different things — theirs is per-entry
  build settings (variants, expect_failure), ours is the fully-expanded
  build configuration for a workflow job. Need to disambiguate — either
  rename ours (e.g. `PlatformBuildOutput`) or theirs (e.g. `EntryBuildConfig`).
- **`test_scope` naming:** PR #3653 adds `TestConfig.test_scope` with values
  `"all"`, `"smoke"`, `"full"`. But PR #3992 (now merged) renamed smoke→quick
  and added standard/comprehensive. These should be aligned. The PR may
  have been written before #3992 landed.
- **Group key format:** Groups use family-level keys like "gfx94X-dcgpu"
  (cmake target names) while the old matrix uses short keys like "gfx94x".
  Our `select_targets` currently works with the short keys (from PR labels
  like `gfx94x`). The new API's case-insensitive lookup handles this, but
  PR label parsing needs to map `gfx94x` → a key the matrix recognizes.
  Worth verifying the case-insensitive lookup handles partial matches
  like `gfx94x` → `gfx94X-dcgpu` (via `is_family_default`).
- **`all_build_variants` location:** The PR moves variant config into the
  data module. Currently `all_build_variants` is a module-level dict in
  `amdgpu_family_matrix.py` that both `configure_ci.py` and our script
  import. After #3653, this becomes `AllBuildVariants` dataclass accessed
  via `amdgpu_family_info_matrix_all.build_variants` or similar. The
  migration path for existing consumers should be clear.
- **No consumer migration:** The PR adds the new API but doesn't update
  any consumers (`configure_ci.py`, our script, etc.). This is fine as a
  standalone data layer PR, but the old `amdgpu_family_matrix.py` stays
  around with a "keep in sync" comment. The migration should happen
  promptly to avoid drift.

### PR #1732 Analysis: Weekly CI and new amdgpu matrix generator

**What it does:** Introduces `ci_weekly.yml` (scheduled + workflow_dispatch),
`new_ci_linux.yml` (per-target reusable workflow), and a new
`configure_amdgpu_matrix.py` script. The configure script outputs a
per-target JSON config that the workflow unpacks with `fromJSON()`.

**Architecture:** Single-arch approach — one workflow job per GPU target.
Each target gets its own `new_ci_linux.yml` call with an `amdgpu_family_config`
JSON object containing `build.*`, `test.*`, `release.*` fields. This is the
opposite of multi-arch (one job for all targets with per-arch stages).

**Key differences from our multi-arch configure script:**

| Aspect | PR #1732 | Our script |
|--------|----------|------------|
| Architecture | Single-arch: one job per target | Multi-arch: one job for all targets |
| Matrix output | Array of per-target JSON objects | One JSON object per platform |
| Build unit | Per-target build + test | Per-stage build, per-target test |
| Config shape | `{amdgpu_family, build: {...}, test: {...}}` | `BuildConfig` with `matrix_per_family_json` |
| Prebuilt | `use_prebuilt_artifacts` boolean | Per-stage `prebuilt_stages` |

**Compatibility concerns:**

1. **Parallel configure scripts.** PR #1732 adds `configure_amdgpu_matrix.py`
   as a third configure script (alongside `configure_ci.py` and our
   `configure_multi_arch_ci.py`). All three read the same matrix data but
   produce different output shapes. Adding a new GPU family or changing
   test config requires updating multiple consumers.

2. **`new_ci_linux.yml` vs `multi_arch_ci_linux.yml`.** Both are reusable
   Linux CI workflows but with different input contracts. A weekly CI built
   on multi-arch would use `multi_arch_ci_linux.yml` directly.

3. **Weekly CI as a multi-arch consumer.** Our script already handles the
   weekly CI's core need: `schedule` trigger → all families including
   nightly-only. The weekly CI could be a thin wrapper calling
   `multi_arch_ci.yml` rather than a separate pipeline.

4. **`predefined_groups` input.** PR #1732 exposes group names as a
   workflow_dispatch input ("run the presubmit group"). Our script handles
   this implicitly via trigger type, but doesn't expose group names as
   explicit inputs. Could be useful for "run as if presubmit" scenarios.

5. **`TaskMask` (BUILD, TEST, RELEASE).** Controls which pipeline parts run.
   Our `JobDecisions` covers build vs test via job group actions but doesn't
   have a release concept yet.

6. **Benchmarks.** `new_ci_linux.yml` has a `test_linux_benchmarks` job.
   Our multi-arch pipeline doesn't have a benchmark job group yet — would
   need one for weekly CI migration.

**Recommendation:** Rather than letting #1732 land as a parallel single-arch
pipeline, weekly CI should migrate to multi-arch. The `schedule` trigger
in `multi_arch_ci.yml` + our configure script already covers the core use
case. The gaps are benchmarks and release tasks, both addressable as new
job groups in the existing model.

- Prebuilt only for PRs (version embedding makes prebuilt risky for push/schedule)
- Job graph model: build-rocm → test-rocm → build-rocm-python → build-pytorch etc.
- Test determination is a separate concern from job decisions (future: per-job-group
  target determinator, similar to pytorch upstream)

## Job Graph Model

The CI pipeline is a DAG of job groups:

```
build-rocm → test-rocm
           → build-rocm-python → build-pytorch → test-pytorch
                               → build-jax     → test-jax
                               → build-<framework> → test-<framework>
```

### Subgraph selection from changed files

Changed files determine **where we enter** the DAG and **how far we
propagate**. Everything upstream of the entry point uses prebuilt
artifacts. Everything not reachable from the change is skipped.

**Example: change to a ROCm subproject (e.g. HIP runtime)**
Most ROCm changes propagate through to python packages and frameworks:
```
[prebuilt] foundation → [rebuild] compiler-runtime → ... → [test] rocm
                                                         → [rebuild] rocm-python → [rebuild] pytorch → [test] pytorch
                                                                                → [rebuild] jax → [test] jax
```

**Example: change to pytorch packaging code only**
ROCm artifacts are unchanged — start from prebuilt rocm-python:
```
[prebuilt rocm-python] → [rebuild] pytorch → [test] pytorch
                       ↛ build-jax (not affected)
                       ↛ test-rocm (rocm unchanged)
```

**Example: change to jax packaging code only**
```
[prebuilt rocm-python] → [rebuild] jax → [test] jax
                       ↛ build-pytorch (not affected)
```

**Example: change to CI workflow YAML or docs**
May not require building anything — handled by the skip-CI gate.

### Two levels of granularity

1. **Job group level** — the nodes above (build-rocm, test-rocm,
   build-rocm-python, build-pytorch, test-pytorch, build-jax, etc.).
   Small DAG, could be hardcoded or defined in simple config.
2. **Stage level** (within build-rocm) — foundation, compiler-runtime,
   math-libs, etc. BUILD_TOPOLOGY.toml defines this sub-DAG.

### Implications for the pipeline step

The old "Step 4: Decide Stages" mixed build stages with test type — these
are separate concerns. The replacement is a **job decisions** step that
determines, for the whole job graph:
- Which job groups run (entry point + reachability)
- Within build-rocm: which stages rebuild vs use prebuilt
- Test type per test group (smoke vs full)

Initially: all job groups run, all stages rebuild, test type uses existing
smoke/full logic. The subgraph selection is added later without changing
the data structure.

### Prebuilt eligibility by trigger type

Prebuilt artifacts have embedded version information (package filenames,
wheel metadata, etc.). Mixing prebuilt artifacts from one commit with
freshly-built artifacts from another commit creates version mismatches.

**Policy:** Only pull_request triggers use prebuilt artifacts. PR builds
are ephemeral — versions are `0.0.1.dev+<hash>`, nobody installs them,
and slight version mismatches between prebuilt and rebuilt components
are acceptable. Push and schedule builds produce artifacts that go to
release/nightly channels, where version consistency matters.

| Trigger            | Prebuilt eligible? | Rationale |
|--------------------|-------------------|-----------|
| `pull_request`     | Yes | Ephemeral builds, versions are dev hashes, goal is fast feedback |
| `push`             | No  | Produces release/nightly artifacts, version consistency required |
| `schedule`         | No  | Full nightly builds, version consistency required |
| `workflow_dispatch` | Explicit only | User sets `prebuilt_stages` — they know what they're doing |

This simplifies `decide_jobs`:
- push/schedule → everything runs, no prebuilt analysis needed
- workflow_dispatch with explicit prebuilt_stages → trust the user
- pull_request → analyze changed files, use prebuilt where possible

### Testing strategy for decide_jobs

The goal of the configure_ci refactoring is to make policy decisions
visible in code and easy to test. Each policy is a pure function test:

**Trigger type policy (simple):**
- push → all job groups run, no prebuilt
- schedule → all job groups run, no prebuilt
- workflow_dispatch with prebuilt_stages → explicit override applied
- workflow_dispatch without prebuilt_stages → all run

**Changed-file analysis (pull_request only, the interesting cases):**
- Files only in pytorch packaging → build_rocm=prebuilt, test_rocm=skip, build_rocm_python=prebuilt, build_pytorch=run, test_pytorch=run
- Files only in rocm-python packaging → build_rocm=prebuilt, test_rocm=skip, build_rocm_python=run, build_pytorch=run, test_pytorch=run
- Files in a ROCm submodule → build_rocm=run (specific stages), everything downstream=run
- Files only in CI YAML/docs → caught by skip gate (step 2), never reaches decide_jobs
- Infra files (non-submodule, non-skippable) → everything runs (conservative)

Each test constructs a CIInputs + changed_files list and asserts on the
returned JobDecisions. No git, no filesystem, no environment.

## Decisions & Trade-offs

- **Pipeline of pure transformations**: Each step takes typed input, produces
  typed output. Side effects only at the edges (env read, output write).
- **Fork over extend**: Multi-arch needs stage decisions, different matrix
  fields, and will grow test selection. Bolting these onto the existing
  295-line function would make both harder to maintain.
- **Topology-driven**: All stage/source_set logic reads from BUILD_TOPOLOGY.toml.
  No hardcoded stage names in Python.
- **Dataclasses over dicts**: `CIInputs`, `TargetSelection`, `JobDecisions`,
  `MatrixEntry`, `CIOutputs` — each step's interface is explicit.
- **Job graph, not flat stages**: The CI pipeline is a DAG of job groups.
  Decisions operate on the graph (entry point + reachability), not a flat
  list. "Stages" is a build-rocm-specific refinement within the graph.
- **Prebuilt only for PRs**: Version embedding in packages makes prebuilt
  reuse risky for push/schedule/release builds. PRs use dev versions where
  slight mismatches are acceptable, so prebuilt analysis only runs there.
- **Policy as testable code**: Each trigger-type policy and changed-file
  mapping is a pure function, testable with constructed inputs and no
  environment dependencies.

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
- [Issue #3337](https://github.com/ROCm/TheRock/issues/3337) — enable multi-arch CI on pull_request ([comment with migration plan](https://github.com/ROCm/TheRock/issues/3337#issuecomment-4075841091))
- [Issue #3340](https://github.com/ROCm/TheRock/issues/3340) — deprecate non-multi-arch CI
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
3. [x] Review and refine scaffold
4. [x] Phase 2: MVP logic
   - [x] `select_targets` — trigger dispatch, PR labels, platform filtering
   - [x] `expand_build_configs` — per-platform BuildConfig (was `expand_matrix`)
   - [x] `check_skip_ci` — skip-ci label, path filtering
   - [x] `decide_jobs` — test_type (quick/comprehensive/full), prebuilt stages, baseline_run_id
5. [x] Phase 3: Wire into workflow
   - [x] `setup_multi_arch.yml` — new setup workflow calling configure_multi_arch_ci.py
   - [x] `multi_arch_ci.yml` — uses setup_multi_arch.yml, fromJSON on per-platform build configs
6. [x] Pre-PR cleanup: fix stale docstring, sys.exit → raise, rename lookup_matrix
7. [x] Validation: workflow_dispatch runs on fork (various configs, prebuilt, empty)
8. [x] Iterate on logging + `format_summary` markdown
   - Rich step summary: DAG, per-family test runner table, non-default callouts
   - Extracted to `configure_multi_arch_ci_summary.py`
   - Phase headers in logs ("=== Inputs ===", "=== Checking if CI should run ===")
   - Case normalization (lowercase at parse boundary)
   - Empty families → "No GPU families selected" message
9. [x] Enable pull_request trigger with ci:run-multi-arch label gate
   (separate branch `multi-arch-pr-enable`, PR #4039)
10. [x] Rebase onto latest main
11. [x] Consolidate workflow outputs: single `build_config` JSON input,
    `per_family_info` flattened, prebuilt_stages/baseline_run_id folded in
12. [x] Remove multi-arch code from configure_ci.py (-500 lines)
13. [x] Add ci:run-multi-arch label gate to should_skip_ci
14. [x] Simplify: SkipDecision → bool, JobAction enum, remove reason fields,
    prebuilt_stages as list[str] internally, remove redundant _build_enabled outputs
15. [x] Fix Windows workflow stale references (fromJSON migration)
16. [x] Improve summary: per-skip-reason messages, per-platform test labels,
    ci: label callouts, remove git_context from summary path
17. [x] Send upstream PR: #4123
18. [ ] Validate with test runs on the upstream PR
19. [ ] Expand PR trigger policy: path-based filtering, Linux-only builds
    without tests. Eventually deprecate non-multi-arch CI (#3340).
20. [ ] Phase 4: Job graph decisions (topology parsing, source-set analysis)
21. [ ] Phase 5: Prebuilt integration (auto-derive baseline_run_id, DAG expansion)
22. [ ] Phase 6: Test determination (per-job-group, pytorch target determinator)

### Known issues / follow-ups

- workflow_dispatch per-platform filtering silently drops families unavailable
  on the requested platform (e.g. gfx950 on windows). Should validate per-platform
  and raise. Tracked by skipped test `test_workflow_dispatch_wrong_platform_raises`.
- workflow_dispatch with empty family inputs currently builds nothing. Consider
  adding a choice input or special strings (e.g. `all`, `presubmit`,
  `postsubmit`) that select predefined groups — "do what a PR would do" or
  "do what nightly would do" without listing families manually. Related to
  `predefined_groups` concept in PR #1732.
- PR #3653 rewrites amdgpu_family_matrix with dataclasses. When it lands,
  `select_targets` internals swap to the new API (canonical keys, typed entries).
  The pipeline boundary (`TargetSelection`) stays the same.
- Push to non-main branches now includes postsubmit families (gfx950).
  Intentional simplification — `determine_long_lived_branch` dropped.
- `run_functional_tests` not yet ported from single-arch pipeline. TODO in
  TestRocmDecision to consolidate test outputs into per-platform test config.

## Branches

- `multi-arch-configure` — branched from `multi-arch-prebuilt-3`

## Completion Notes

<!-- Fill this in when task is done -->
