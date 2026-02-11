---
repositories:
  - therock
---

# Static Analysis for GitHub Actions Workflows

- **Status:** Completed
- **Priority:** P2 (Medium)
- **Started:** 2026-01-22
- **Completed:** 2026-01-22

## Overview

When modifying reusable workflows, it's easy to introduce regressions that aren't caught by existing tools like actionlint. This task implements a unit test that validates `benc-uk/workflow-dispatch` action calls pass only inputs accepted by the target workflow.

## Goals

- [x] Identify gaps in actionlint coverage for TheRock's workflow patterns
- [x] Implement a test for `benc-uk/workflow-dispatch` input validation
- [x] Validate both unexpected inputs and missing required inputs
- [ ] Broader `workflow_call` input propagation validation (future work)

## Context

### Background

PR #2557 introduced a bug where a `ref` input was passed to `build_linux_jax_wheels.yml` via `benc-uk/workflow-dispatch`, but that workflow's `on: workflow_dispatch: inputs:` section didn't define `ref`. The GitHub API rejected the dispatch with "Unexpected inputs provided: ["ref"]", breaking nightly releases.

This class of bug is invisible to actionlint because `benc-uk/workflow-dispatch` is a regular action — actionlint just sees a step with a string `inputs` parameter. It cannot parse the JSON string to validate against the target workflow's accepted inputs.

### What actionlint covers vs. what it doesn't

**Actionlint catches** (for `workflow_call` / reusable workflows):
- Required inputs without defaults are passed
- Input types match declarations
- Outputs are correctly typed

**Actionlint does NOT catch:**
- Inputs passed via `benc-uk/workflow-dispatch` (regular action, not reusable workflow)
- Semantic changes in how inputs are consumed internally
- Input propagation through `workflow_call` chains (each workflow has isolated `inputs` context)

### The `benc-uk/workflow-dispatch` pattern

This action triggers workflows via the GitHub REST API's "Create a workflow dispatch event" endpoint. The `workflow` field supports names, filenames, or IDs — our test enforces filenames so it can resolve and validate locally.

### The Input Propagation Problem

**Key insight:** `inputs` in a reusable workflow refers to that workflow's own `workflow_call` inputs, NOT the original dispatch inputs from the calling workflow.

```
User dispatches ci_nightly.yml with linux_amdgpu_families="gfx1153"
       ↓
ci_nightly.yml: inputs.linux_amdgpu_families = "gfx1153" ✓
       ↓ (calls setup.yml without passing the input)
setup.yml: inputs.linux_amdgpu_families = "" ✗ (empty!)
```

#### The 2022 Unification (and its limits)

[GitHub unified inputs](https://github.blog/changelog/2022-06-09-github-actions-inputs-unified-across-manual-and-reusable-workflows/) so `inputs.*` works for both `workflow_dispatch` and `workflow_call`. But this only applies within a single workflow - inputs don't propagate across `workflow_call` boundaries.

### Potential Solutions

#### 1. Custom Static Analysis Tool (Recommended)

Build a tool that:

1. **Parses all workflow files** in `.github/workflows/`
2. **Builds a call graph** of workflow_call relationships
3. **Tracks input dependencies** - which `inputs.X` values each workflow uses
4. **Validates propagation** - for each caller, check if it passes required inputs

**Pseudocode:**
```python
def validate_workflows(workflows_dir):
    workflows = parse_all_workflows(workflows_dir)
    call_graph = build_call_graph(workflows)

    for caller, callees in call_graph.items():
        for callee, call_site in callees:
            # Find inputs the callee actually uses (references inputs.X)
            used_inputs = find_input_references(callee)

            # Find inputs the caller passes (in the 'with:' block)
            passed_inputs = call_site.get('with', {}).keys()

            # Find inputs with defaults in callee
            defaulted_inputs = {i for i in callee.inputs if i.has_default}

            # Flag inputs that are used but not passed and have no default
            missing = used_inputs - passed_inputs - defaulted_inputs
            if missing:
                warn(f"{caller} calls {callee} without passing: {missing}")
```

**Implementation options:**
- Python script using `ruamel.yaml` for parsing
- Go tool extending actionlint's AST
- Pre-commit hook that runs on workflow changes

#### 2. Workflow Interface Contracts

Treat reusable workflows like APIs with explicit contracts:

```yaml
# setup.yml
on:
  workflow_call:
    inputs:
      linux_amdgpu_families:
        type: string
        required: true  # Make it required, not optional with default
        description: "GPU families for Linux builds"
```

**When inputs are `required: true`**, actionlint WILL catch callers that don't pass them.

**Trade-off:** Less flexibility - can't have sensible defaults that work for most callers.

#### 3. Input Propagation Helper Pattern

Create a convention where workflows explicitly propagate all inputs:

```yaml
# ci_nightly.yml
jobs:
  setup:
    uses: ./.github/workflows/setup.yml
    with:
      # Explicit propagation of all dispatch inputs
      linux_amdgpu_families: ${{ inputs.linux_amdgpu_families }}
      windows_amdgpu_families: ${{ inputs.windows_amdgpu_families }}
      build_variant: ${{ inputs.build_variant }}
```

**Enforce with a lint rule:** If a workflow has `workflow_dispatch` inputs, require that calls to reusable workflows pass those inputs.

#### 4. Integration Tests (Lightweight)

Write tests that parse workflow YAML and simulate input flow without running full CI:

```python
def test_ci_nightly_propagates_inputs():
    """Verify ci_nightly.yml passes GPU family inputs to setup.yml"""
    ci_nightly = load_workflow("ci_nightly.yml")
    setup_call = ci_nightly.jobs["setup"]

    # These inputs should be propagated
    expected = ["linux_amdgpu_families", "windows_amdgpu_families"]
    passed = setup_call.get("with", {}).keys()

    for inp in expected:
        assert inp in passed, f"ci_nightly.yml should pass {inp} to setup.yml"
```

#### 5. Pre-commit Hook for Caller Inventory

When a reusable workflow changes, require the PR to document all callers:

```bash
#!/bin/bash
# .git/hooks/pre-commit or pre-commit config

changed_workflows=$(git diff --cached --name-only | grep '.github/workflows/')

for workflow in $changed_workflows; do
    if grep -q "workflow_call:" "$workflow"; then
        echo "⚠️  Reusable workflow modified: $workflow"
        echo "   Callers:"
        grep -r "uses:.*$(basename $workflow)" .github/workflows/ | grep -v "^$workflow"
        echo ""
        echo "   Please verify all callers are updated appropriately."
    fi
done
```

### Recommended Approach for TheRock

Given the complexity of TheRock's workflow hierarchy:

```
ci.yml → setup.yml → configure_ci.py
       → ci_linux.yml → build_portable_linux_artifacts.yml
       → ci_windows.yml → build_windows_artifacts.yml
```

**Short-term (Process):**
1. Require caller inventory in PR description for any reusable workflow change
2. Add integration tests for critical input propagation paths
3. Pre-commit hook that warns when reusable workflows are modified

**Medium-term (Tooling):**
4. Build custom validation script that parses workflow call graph, validates input propagation, and runs as part of CI

**Long-term (Architecture):**
5. Consider making critical inputs `required: true` so actionlint catches missing inputs
6. Version reusable workflows with breaking change policies
7. Centralize input definitions to reduce propagation chains

### Example: Custom Validation Script

```python
#!/usr/bin/env python3
"""Validate GitHub Actions workflow call graph and input propagation."""

import yaml
from pathlib import Path
import re

def load_workflows(workflows_dir: Path) -> dict:
    """Load all workflow files."""
    workflows = {}
    for f in workflows_dir.glob("*.yml"):
        with open(f) as fh:
            workflows[f.name] = yaml.safe_load(fh)
    return workflows

def find_callers(workflows: dict, target: str) -> list:
    """Find all workflows that call the target workflow."""
    callers = []
    pattern = re.compile(rf"uses:\s*\./.github/workflows/{re.escape(target)}")
    for name, wf in workflows.items():
        if name == target:
            continue
        for job_name, job in wf.get("jobs", {}).items():
            if "uses" in job and target in job["uses"]:
                callers.append((name, job_name, job.get("with", {})))
    return callers

def get_workflow_inputs(workflow: dict) -> set:
    """Get inputs defined in a workflow_call trigger."""
    inputs = set()
    on_block = workflow.get("on", {})
    if isinstance(on_block, dict):
        wf_call = on_block.get("workflow_call", {})
        if wf_call and "inputs" in wf_call:
            inputs = set(wf_call["inputs"].keys())
    return inputs

def find_input_references(workflow: dict) -> set:
    """Find all inputs.X references in the workflow."""
    refs = set()
    yaml_str = yaml.dump(workflow)
    for match in re.finditer(r"\$\{\{\s*inputs\.(\w+)", yaml_str):
        refs.add(match.group(1))
    return refs

def validate_input_propagation(workflows_dir: Path) -> list:
    """Validate that callers pass inputs that callees use."""
    workflows = load_workflows(workflows_dir)
    issues = []

    for name, wf in workflows.items():
        # Only check reusable workflows
        defined_inputs = get_workflow_inputs(wf)
        if not defined_inputs:
            continue

        used_inputs = find_input_references(wf)
        callers = find_callers(workflows, name)

        for caller_name, job_name, passed_inputs in callers:
            passed = set(passed_inputs.keys())
            # Find inputs that are used but not passed
            # (could also check for defaults here)
            missing = used_inputs - passed
            if missing:
                issues.append({
                    "callee": name,
                    "caller": caller_name,
                    "job": job_name,
                    "missing_inputs": missing,
                })

    return issues

if __name__ == "__main__":
    issues = validate_input_propagation(Path(".github/workflows"))
    for issue in issues:
        print(f"⚠️  {issue['caller']}:{issue['job']} calls {issue['callee']}")
        print(f"   Missing inputs: {', '.join(issue['missing_inputs'])}")
```

### Sources

- [actionlint - Static checker for GitHub Actions](https://github.com/rhysd/actionlint)
- [actionlint checks documentation](https://github.com/rhysd/actionlint/blob/main/docs/checks.md)
- [GitHub Actions: Inputs unified across manual and reusable workflows](https://github.blog/changelog/2022-06-09-github-actions-inputs-unified-across-manual-and-reusable-workflows/)
- [Community discussion: Homogenise inputs from callable workflows and event inputs](https://github.com/orgs/community/discussions/9092)
- [Hard won lessons about Github Actions](https://lucasroesler.com/posts/2022/2-github-actions-lessons/)

### Related Work
- PR #2557: The bug that motivated this work
- PR #2317: Added actionlint to TheRock (covers `workflow_call` but not dispatch actions)
- PR #3057: The implementation PR for this test

### Directories/Files Involved
```
D:/projects/TheRock/build_tools/github_actions/tests/workflow_dispatch_inputs_test.py
D:/projects/TheRock/.github/workflows/release_portable_linux_packages.yml
D:/projects/TheRock/.github/workflows/release_windows_packages.yml
```

## Decisions & Trade-offs

- **Decision:** Dynamic test generation (one test per workflow file) instead of a single monolithic test
  - **Rationale:** Per-file isolation means failures in one workflow don't mask others; pytest output naturally identifies which file has the problem
  - **Alternatives considered:** Single test with `subTest`; static test methods per file

- **Decision:** Only generate tests for workflow files that have dispatch calls
  - **Rationale:** Reduces test count from 72 (all files × 2) to 4 (2 files × 2), eliminating no-op tests
  - **Alternatives considered:** Keeping tests for all files as "sanity checks" (decided against since they assert nothing)

- **Decision:** Enforce workflow filenames (not IDs or display names) in the `workflow` field
  - **Rationale:** Enables local validation by resolving the target file and parsing its inputs
  - **Alternatives considered:** Skipping unresolvable targets (would miss the validation opportunity)

- **Decision:** Keep the "required inputs" test despite actionlint covering `workflow_call` required inputs
  - **Rationale:** Actionlint doesn't cover `benc-uk/workflow-dispatch` calls at all; the GitHub API may silently accept missing required inputs leading to runtime failures

- **Decision:** Direct `json.loads` without regex fallback for parsing dispatch inputs
  - **Rationale:** GitHub expressions (`${{ ... }}`) are inside JSON string values and don't break parsing; removed dead code

## Code Changes

### Files Added
- `build_tools/github_actions/tests/workflow_dispatch_inputs_test.py` — Unit test with:
  - `get_workflow_dispatch_inputs()` — extracts accepted input names from target workflow
  - `get_required_workflow_dispatch_inputs()` — extracts required inputs (no default)
  - `parse_dispatch_inputs_json()` — parses the JSON inputs string from action steps
  - `find_dispatch_calls_in_workflow()` — finds dispatch calls in a single workflow
  - Dynamic test generation for unexpected and missing-required input checks

### Testing Done
- All 4 generated tests pass (2 workflow files × 2 checks)
- Verified bug reproduction: adding `"ref"` to JAX dispatch correctly triggers failure
- Verified actionlint does NOT catch this class of bug

## Completion Notes

### Summary
Implemented a focused unit test that prevents the PR #2557 class of bug. The test parses workflow files, finds `benc-uk/workflow-dispatch` calls, and validates their inputs against what the target workflow accepts.

### Lessons Learned
- PyYAML parses the unquoted YAML key `on:` as Python boolean `True` (YAML 1.1 boolean literal)
- GitHub expressions inside JSON string values don't affect `json.loads` — no regex sanitization needed
- `benc-uk/workflow-dispatch` is invisible to actionlint's static analysis

### Follow-up Tasks
- Broader `workflow_call` input propagation validation (the call-graph analysis from the original plan)
- Consider adding this test to CI or pre-commit for automatic validation on workflow changes
- Could extend to validate that `workflow` field uses filenames (not names/IDs)
