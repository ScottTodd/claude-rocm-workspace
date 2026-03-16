# Branch Review: multi-arch-configure

* **Branch:** `multi-arch-configure`
* **Base:** `7383429ae30b3f93f5a3a7`
* **Reviewed:** 2026-03-16
* **Commits:** 16 commits

---

## Summary

New `configure_multi_arch_ci.py` script replacing the multi-arch codepath
in `configure_ci.py`. Implements a pipeline of pure data transformations
(CIInputs → skip gate → job decisions → target selection → build configs →
outputs) with typed dataclasses at every boundary. Wired into
`multi_arch_ci.yml` via a new `setup_multi_arch.yml` workflow.

**Net changes:** +1947 lines, -33 lines across 5 files

---

## Overall Assessment

**✅ APPROVED** — Well-structured pipeline with clear separation of concerns,
good test coverage (90%), and thoughtful design decisions. A few issues to
address before sending upstream.

**Strengths:**

- Pipeline architecture: each step is a pure function of typed dataclasses,
  independently testable
- GitContext extraction: `configure()` is fully pure, no git calls
- Early-return priority chain in `_determine_test_type` makes precedence
  explicit
- Structural tests that don't break when matrix data values change
- Data invariant tests for `amdgpu_family_matrix.py` catch schema issues
  upstream

**Issues:**

- One stale docstring
- One fail-fast gap in `from_environ()`
- Workflow `fromJSON` repetition could be fragile

---

## Detailed Review

### 1. configure_multi_arch_ci.py

#### ⚠️ IMPORTANT: Stale docstring — test_type values

Line 44: `test_type: "smoke" or "full"` — should be
`"quick", "standard", "comprehensive", or "full"` per the PR #3992 naming
adopted throughout the rest of the script.

**Recommendation:** Update the module docstring to match the actual values.

#### ⚠️ IMPORTANT: `from_environ()` uses `sys.exit(1)` instead of raising

Lines 153-157: `sys.exit(1)` when `GITHUB_REF_NAME` is not set. Per the
project's Python style guide (fail-fast behavior), this should raise an
exception. `sys.exit()` makes the function untestable and bypasses the
call stack.

**Recommendation:** `raise RuntimeError("GITHUB_REF_NAME is not set")`.
The `from_environ` tests already avoid hitting this path, but it should
still be a proper exception.

#### 💡 SUGGESTION: `expand_build_configs` calls `get_all_families_for_trigger_types` again

Both `select_targets` (line 642) and `expand_build_configs` (line 790)
call `get_all_families_for_trigger_types(["presubmit", "postsubmit", "nightly"])`.
These return the same data. Could pass it through from `configure()` to
avoid the redundant call, but it's cheap and not a correctness issue.

#### 💡 SUGGESTION: `_filter_families_by_platform` parameter named `lookup_matrix`

Line 611: The parameter is still named `lookup_matrix` while the rest of the
file uses `all_families` for the same data. Minor inconsistency from
`select_targets`, which wasn't part of the rename sweep.

#### 💡 SUGGESTION: `BuildConfig.to_dict()` could use `dataclasses.asdict()`

Lines 374-385: Manual dict construction mirrors the field list. Using
`dataclasses.asdict()` would auto-update if fields are added. Minor —
the explicit version is arguably clearer and avoids surprises with nested
dataclasses.

### 2. setup_multi_arch.yml

#### 💡 SUGGESTION: Consider pinning `python` version

Line 77: `run: python ./build_tools/github_actions/configure_multi_arch_ci.py`
uses the system Python. The existing `setup.yml` does the same, so this is
consistent, but worth noting if Python 3.12+ features are used (union types
like `X | None` require 3.10+, `ubuntu-24.04` ships 3.12 so this is fine).

### 3. multi_arch_ci.yml

#### ⚠️ IMPORTANT: Repeated `fromJSON` calls on the same output

Lines 84-91 and 115-122: `fromJSON(needs.setup.outputs.linux_build_config)`
is called 7 times for linux and 7 times for windows. If the JSON is
malformed (empty string when `linux_build_enabled` is somehow true), all
7 calls fail with unhelpful error messages.

GitHub Actions evaluates expressions lazily per-field, so there's no
performance concern. But the repetition makes the YAML harder to read
and increases the surface area for copy-paste errors between linux and
windows blocks.

**Recommendation:** Not blocking — this is a known trade-off from removing
the matrix. A future improvement could use a reusable workflow input that
accepts the whole JSON object and unpacks it internally.

### 4. Tests (configure_multi_arch_ci_test.py)

#### 💡 SUGGESTION: `_inputs()` helper duplicated in two test classes

`TestCheckSkipCI._inputs()` and `TestDecideJobs._inputs()` are identical.
Could be a module-level helper like `_run_from_environ`.

#### 📋 FUTURE WORK: End-to-end test without mocks

`TestConfigurePipeline.test_pipeline_calls_all_steps` mocks all step
functions. Now that `configure()` takes `GitContext` directly, an
end-to-end test that constructs real `CIInputs` + `GitContext` and
asserts on `CIOutputs` fields would be valuable — exercising the actual
step implementations together rather than just verifying they're called.

### 5. amdgpu_family_matrix_test.py

No issues. Clean schema validation tests.

---

## Recommendations

### ❌ REQUIRED (Blocking):

(none)

### ✅ Recommended:

1. Fix stale docstring: `test_type` values on line 44
2. Replace `sys.exit(1)` with `raise RuntimeError` in `from_environ()`

### 💡 Consider:

1. Rename `lookup_matrix` → `all_families` in `_filter_families_by_platform`
2. Extract shared `_inputs()` helper in tests
3. Add end-to-end test for `configure()` without mocks

### 📋 Future Follow-up:

1. Reduce `fromJSON` repetition in workflow YAML (reusable workflow or
   intermediate variable)
2. `format_summary` needs real markdown (tracked as next step)

---

## Testing Recommendations

- Run `workflow_dispatch` on fork with default inputs (release, all families)
- Run `workflow_dispatch` with explicit `prebuilt_stages` and `baseline_run_id`
- Run `workflow_dispatch` with ASAN variant to verify windows is skipped
- Verify `push` trigger on fork branch produces correct family set
- Check step summary output in GitHub Actions UI

---

## Conclusion

**Approval Status: ✅ APPROVED**

Two recommended fixes (stale docstring, sys.exit) are minor and can be
addressed before sending the PR upstream. The architecture is sound, test
coverage is strong, and the workflow integration is clean. Ready for
validation via test runs on a fork.
