# PR Review: #4123 — configure_multi_arch_ci.py pipeline

* **PR:** https://github.com/ROCm/TheRock/pull/4123
* **Branch:** `multi-arch-configure`
* **Base:** `main`
* **Reviewed:** 2026-03-24 (updated after addressing feedback)
* **Key files:** 4 new, 5 modified

---

## Summary

Forks multi-arch CI configuration from `configure_ci.py` into a new
`configure_multi_arch_ci.py` with a pipeline architecture: parse inputs,
check skip gate, decide jobs, select targets, expand build configs, write
outputs. Adds a companion summary formatter, a comprehensive test suite,
a `setup_multi_arch.yml` reusable workflow, and updates
`multi_arch_ci.yml` / `multi_arch_ci_linux.yml` / `multi_arch_ci_windows.yml`
to consume the new config. Old `generate_multi_arch_matrix` code is removed
from `configure_ci.py`.

---

## Overall Assessment

**✅ APPROVED** — All blocking and most important issues addressed.

**Strengths:**

- Clean pipeline design: each step is a pure function of typed dataclasses,
  making the logic testable without environment access
- Excellent `TestBuildConfigWorkflowContract` tests that regex-scan YAML for
  `fromJSON(inputs.build_config).FIELD` and assert exact match against
  `BuildConfig` dataclass fields — catches Python/YAML drift at test time
- No `sys.exit()` calls; errors are raised as exceptions
- `BuildConfig.to_dict()` field set matches workflow YAML references exactly
  (verified programmatically)
- Tests avoid hardcoding family names from `amdgpu_family_matrix.py`,
  asserting on structural properties instead
- Cleanup of `configure_ci.py` is complete — no remaining
  `generate_multi_arch_matrix` references
- Summary module is now a pure formatter (no env var access)

---

## Resolved Issues

### ~~❌ BLOCKING: Lazy `import os` buried inside `_repo_slug()`~~

**Resolved.** Replaced `_repo_slug()` function and `import os` with a
hardcoded `_REPO_SLUG = "ROCm/TheRock"` constant. Prebuilt artifacts
always come from ROCm/TheRock workflow runs. TODO(#3399) added for when
`baseline_run_id` carries a repo qualifier.

### ~~⚠️ IMPORTANT: `_parse_comma_list` lowercases — may corrupt stage names~~

**Investigated, no action needed.** Stage names in `BUILD_TOPOLOGY.toml`
are all lowercase (`foundation`, `compiler-runtime`, etc.).
`artifact_manager.py copy` does exact dict key lookup against those names.
Lowercasing is safe and actually protects against user typos in
workflow_dispatch input.

### ~~💡 SUGGESTION: `test_build_config_to_dict_round_trips` name misleading~~

**Resolved.** Renamed to `test_build_config_to_dict_has_all_fields`.

### ~~💡 SUGGESTION: `TestFormatSummary` tests only check "does not raise"~~

**Resolved.** Both tests now assert the output starts with
`## Multi-Arch CI Configuration`. Docstrings explain why we don't assert
more (output is markdown for humans, not a contract — more assertions
would create change-detector tests).

---

## Remaining Items

### 💡 SUGGESTION: No test for `write_outputs` contract

`write_outputs()` is the bridge between the pipeline and GITHUB_OUTPUT.
The output variable names (`enable_build_jobs`, `linux_build_config`,
etc.) must match what `setup_multi_arch.yml` reads as step outputs. A
contract test (similar to `TestBuildConfigWorkflowContract`) scanning
the YAML for `steps.configure.outputs.X` and comparing against the keys
in `write_outputs` would catch drift.

### 💡 SUGGESTION: YAML comment on `!cancelled() && !failure()` gate

Both Linux and Windows workflows have `build_multi_arch_stages` with
`needs: copy_prebuilt_stages` and `if: ${{ !cancelled() && !failure() }}`.
If `copy_prebuilt_stages` is *skipped* (prebuilt_stages is empty), the
condition still passes (skipped is neither cancelled nor failed). This is
correct but a subtle GHA semantics point worth a comment.

### 📋 FUTURE WORK

1. Per-platform validation for workflow_dispatch family names (tracked by
   skipped test `test_workflow_dispatch_wrong_platform_raises`).
2. Job group pruning (skip pytorch when only JAX edited, etc.) — tracked
   in TODO comments.
3. Automatic `baseline_run_id` derivation from parent workflow run
   (tracked via #3399).
4. `write_outputs` contract test.

---

## Testing Recommendations

- Tests pass: 46 passed, 1 skipped (the intentional TODO skip).
- Run `multi_arch_ci.yml` via `workflow_dispatch` with:
  - Default inputs (empty families) to verify the "nothing to build" path
  - `linux_amdgpu_families=gfx110x` to verify single-platform build
  - `prebuilt_stages=foundation` + `baseline_run_id=<valid_id>` to verify
    the copy-prebuilt path
- Run on a PR with `ci:run-multi-arch` label to verify the opt-in gate.

---

## Conclusion

**Approval Status: ✅ APPROVED**

All blocking and important issues have been addressed. The architecture
is clean, the test suite is well-designed (especially the YAML contract
tests), and the cleanup is complete. Remaining items are suggestions and
future work.
