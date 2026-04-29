# PR Review: #3126 — Deb and rpm install sanity check

* **PR:** https://github.com/ROCm/TheRock/pull/3126
* **Author:** jonatluu
* **Branch:** `users/jonatluu/install_test` → `main`
* **Reviewed:** 2026-04-27
* **Status:** OPEN

---

## Summary

Adds a new reusable workflow `test_native_linux_packages_install.yml` that validates native Linux package (deb/rpm) installation across Ubuntu, RHEL, and SLES containers. The workflow runs the existing `native_linux_package_install_test.py` script against a package repository URL, supporting both `sanity` and `full` test types.

**Net changes:** +237 lines, -0 lines across 1 file

**Note:** The PR description mentions changes to `build_native_linux_packages.yml` and `native_linux_package_install_test.py`, but only the new workflow file is in the diff. Those changes may be in separate PRs or already merged.

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The workflow achieves its goal but has significant inline bash complexity that violates the project's [GitHub Actions style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/github_actions_style_guide.md#prefer-python-scripts-over-inline-bash). Three steps contain conditionals and case statements that should be in Python scripts.

**Strengths:**
- Good multi-distro coverage (Ubuntu, RHEL, SLES)
- Clean separation of concerns: `prepare_install_context` job derives metadata, main job runs the test
- Reusable via `workflow_call` with sensible defaults
- Action SHA-pinned (`actions/checkout@de0fac...`)
- Runner labels are pinned (`ubuntu-24.04`, not `ubuntu-latest`)
- Script dependencies installed via `requirements.txt` in a venv (PEP 668 compliant)
- Referenced scripts all exist and accept the arguments being passed

**Issues:**
- 3 BLOCKING: Complex inline bash in 3 steps
- 1 IMPORTANT: Direct expression interpolation in `run:` blocks instead of env vars
- 1 SUGGESTION: Prepare job could be folded into the main job

---

## Detailed Review

### 1. Complex inline bash

#### ❌ BLOCKING: "Install System Prerequisites" step has nested conditionals

Lines ~115–155 of the new file contain a multi-branch `if/elif/else` with nested inner conditionals (`if [ "$TEST_TYPE" = "full" ]` inside each branch). This is the most complex inline bash in the workflow — three package managers, each with a conditional extra-packages block.

Per the [style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/github_actions_style_guide.md#prefer-python-scripts-over-inline-bash), logic with conditionals belongs in a Python script.

**Required action:** Extract to a Python script (e.g., `install_system_prerequisites.py`) that takes `--os-profile` and `--test-type` and calls the appropriate package manager via `subprocess`. This makes the logic testable and consistent with the project's existing packaging scripts.

*Acknowledged tradeoff:* Package installation is inherently shell-oriented, so the Python script would be a thin wrapper around subprocess calls. But it becomes testable and avoids the 40-line inline bash block.

#### ❌ BLOCKING: "Derive package type and GPU architecture" step uses case statement

```yaml
case "${{ inputs.os_profile }}" in
  ubuntu*|debian*) PKG_TYPE="deb" ;;
  *) PKG_TYPE="rpm" ;;
esac
```

This `case` statement is a conditional. The same logic could live in `get_url_repo_params.py` (which is already called in the same step) or a small helper. The `extract-gfx-arch` subcommand is already Python — add a `derive-pkg-type` subcommand that also outputs `pkg_type=...` to `$GITHUB_OUTPUT`.

**Required action:** Move the `case` logic into the Python script that's already being called.

#### ❌ BLOCKING: "Test Report" step has case statement and conditionals

Lines ~198–237 contain a `case` statement selecting message strings and an `if/else` on step outcome. This is moderate complexity but still violates the guideline.

**Required action:** Move the report logic into a Python script or fold it into `native_linux_package_install_test.py` itself (the script could print its own pass/fail summary).

---

### 2. Expression interpolation in run blocks

#### ⚠️ IMPORTANT: Direct `${{ inputs.os_profile }}` in bash instead of env vars

Several `run:` blocks use `${{ inputs.os_profile }}` and `${{ env.PKG_TYPE }}` as direct expression interpolation instead of shell variables. The workflow already sets `OS_PROFILE` and `PKG_TYPE` as env vars, but they're not consistently used.

For example, the "Install System Prerequisites" step uses:
```yaml
if [ "${{ env.PKG_TYPE }}" = "deb" ]; then
```
instead of:
```bash
if [ "$PKG_TYPE" = "deb" ]; then
```

And:
```yaml
elif [[ "${{ inputs.os_profile }}" == sles* ]]; then
```
instead of:
```bash
elif [[ "$OS_PROFILE" == sles* ]]; then
```

While the injection risk is low (inputs come from choice dropdowns or trusted callers), using `${{ }}` interpolation in `run:` blocks is a security anti-pattern. If a `workflow_call` caller passes an untrusted value, the expression is interpolated *before* the shell parses it. Using env vars (`$OS_PROFILE`, `$PKG_TYPE`) is safer and more consistent — the env vars are already defined.

**Recommendation:** Replace all `${{ inputs.* }}` and `${{ env.* }}` in `run:` blocks with their corresponding shell env vars (`$OS_PROFILE`, `$PKG_TYPE`, `$REPO_URL`, etc.).

---

### 3. Architecture decisions

#### 💡 SUGGESTION: Fold `prepare_install_context` into the main job

The `prepare_install_context` job runs on a separate `ubuntu-24.04` runner just to derive `pkg_type` (a case statement) and `gfx_arch` (a Python one-liner). This adds job scheduling overhead. Both could run as early steps in the main job since the main job already checks out the repo and has Python available (after `setup_python_cmd.sh`).

However, the current structure has the advantage of making the container image selection expression cleaner (it doesn't need the derived values). If keeping two jobs, no action needed — just noting the tradeoff.

---

### 4. Container configuration

#### 💡 SUGGESTION: Document why `--privileged` is needed

The container runs with `--privileged` and `--ipc host`. These are presumably needed for GPU device access during the `full` test type (RDHC verification). A brief comment in the workflow would help future maintainers understand this choice.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Extract "Install System Prerequisites" bash logic into a Python script
2. Move `case` statement for package type derivation into the existing Python call (`get_url_repo_params.py`)
3. Move "Test Report" logic into a Python script or the existing test script

### ✅ Recommended:

4. Use shell env vars (`$OS_PROFILE`, `$PKG_TYPE`) in `run:` blocks instead of `${{ }}` expression interpolation

### 💡 Consider:

5. Fold `prepare_install_context` job into the main job to reduce scheduling overhead
6. Add a comment explaining why `--privileged` is needed on the container

---

## Testing Recommendations

The PR body includes links to several test runs — good coverage:
- No-verify nightly: runs 23602292215, 23610612186
- Verify nightly: runs 23785348518 (rpm), 23778928188 (deb)
- Full test workflow: runs 24353145372, 24571097705, 24569164778

Both `workflow_call` and `workflow_dispatch` triggers exist. The test runs appear to cover `workflow_dispatch`. Confirm that a `workflow_call` invocation (from a parent workflow) has also been tested.

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The workflow is functionally sound and the test coverage is good, but three steps violate the project's inline bash complexity rule. Moving the conditional logic into Python scripts will make the code testable, consistent with the project style, and easier to maintain. The expression interpolation cleanup is a secondary concern but improves security posture.
