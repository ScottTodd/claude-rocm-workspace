# GitHub Actions Review Guidelines

Checklist for reviewing PRs that modify GitHub Actions workflows.

## Summary

| Check | Automatable | Severity | Notes |
|-------|-------------|----------|-------|
| [All callers updated](#reusable-workflow-changes) | Partial | BLOCKING | Can list callers, can't verify correctness |
| [Input propagation correct](#input-propagation) | No | BLOCKING | Requires understanding data flow |
| [All trigger paths tested](#testing-trigger-paths) | No | BLOCKING | Each path may behave differently |
| [No breaking changes to callers](#breaking-changes) | No | BLOCKING | Semantic changes are subtle |
| [Permissions minimal](#permissions) | Yes | IMPORTANT | Can scan for overly broad permissions |
| [Actions pinned](#pinned-versions) | Yes | IMPORTANT | Can detect `@main` or `@latest` |
| [Style guide followed](#style) | Partial | SUGGESTION | Linters can catch some issues |

**What reviewers must check manually:**
- Data flow through workflow_call chains
- Semantic correctness of input/output mappings
- Coverage of all trigger types (dispatch, call, PR, push, schedule)
- Regression to existing callers when modifying shared workflows

**What automation can help with:**
- Listing all callers of a reusable workflow
- Detecting unpinned action versions
- Scanning for overly broad permissions
- Style/lint checks (actionlint)

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
- [ ] Permissions are minimal
- [ ] Actions are pinned
- [ ] No security vulnerabilities

**Before approving:**
- [ ] Each trigger type has a passing CI run linked
- [ ] `workflow_dispatch` specifically tested (if supported)
- [ ] External repo callers considered (if applicable)
