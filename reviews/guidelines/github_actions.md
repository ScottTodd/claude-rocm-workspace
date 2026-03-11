# GitHub Actions Review Guidelines

Checklist for reviewing PRs that modify GitHub Actions workflows.

## Summary

| Check | Automatable | Severity | Notes |
|-------|-------------|----------|-------|
| [All callers updated](#reusable-workflow-changes) | Partial | BLOCKING | Can list callers, can't verify correctness |
| [Input propagation correct](#input-propagation) | No | BLOCKING | Requires understanding data flow |
| [All trigger paths tested](#testing-trigger-paths) | No | BLOCKING | Each path may behave differently |
| [No breaking changes to callers](#breaking-changes) | No | BLOCKING | Semantic changes are subtle |
| [Script dependencies satisfied](#script-runtime-dependencies) | No | BLOCKING | Trace imports through script call chain |
| [No complex inline bash](#no-complex-inline-bash) | Partial | BLOCKING | Conditionals, loops, string manipulation belong in Python scripts |
| [Multiple checkouts wired correctly](#multiple-checkouts) | No | BLOCKING | Each checkout must feed its intended consumers |
| [Runners pinned to specific versions](#pinned-runner-versions) | Yes | IMPORTANT | Detect `ubuntu-latest` etc. |
| [Permissions minimal](#permissions) | Yes | IMPORTANT | Can scan for overly broad permissions |
| [Actions pinned](#pinned-versions) | Yes | IMPORTANT | Can detect `@main` or `@latest` |
| [Style guide followed](#style) | Partial | SUGGESTION | Linters can catch some issues |

**What reviewers must check manually:**
- Data flow through workflow_call chains
- Semantic correctness of input/output mappings
- Coverage of all trigger types (dispatch, call, PR, push, schedule)
- Regression to existing callers when modifying shared workflows
- Script runtime dependencies (pip packages available in CI environment)
- Whether inline bash should be a Python script (conditionals, loops, string manipulation)
- Multiple checkouts actually consumed by their intended steps (not silently unused)

**What automation can help with:**
- Listing all callers of a reusable workflow
- Detecting unpinned action versions and runner labels (`*-latest`)
- Scanning for overly broad permissions
- Style/lint checks (actionlint)
- Detecting complex inline bash (conditionals, loops in `run:` blocks)

---

## Scope and Exemptions

### When This Guide Applies

This guide applies to PRs that:
- Add or modify `.github/workflows/*.yml` files
- Add or modify reusable workflows (workflows with `workflow_call` trigger)
- Change workflow inputs, outputs, or secrets
- Modify job dependencies or matrix strategies

### Lighter Review for Trivial Changes

Some workflow changes don't need full scrutiny:
- Updating pinned action versions (e.g., `v3.0.0` to `v3.0.1`)
- Fixing typos in comments or job names
- Adjusting timeouts or minor configuration

For these, verify CI passes and move on.

---

## No Complex Inline Bash

### The Rule

The [GitHub Actions style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/github_actions_style_guide.md#prefer-python-scripts-over-inline-bash) says: **prefer Python scripts over inline bash.** Workflow `run:` blocks should call scripts, not contain logic.

This is a style guide rule, but violations are **BLOCKING** because:
- Inline bash can't be unit tested
- Inline bash can't be debugged with standard tools
- Inline bash isn't portable across platforms
- Inline bash encourages duplicating logic that scripts already handle

### Complexity Signals

Any of these in a `run:` block indicate the logic belongs in a Python script:

- **Conditionals** (`if/elif/else`)
- **Loops** (`for`, `while`)
- **String manipulation** (parameter expansion, `sed`, `awk`)
- **Array operations** (splitting, iterating)
- **Multi-branch decision trees**

### Check: Inline Bash Complexity

1. **Scan all `run:` blocks** in new or modified workflows
2. **Flag blocks with complexity signals** listed above
3. **Verify no existing script already handles** the same task — if a script
   exists, the workflow should call it rather than reimplementing the logic inline

### Common Violations in TheRock

| Pattern | Should Be |
|---------|-----------|
| S3 bucket selection with if/elif/else | Python script with unit tests |
| IAM role selection with conditionals | Python script with unit tests |
| Loop over families calling `fetch_artifacts.py` per iteration | Single call to `fetch_artifacts.py` (which already accepts lists) |
| Parsing/splitting semicolon-separated inputs | Python script argument handling |

### Questions to Ask

- "Could this `run:` block be a one-line call to a Python script instead?"
- "Does an existing script already handle this logic?"
- "Are there unit tests for this logic?"

### Severity

- Complex inline bash (conditionals, loops, decision trees): **BLOCKING**
- Simple inline bash (single command, `echo`, `mkdir`): **OK**

---

## Multiple Checkouts

### The Problem

When a workflow checks out multiple repositories (e.g., rocm-systems *and*
TheRock), each checkout exists for a reason — typically the workflow needs to
build or test one repo's source using the other repo's build infrastructure.
If the wiring between checkout and consumer is wrong or missing, the workflow
silently does the wrong thing: it runs successfully but tests the wrong source.

This is especially dangerous because:
1. **CI passes** — there's no error, just a green check on untested code
2. **The diff doesn't show the absence** — a missing CMake flag or env var
   isn't visible in the diff of what *was* added
3. **It's easy to cargo-cult** — copying from an existing workflow and
   forgetting a flag that wires the two checkouts together

### Real Example: rocm-systems#3066

PR #3066 added RCCL CI workflows to rocm-systems. The workflow checked out both
rocm-systems (the repo under test) and TheRock (the build system). However, it
never passed `-DTHEROCK_ROCM_SYSTEMS_SOURCE_DIR=../` in `extra_cmake_options`,
which is the flag that tells TheRock to overlay the rocm-systems source on top
of its own submodules. Result: every CI run built and tested an unchanging
snapshot of RCCL from the pinned TheRock commit, completely ignoring the PR's
changes.

### Check: Multiple Checkout Wiring

When a workflow has more than one `actions/checkout` step:

1. **Identify each checkout's purpose** — what source does it provide?
2. **Trace how each checkout is consumed** — which subsequent steps reference
   the checked-out path? Look for:
   - CMake flags (e.g., `-D*_SOURCE_DIR=...`)
   - Environment variables (e.g., `PYTHONPATH`, `PATH` additions)
   - Explicit `working-directory:` on steps
   - Script arguments that reference the checkout path
3. **Verify no checkout is silently unused** — if a repo is checked out but
   no subsequent step references its path, that's a strong signal the wiring
   is missing
4. **Compare with existing workflows** — if a similar workflow already exists
   (e.g., `therock-ci-linux.yml`), diff the checkout + configuration steps to
   find missing flags or env vars

### Red Flags

| Signal | Likely Bug |
|--------|------------|
| Repo checked out into `path: X` but no step references `X/` | Checkout is unused — wiring missing |
| Existing workflow passes `-DFOO_SOURCE_DIR=../` but new workflow doesn't | Forgot to carry over the source-dir flag |
| Two checkouts of the same repo at different refs | Probably a copy-paste error (unless intentional, e.g., diff) |
| Checkout with `path:` but build step uses default working directory | Build is using the wrong source tree |

### Questions to Ask

- "This workflow checks out both X and Y — which steps use X's source vs Y's?"
- "The existing `foo-ci-linux.yml` passes `-DBAR_SOURCE_DIR=../`. Does this
  new workflow need the same flag?"
- "If I remove the first checkout, would the build still succeed? If yes,
  that checkout isn't wired correctly."

### Severity

- Checkout exists but source is never consumed by build/test steps: **BLOCKING**
- Checkout path inconsistency (e.g., `path: TheRock` vs hardcoded `./TheRock`): **IMPORTANT**

---

## Pinned Runner Versions

### The Rule

The [GitHub Actions style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/github_actions_style_guide.md#pin-action-runs-on-labels-to-specific-versions) says: **pin `runs-on:` labels to specific versions.**

Using `ubuntu-latest` means GitHub controls when the runner image changes,
which can break builds unexpectedly.

### Check: Runner Labels

Scan all `runs-on:` values in new or modified workflows for floating labels.

| Label | Status |
|-------|--------|
| `ubuntu-24.04` | OK — pinned |
| `ubuntu-latest` | **Flag** — should be pinned |
| `windows-latest` | **Flag** — should be pinned |
| Custom labels (e.g., `azure-linux-scale-rocm`) | OK — managed internally |

### Severity

- Using `*-latest` labels: **IMPORTANT**

---

## Reusable Workflow Changes

### The Critical Pattern

When a PR modifies a **reusable workflow** (one with `on: workflow_call`), you must verify that **all callers** are updated appropriately.

**This is the #1 source of regressions in workflow changes.**

### Check: Caller Inventory

Before approving any change to a reusable workflow:

1. **List all callers** of the modified workflow:
   ```bash
   # Find all workflows that call the modified workflow
   grep -r "uses:.*workflow-name.yml" .github/workflows/
   ```

2. **Verify each caller** either:
   - Passes any new required inputs
   - Handles any changed outputs
   - Is unaffected by the change (explain why)

3. **Check callers in other repositories** if the workflow is called cross-repo

### Questions to Ask

- "Which workflows call this reusable workflow?"
- "Were all callers updated to pass the new inputs?"
- "Were callers in other repositories (rocm-libraries, rocm-systems) considered?"

### Severity

- Callers not updated for new required inputs: **BLOCKING**
- Callers not listed/verified in PR description: **IMPORTANT**

### Example: PR #2771 Failure

PR #2771 changed `setup.yml` to use `inputs.linux_amdgpu_families` instead of `github.event.inputs.linux_amdgpu_families`, but `ci_nightly.yml` (a caller) wasn't updated to pass that input. Result: nightly workflow_dispatch stopped working.

---

## Input Propagation

### The Three Input Sources

GitHub Actions has multiple ways to receive inputs, and they are **NOT interchangeable**:

| Source | Works For | Example |
|--------|-----------|---------|
| `inputs.*` | `workflow_call` | Called by another workflow |
| `github.event.inputs.*` | `workflow_dispatch` | Manual trigger from UI |
| `github.event.client_payload.*` | `repository_dispatch` | API trigger |

### Check: Input Source Correctness

When reviewing input handling:

1. **Identify all trigger types** the workflow supports
2. **Verify each trigger type** receives inputs correctly
3. **Watch for source changes** - switching from `github.event.inputs` to `inputs` is a **breaking change** for `workflow_dispatch`

### Common Mistake

```yaml
# BEFORE: Works for workflow_dispatch
env:
  FAMILIES: ${{ github.event.inputs.amdgpu_families }}

# AFTER: Only works for workflow_call - BREAKS workflow_dispatch!
env:
  FAMILIES: ${{ inputs.amdgpu_families }}
```

### Fix: Support Both Trigger Types

```yaml
# Option 1: Coalesce with fallback
env:
  FAMILIES: ${{ inputs.amdgpu_families || github.event.inputs.amdgpu_families }}

# Option 2: Caller passes inputs explicitly (preferred for clarity)
# In the calling workflow:
uses: ./.github/workflows/setup.yml
with:
  amdgpu_families: ${{ github.event.inputs.amdgpu_families }}
```

### Questions to Ask

- "Does this workflow support both `workflow_dispatch` and `workflow_call`?"
- "If inputs changed, were both trigger paths verified?"
- "Did you test manual dispatch from the GitHub UI?"

### Severity

- Breaking `workflow_dispatch` when adding `workflow_call`: **BLOCKING**
- Input source unclear or undocumented: **IMPORTANT**

---

## Testing Trigger Paths

### Each Trigger Type is a Separate Code Path

A workflow with multiple triggers must be tested for **each trigger type**:

| Trigger | Test Method |
|---------|-------------|
| `pull_request` | Open a PR |
| `push` | Push to branch |
| `workflow_dispatch` | Manual trigger from GitHub UI |
| `workflow_call` | Trigger from another workflow |
| `schedule` | Wait for schedule (or test via dispatch) |

### Check: Trigger Coverage

1. **List all triggers** the workflow supports
2. **Verify each trigger was tested** (links to CI runs in PR description)
3. **Pay special attention to `workflow_dispatch`** - it's often forgotten

### PR Description Should Include

For workflows with multiple triggers:
```markdown
## Testing

- [x] `pull_request`: [Run #123](link)
- [x] `workflow_dispatch`: [Run #124](link)
- [x] `workflow_call` from ci.yml: [Run #125](link)
```

### Questions to Ask

- "Which trigger types does this workflow support?"
- "Was each trigger type tested?"
- "Is there a link to a successful `workflow_dispatch` run?"

### Severity

- Trigger type not tested: **BLOCKING** (for dispatch/call especially)
- Missing test evidence in PR description: **IMPORTANT**

---

## Breaking Changes

### What Constitutes a Breaking Change

Changes that can break existing callers or users:

| Change Type | Breaking? | Notes |
|-------------|-----------|-------|
| Adding required input | Yes | Callers must be updated |
| Removing input | Yes | Callers using it will fail |
| Renaming input | Yes | Same as remove + add |
| Changing input semantics | Yes | Callers may pass wrong values |
| Changing output name/format | Yes | Consumers may break |
| Changing job/step IDs | Maybe | If referenced by callers |

### Check: Breaking Change Detection

1. **Compare inputs/outputs** before and after
2. **Check for semantic changes** - same name but different meaning
3. **Verify migration path** if breaking change is intentional

### Questions to Ask

- "Does this change require updates to callers?"
- "Is there a migration path for existing users?"
- "Should this be a new workflow instead of modifying the existing one?"

### Severity

- Breaking change without caller updates: **BLOCKING**
- Breaking change without migration notes: **IMPORTANT**

---

## Permissions

### Check: Minimal Permissions

Workflows should request only the permissions they need.

```yaml
# Good: Explicit minimal permissions
permissions:
  contents: read

# Bad: Implicit write-all (default for some triggers)
# (no permissions block)

# Bad: Overly broad
permissions: write-all
```

### Questions to Ask

- "Does this workflow need write permissions?"
- "Can permissions be scoped to specific jobs instead of workflow-level?"

### Severity

- Overly broad permissions: **IMPORTANT**
- Missing explicit permissions block: **SUGGESTION**

---

## Pinned Versions

### Check: Actions Are Pinned

All third-party actions should use pinned versions:

```yaml
# Good: Pinned to commit SHA
uses: actions/checkout@8e8c483db84b4bee98b60c0593521ed34d9990e8

# Acceptable: Pinned to version tag
uses: actions/checkout@v4.1.0

# Bad: Floating tag
uses: actions/checkout@v4

# Worse: Branch reference
uses: actions/checkout@main
```

### Severity

- Using `@main` or `@latest`: **IMPORTANT**
- Using major version tag (e.g., `@v4`): **SUGGESTION** (prefer SHA or full version)

---

## Script Runtime Dependencies

### The Problem

Workflows that call Python (or other) scripts must ensure all import
dependencies are available in the CI environment. This means either:

- Pre-installed in the container/runner image
- Installed in a prior workflow step (e.g., `pip install`)
- Listed in a requirements file that a prior step installs

**This is easy to miss** because the script may work locally (where the
developer has the package installed) but fail in CI.

### Real Example: PR #3596 → Issue #3783

PR #3596 added workflow steps that call `upload_pytorch_manifest.py`, which
imports `boto3` via `storage_backend.py`. No workflow step installed `boto3`,
causing all pytorch release runs to fail with `ModuleNotFoundError: No module
named 'boto3'`.

### Check: Script Dependencies Satisfied

When a workflow step runs a Python script (`python script.py` or
`python -m module`):

1. **Trace the script's imports** — check what the script imports, including
   transitive imports (e.g., script imports `storage_backend`, which imports
   `boto3`)
2. **Verify each non-stdlib import is available** — either pre-installed in
   the container image or installed by a prior step
3. **Watch for conditional/lazy imports** — a package imported inside a
   function or `if` block may only be needed on certain code paths, making it
   easy to miss in testing
4. **Check requirements files** — if the workflow does `pip install -r
   requirements.txt`, verify the requirements file includes the needed packages

### Common Patterns in TheRock

| Package | Where It's Needed | How to Provide |
|---------|-------------------|----------------|
| `boto3` | S3 upload/download scripts | `pip install` or requirements file |
| `packaging` | Version parsing scripts | `pip install` or requirements file |
| `requests` | API-calling scripts | Usually pre-installed, but verify |

### Red Flags

- A new `run: python ...` step calling a script not previously called from
  this workflow
- A script that was refactored to use a new library (e.g., switching from
  `awscli` subprocess calls to `boto3` Python API)
- Moving a script call from one workflow to another (the new workflow may not
  have the same `pip install` steps)

### Questions to Ask

- "Does this script import anything not in the Python stdlib?"
- "Is there a `pip install` step (or requirements file) that provides those
  packages?"
- "If this script is called from a container, does the container image include
  these packages?"

### Severity

- Script will fail at runtime due to missing import: **BLOCKING**
- Import is present but version not pinned and could break: **IMPORTANT**

---

## Style

### Check: Style Guide Compliance

- [ ] Follows [GitHub Actions Style Guide](../../../TheRock/docs/development/style_guides/github_actions_style_guide.md)
- [ ] Job and step names are descriptive
- [ ] Comments explain non-obvious logic
- [ ] YAML is properly formatted

### Severity

- Style violations: **SUGGESTION** (unless egregious)

---

## Security Considerations

### Command Injection

Watch for user-controlled input in `run` blocks:

```yaml
# DANGEROUS: Direct interpolation of user input
- run: echo "${{ github.event.issue.title }}"

# SAFER: Use environment variable
- run: echo "$TITLE"
  env:
    TITLE: ${{ github.event.issue.title }}
```

### Secrets

- [ ] No secrets in workflow files (use GitHub Secrets)
- [ ] Secrets not logged or exposed in outputs
- [ ] `GITHUB_TOKEN` permissions are minimal

### Severity

- Command injection vulnerability: **BLOCKING**
- Secret exposure risk: **BLOCKING**

---

## TheRock-Specific Considerations

### Reusable Workflow Hierarchy

TheRock uses a hierarchy of reusable workflows:

```
ci.yml
├── setup.yml (generates matrix)
├── ci_linux.yml
│   ├── build_portable_linux_artifacts.yml
│   └── test_artifacts.yml
└── ci_windows.yml
    ├── build_windows_artifacts.yml
    └── test_artifacts.yml
```

When modifying any workflow in this chain:
1. Trace inputs from top to bottom
2. Trace outputs from bottom to top
3. Verify all intermediate workflows pass data correctly

### External Repository Integration

TheRock workflows are called by external repositories (rocm-libraries, rocm-systems).

When modifying workflows with `workflow_call`:
- [ ] Check if external repos call this workflow
- [ ] Verify external callers will continue to work
- [ ] Consider whether changes need coordinated rollout

### Input Naming Conventions

- `external_source_checkout`: Boolean for external repo mode
- `therock_ref`: Git ref for TheRock checkout
- `repository_override`: Override `github.repository` for testing
- `amdgpu_families`: GPU family specification

---

## Summary Checklist

**Before reviewing code:**
- [ ] Identify all triggers the workflow supports
- [ ] List all callers of modified reusable workflows
- [ ] Check PR description for test evidence per trigger type

**During code review:**
- [ ] All callers updated for input changes
- [ ] Input sources correct for each trigger type
- [ ] No breaking changes without migration path
- [ ] Script runtime dependencies available (trace imports of called scripts)
- [ ] No complex inline bash — logic with conditionals/loops/string manipulation belongs in Python scripts
- [ ] Multiple checkouts wired correctly (each checkout consumed by intended steps)
- [ ] `runs-on:` labels pinned to specific versions (not `*-latest`)
- [ ] Permissions are minimal
- [ ] Actions are pinned
- [ ] No security vulnerabilities

**Before approving:**
- [ ] Each trigger type has a passing CI run linked
- [ ] `workflow_dispatch` specifically tested (if supported)
- [ ] External repo callers considered (if applicable)
