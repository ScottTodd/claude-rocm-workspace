# format_summary v2: highlighting what's standard vs unusual

Key idea: a contributor scanning the step summary should immediately see
"this is a normal PR run" or "this run has unusual configuration — here's
what and why."

---

## Example scenarios

### Scenario 1: Normal push to main (nothing unusual)

Inputs: push, main, release, no labels, no prebuilt
Git: 3 files changed, 1 submodule (rocm-libraries)
Decisions: all families (presubmit+postsubmit), full tests, no prebuilt

### Scenario 2: workflow_dispatch with explicit families, test labels, prebuilt

Inputs: workflow_dispatch, linux=gfx94X,gfx110X, windows=gfx1151,
        test_labels=test:hipcub, prebuilt_stages=foundation,compiler-runtime,
        baseline_run_id=22909539293
Git: none (workflow_dispatch)
Decisions: explicit families, full tests, 2 prebuilt stages

### Scenario 3: PR with labels opting into extra targets

Inputs: pull_request, pr_labels=[gfx950, test:rocprim, test_filter:comprehensive]
Git: 5 files changed, 0 submodules
Decisions: presubmit + gfx950, comprehensive tests (overridden by label)

---

## Option I: "What's different" callouts

### Scenario 1 (normal push):

## Multi-Arch CI Configuration

**Trigger:** push to `main`

**Build:** Linux and Windows, release variant
- Linux: gfx94X-dcgpu, gfx110X-all, gfx1151, gfx120X-all, gfx950-dcgpu
- Windows: gfx110X-all, gfx1151, gfx120X-all

**Test:** full (submodule `rocm-libraries` changed)

### Scenario 2 (workflow_dispatch with overrides):

## Multi-Arch CI Configuration

**Trigger:** workflow_dispatch on `multi-arch-configure`

> **Non-default configuration:**
> - Explicit family selection (not using trigger-type defaults)
> - Test labels: test:hipcub
> - Prebuilt stages: foundation, compiler-runtime (from run [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293))

**Build:** Linux and Windows, release variant
- Linux: gfx94X-dcgpu, gfx110X-all
- Windows: gfx1151

**Test:** full (test labels specified)

### Scenario 3 (PR with label overrides):

## Multi-Arch CI Configuration

**Trigger:** pull_request on `feature-branch`

> **Non-default configuration:**
> - PR label `gfx950` added family gfx950 (not in default presubmit set)
> - PR label `test_filter:comprehensive` overrode test level (default would be quick)
> - PR label `test:rocprim` requested specific component tests

**Build:** Linux and Windows, release variant
- Linux: gfx94X-dcgpu, gfx110X-all, gfx1151, gfx120X-all, gfx950-dcgpu
- Windows: gfx110X-all, gfx1151, gfx120X-all, gfx950-dcgpu

**Test:** comprehensive (test_filter label: test_filter:comprehensive)

---

## Option J: Terse default, expandable details

### Scenario 1 (normal push):

## Multi-Arch CI Configuration

push to `main` · release · 5 families per platform · full tests (submodule changed)

### Scenario 2 (workflow_dispatch with overrides):

## Multi-Arch CI Configuration

workflow_dispatch on `multi-arch-configure` · release · full tests (test labels)

| | Linux | Windows |
|---|---|---|
| Families | gfx94X-dcgpu, gfx110X-all | gfx1151 |
| Prebuilt | foundation, compiler-runtime | foundation, compiler-runtime |

Test labels: test:hipcub · Baseline run: [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293)

### Scenario 3 (PR with label overrides):

## Multi-Arch CI Configuration

pull_request on `feature-branch` · release · comprehensive tests (label override)

**Labels applied:** `gfx950` (added family), `test:rocprim` (component test), `test_filter:comprehensive` (test level override)

---

## Option K: Decision log style

### Scenario 1 (normal push):

## Multi-Arch CI Configuration

| Step | Decision | Reason |
|------|----------|--------|
| Trigger | push | `main` branch |
| Skip CI? | No | Non-skippable files changed |
| Families | presubmit + postsubmit (5 linux, 3 windows) | Default for push |
| Test level | full | Submodule `rocm-libraries` changed |
| Prebuilt | none | Push builds always build from source |

### Scenario 2 (workflow_dispatch with overrides):

## Multi-Arch CI Configuration

| Step | Decision | Reason |
|------|----------|--------|
| Trigger | workflow_dispatch | `multi-arch-configure` branch |
| Skip CI? | No | workflow_dispatch always proceeds |
| Families | 2 linux, 1 windows | Explicit input: gfx94X-dcgpu, gfx110X-all (linux), gfx1151 (windows) |
| Test level | full | Test labels: test:hipcub |
| Prebuilt | foundation, compiler-runtime | Explicit input, baseline run [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293) |

### Scenario 3 (PR with label overrides):

## Multi-Arch CI Configuration

| Step | Decision | Reason |
|------|----------|--------|
| Trigger | pull_request | `feature-branch` |
| Skip CI? | No | Non-skippable files changed |
| Families | presubmit + gfx950 (5 linux, 4 windows) | Default presubmit + `gfx950` label |
| Test level | comprehensive | `test_filter:comprehensive` label (overrides default quick) |
| Test labels | test:rocprim | `test:rocprim` label |
| Prebuilt | none | Not yet enabled for PRs |

---

## Option L: Prose with inline "why" annotations

### Scenario 1 (normal push):

## Multi-Arch CI Configuration

This is a **push** to `main`, building **release** for all presubmit and postsubmit families.

**Linux:** gfx94X-dcgpu, gfx110X-all, gfx1151, gfx120X-all, gfx950-dcgpu
**Windows:** gfx110X-all, gfx1151, gfx120X-all

Running **full** tests because submodule `rocm-libraries` was modified. All stages build from source.

### Scenario 2 (workflow_dispatch with overrides):

## Multi-Arch CI Configuration

This is a **workflow_dispatch** run on `multi-arch-configure`, building **release** for explicitly selected families.

**Linux:** gfx94X-dcgpu, gfx110X-all
**Windows:** gfx1151

Stages **foundation** and **compiler-runtime** use prebuilt artifacts from run [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293). All other stages build from source.

Running **full** tests because test label `test:hipcub` was specified.

### Scenario 3 (PR with label overrides):

## Multi-Arch CI Configuration

This is a **pull_request** run on `feature-branch`, building **release** for the default presubmit families plus additions from PR labels.

**Linux:** gfx94X-dcgpu, gfx110X-all, gfx1151, gfx120X-all, gfx950-dcgpu
**Windows:** gfx110X-all, gfx1151, gfx120X-all, gfx950-dcgpu

Additional families from labels: **gfx950** (not in default presubmit set).

Running **comprehensive** tests (overridden by `test_filter:comprehensive` label; default would be quick). Component tests requested: `test:rocprim`.
