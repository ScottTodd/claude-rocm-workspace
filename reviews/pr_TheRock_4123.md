# PR Review: #4123 — configure_multi_arch_ci.py pipeline

* **PR:** https://github.com/ROCm/TheRock/pull/4123
* **Branch:** `multi-arch-configure`
* **Base:** `main`
* **Reviewed:** 2026-03-24
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

**⚠️ CHANGES REQUESTED** — One blocking issue with the summary module.
Architecture and test quality are strong overall.

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

**Issues:**

- 1 blocking (summary module import)
- 3 important
- 4 suggestions

---

## Detailed Review

### 1. configure_multi_arch_ci_summary.py

#### ❌ BLOCKING: Lazy `import os` buried inside `_repo_slug()`

`_repo_slug()` (line 202) has `import os` inside the function body rather
than at module top level. The module already depends on `os` implicitly
(it runs in a GHA environment reading env vars). Burying the import inside
a helper function is non-obvious and inconsistent with the rest of the
codebase.

More importantly, this is the *only* import that reads from the environment
in the summary module — the stated design goal is that the summary module
is a pure formatter. `_repo_slug()` breaks that by reaching into
`os.environ`.

**Required action:** Move `import os` to the top of the file. Consider
passing `repo_slug` as a parameter from the caller (or from `CIInputs`)
to keep the module pure, or at minimum document why the env access is
acceptable here.

---

### 2. configure_multi_arch_ci.py

#### ⚠️ IMPORTANT: `_parse_comma_list` lowercases names — may silently corrupt family names with mixed case

`_parse_comma_list` (line 72) lowercases all names. This is used for both
`linux_amdgpu_families` and `prebuilt_stages`. Family names in
`amdgpu_family_matrix.py` are already lowercase (verified: `gfx94x`,
`gfx110x`, etc.), so this works today.

However, stage names might not be lowercase (e.g., `Compiler-Runtime`).
If `prebuilt_stages` values are case-sensitive in `BUILD_TOPOLOGY.toml` or
downstream, lowercasing silently corrupts them.

**Recommendation:** Either:
- Split `_parse_comma_list` into two variants (one that lowercases for
  family names, one that preserves case for stage names), or
- Validate that stage names are case-insensitive downstream and document
  the assumption.

#### ⚠️ IMPORTANT: `should_skip_ci` for push events does not check the `ci:run-multi-arch` label

The skip gate (line 443) requires `ci:run-multi-arch` for PRs but not
for push events. Push events on `main` and `multi_arch/**` branches
(per `multi_arch_ci.yml` triggers) always run CI. This is likely
intentional since push events can't have PR labels, but the docstring
(line 434-435) only mentions `pull_request` label behavior. If someone
pushes to `multi_arch/bringup1` and expects the same skip-unless-opted-in
behavior as PRs, they'd be surprised.

**Recommendation:** Add a comment in `should_skip_ci` explicitly stating
that push events always run (no opt-in label required) and why.

#### ⚠️ IMPORTANT: `to_dict()` serializes `prebuilt_stages` as comma-joined string but `per_family_info` as a list

`BuildConfig.to_dict()` (line 374) joins `prebuilt_stages` as
`",".join(self.prebuilt_stages)` producing a string, while
`per_family_info` stays as a list. The YAML consumers treat
`prebuilt_stages` as a string (`!= ''` check on line 30 of both
linux/windows workflows) and `per_family_info` as JSON
(`fromJSON(...).per_family_info` for matrix expansion).

This *works* but the asymmetry is a source of future confusion. If someone
adds a new list field and follows the `per_family_info` pattern (keep as
list), the YAML `!= ''` gate would break because `fromJSON` of a JSON
array is never `''`.

**Recommendation:** Add a comment on `to_dict()` explaining the
serialization convention: list fields that need YAML `!= ''` gating
must be comma-joined strings; list fields consumed by `fromJSON` matrix
expansion stay as lists.

---

### 3. configure_multi_arch_ci_test.py

#### 💡 SUGGESTION: `test_build_config_to_dict_round_trips` name is misleading

The test (line 557) checks that `to_dict()` keys match dataclass field
names but doesn't actually round-trip (deserialize back to a
`BuildConfig`). The name implies a serialize+deserialize cycle. Consider
renaming to `test_build_config_to_dict_has_all_fields`.

#### 💡 SUGGESTION: `TestFormatSummary` tests only check "does not raise"

The two summary tests (lines 717, 721) verify the function doesn't crash
but don't assert on any output content. A test that at minimum checks the
header line (`## Multi-Arch CI Configuration`) would catch accidental
empty output.

#### 💡 SUGGESTION: No test for `write_outputs` contract

`write_outputs()` is the bridge between the pipeline and GITHUB_OUTPUT.
The output variable names (`enable_build_jobs`, `linux_build_config`,
etc.) must match what `setup_multi_arch.yml` reads as step outputs. A
contract test (similar to `TestBuildConfigWorkflowContract`) scanning
the YAML for `steps.configure.outputs.X` and comparing against the keys
in `write_outputs` would catch drift.

---

### 4. Workflow YAML

#### 💡 SUGGESTION: `copy_prebuilt_stages` needs dependency from `build_multi_arch_stages`

Both Linux and Windows workflows have `build_multi_arch_stages` with
`needs: copy_prebuilt_stages` and `if: ${{ !cancelled() && !failure() }}`.
This correctly gates the build on prebuilt copy completion. However, if
`copy_prebuilt_stages` is *skipped* (its `if` is false because
`prebuilt_stages == ''`), the `!cancelled() && !failure()` condition still
passes (skipped is neither cancelled nor failed). This is the correct
behavior but worth a YAML comment since it's a subtle GHA semantics point.

---

### 5. Cleanup completeness

`generate_multi_arch_matrix` is fully removed from `configure_ci.py` and
its test file. No remaining references found in the codebase. The two
remaining `multi_arch` references in `configure_ci.py` (line 191: branch
name pattern for non-long-lived branches; line 592: summary formatting
comment) are about the *workflow*, not the removed function — these are
fine to keep.

---

### 6. Security

No concerns found:
- No `eval`/`exec` or command injection vectors
- `fromJSON(inputs.build_config)` values are set by the setup job (not
  user-controlled PR body text)
- No secrets in committed files
- OIDC role assumption is gated on `github.repository == 'ROCm/TheRock'`
  and not-a-fork

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Move `import os` to top level in `configure_multi_arch_ci_summary.py`
   and consider passing `repo_slug` as a parameter to keep the module pure.

### ✅ Recommended:

1. Audit `_parse_comma_list` lowercasing for `prebuilt_stages` — confirm
   stage names are case-insensitive downstream or split the helper.
2. Document in `should_skip_ci` that push events always run (no label
   required).
3. Add a comment on `to_dict()` explaining the string-vs-list
   serialization convention.

### 💡 Consider:

1. Rename `test_build_config_to_dict_round_trips` to match what it
   actually tests.
2. Add minimal content assertions to `TestFormatSummary`.
3. Add a `write_outputs` key contract test (scan YAML for
   `steps.configure.outputs.X` vs. Python output keys).
4. Add a YAML comment on the `!cancelled() && !failure()` gate explaining
   that skipped `copy_prebuilt_stages` is intentionally allowed through.

### 📋 Future Follow-up:

1. Per-platform validation for workflow_dispatch family names (the skipped
   test `test_workflow_dispatch_wrong_platform_raises` tracks this).
2. Job group pruning (skip pytorch when only JAX edited, etc.) — tracked
   in TODO comments.
3. Automatic `baseline_run_id` derivation from parent workflow run
   (tracked via #3399).

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

**Approval Status: ⚠️ CHANGES REQUESTED**

One blocking issue (buried `import os` / impure summary module). The
remaining items are important-but-not-blocking recommendations. After
fixing the blocking issue, this is ready for human review. The
architecture is clean, the test suite is well-designed (especially the
YAML contract tests), and the cleanup is complete.
