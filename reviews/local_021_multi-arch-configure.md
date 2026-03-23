# Code Review: multi-arch-configure branch

**Branch:** `multi-arch-configure` (34 commits since main)
**Reviewer:** Claude
**Date:** 2026-03-23

## Summary

This branch creates a new `configure_multi_arch_ci.py` script that replaces the multi-arch codepath in `configure_ci.py` with a pipeline architecture. Key changes:

- New pipeline script with 6 steps (parse inputs, skip gate, job decisions, target selection, matrix expansion, output formatting)
- New `setup_multi_arch.yml` workflow
- Updated `multi_arch_ci.yml`/linux/windows to consume a single `build_config` JSON instead of individual matrix fields
- Removed ~500 lines of multi-arch code from `configure_ci.py`
- Summary formatting in separate module (`configure_multi_arch_ci_summary.py`)
- 46 tests with reported 90% coverage

## Overall Assessment

The architecture is a significant improvement over the old approach — typed dataclasses, pure functions between steps, clean separation of concerns. The test suite is well-structured and avoids the change-detector anti-pattern by testing structural properties rather than hardcoded data values.

There are two blocking bugs in the Windows workflow YAML (incomplete migration) and one in the top-level `multi_arch_ci.yml`. Several important items around edge cases and naming are also noted.

---

## Detailed Review

### 1. Workflow YAML — Incomplete Migration

#### ❌ BLOCKING: `multi_arch_ci_windows.yml` lines 127-163 — Three references still use old `inputs.*` fields

The `build_python_packages` and `build_pytorch_wheels_per_family` jobs in the Windows workflow were **not migrated** to the `fromJSON(inputs.build_config).*` pattern. These still reference:

- `inputs.expect_failure` (line 130) — should be `fromJSON(inputs.build_config).expect_failure`
- `inputs.artifact_group` (line 133) — should be `fromJSON(inputs.build_config).artifact_group`
- `inputs.dist_amdgpu_families` (line 134) — should be `fromJSON(inputs.build_config).dist_amdgpu_families`
- `inputs.build_pytorch` (line 148) — should be `fromJSON(inputs.build_config).build_pytorch`
- `inputs.matrix_per_family_json` (line 152) — should be `fromJSON(inputs.build_config).per_family_info`

These fields no longer exist as workflow_call inputs. The `build_python_packages` job will have a vacuously-true `if` condition (undefined `inputs.expect_failure` evaluates as falsy, `== false` is true), and the artifact_group/amdgpu_families will be empty strings. **This will cause silent failures or wrong behavior at runtime.**

#### ❌ BLOCKING: `multi_arch_ci.yml` line 101 — Stale `matrix.variant` reference

```yaml
build_pytorch: ${{ matrix.variant.build_pytorch == true }}
```

The `matrix` strategy block was removed from `windows_build_and_test`, so `matrix.variant` is undefined. This will silently evaluate to false, meaning Windows pytorch builds will **never** run.

Additionally, the Windows workflow still declares `build_pytorch` as a separate `inputs` field (line 23-25 of `multi_arch_ci_windows.yml`), but the new architecture embeds it in `build_config`. This is a half-migrated state.

### 2. Python Script — `configure_multi_arch_ci.py`

#### Architecture and Data Flow

The pipeline architecture is clean: `CIInputs` + `GitContext` -> `should_skip_ci` -> `decide_jobs` -> `select_targets` -> `expand_build_configs` -> `CIOutputs`. Frozen dataclasses enforce immutability between steps. The `configure()` function is the primary testable entry point.

#### ⚠️ IMPORTANT: `from_environ()` — Missing `GITHUB_EVENT_NAME` validation

`event_name` defaults to `""` if `GITHUB_EVENT_NAME` is unset (line 142), but `branch_name` raises `RuntimeError` if unset (lines 144-145). An empty `event_name` will fall through all the `is_*` property checks silently until `select_targets` raises `ValueError("Unsupported event type: ''")`. This is fail-fast in practice, but the error message is misleading — it points at `select_targets` instead of the missing environment variable.

#### 💡 SUGGESTION: `_parse_comma_list` lowercasing — Potential mismatch with stage names

`_parse_comma_list` lowercases all values (line 74). This is correct for GPU family names (which are case-insensitive), but it's also used for `prebuilt_stages` (line 563). If stage names in `BUILD_TOPOLOGY.toml` are case-sensitive (e.g., "Foundation" vs "foundation"), this could cause mismatches.

#### 💡 SUGGESTION: `should_skip_ci` — Skip message inaccuracy

The summary formatting in `_format_skipped` always says "no CI-relevant files changed" (line 69-73 of summary module), but CI can also be skipped due to missing `ci:run-multi-arch` label or `ci:skip` label. The skip reason isn't passed through to the summary.

#### 💡 SUGGESTION: `select_targets` — `gfx*` label parsing truncates at `-`

Line 692: `target = label.split("-")[0]`. A label like `gfx94x-dcgpu` would be treated as `gfx94x`. This is likely intentional (labels are family-level, not target-level), but the truncation behavior should be documented.

#### 💡 SUGGESTION: `expand_build_configs` — Redundant `get_all_families_for_trigger_types` call

`select_targets` calls `get_all_families_for_trigger_types(["presubmit", "postsubmit", "nightly"])` and `expand_build_configs` calls it again. Consider passing the family data through the pipeline to avoid the redundancy.

#### 💡 SUGGESTION: `write_outputs` — Lazy import for circular dependency

Line 870: `from configure_multi_arch_ci_summary import format_summary` inside the function body. Consider extracting the dataclasses into a `configure_multi_arch_ci_types.py` module that both scripts import, eliminating the circular dependency. Not urgent.

#### 📋 FUTURE WORK: `BuildConfig.to_dict()` — `prebuilt_stages` type mismatch

`prebuilt_stages` is a `list[str]` on the dataclass but serialized as a comma-separated string in `to_dict()` (line 377). The workflow YAML then checks `fromJSON(inputs.build_config).prebuilt_stages != ''` (string comparison). This works but the Python side models it as a list while the consumer treats it as a string. Keep the types consistent as the system evolves.

### 3. Summary Module — `configure_multi_arch_ci_summary.py`

#### 💡 SUGGESTION: `_repo_slug` — Inline `import os`

Line 217: `import os` inside the function body. The `os` module is already used elsewhere in the codebase. Move it to the module top level.

#### ⚠️ IMPORTANT: `_append_build_rocm` — `build_variant` parameter unused

The `build_variant` parameter is passed to `_append_build_rocm` (line 141) but never used in the function body. Remove the unused parameter.

### 4. Tests — `configure_multi_arch_ci_test.py`

#### Test quality

The tests are well-structured overall:
- Each pipeline step has its own test class
- Tests construct dataclasses directly (no environment mocking except `from_environ` tests)
- Structural assertions avoid hardcoding specific family names (good — avoids change-detector tests)
- The `TestBuildConfigWorkflowContract` class is an excellent pattern — regex-matching YAML field references against Python dataclass fields catches drift at test time

#### ⚠️ IMPORTANT: `test_pipeline_calls_all_steps` — Over-mocking

This test (line 743) mocks 4 of the 5 pipeline steps to verify they're called. This is a wiring test that will break if any step is renamed or the call signature changes, but doesn't verify any behavior. The value is low because `test_skipped_outputs` and other integration tests already exercise the pipeline. Consider replacing with a more meaningful integration test or documenting the rationale.

#### ⚠️ IMPORTANT: Missing test: `write_outputs` coverage

`write_outputs` is not tested. A test that patches `gha_set_output` and `gha_append_step_summary` and verifies the output dict shape would catch serialization bugs (like the `to_dict` key mismatch).

#### 💡 SUGGESTION: Missing test: `from_environ` with missing `GITHUB_REF_NAME`

The code raises `RuntimeError` when `GITHUB_REF_NAME` is unset, but no test exercises this error path.

#### 📋 FUTURE WORK: `test_windows_workflow_uses_all_fields` — Skipped

Skipped with a note about Windows not building pytorch yet. However, the Windows workflow **does** reference `build_pytorch` and `matrix_per_family_json`. Once the Windows workflow is fully migrated (see blocking bug #1), this skip should be removed.

### 5. Workflow YAML — `setup_multi_arch.yml`

Clean and minimal. The `fetch-depth: 2` for diff support is correct. The `BUILD_VARIANT` env var pass-through is the right approach for `workflow_call` inputs that don't come from the event payload.

The `prebuilt_stages` and `baseline_run_id` workflow_dispatch inputs on `multi_arch_ci.yml` are no longer passed to `setup_multi_arch.yml` — correct, because the new script reads them from `GITHUB_EVENT_PATH` directly.

### 6. Security

The `build_config` JSON blob is constructed by the Python script and passed through GHA outputs. Shell interpolation via `${{ fromJSON(...) }}` uses values from workflow_dispatch inputs (trusted) or the script's own logic (also trusted). PR labels are only used for string comparisons, not interpolated into shell commands. **No injection risk identified.**

### 7. Cleanup of `configure_ci.py`

The removal of `generate_multi_arch_matrix`, the `multi_arch` parameter from `matrix_generator`, and the `MULTI_ARCH` environment variable is clean. The `format_variants` cleanup is correct.

#### 💡 SUGGESTION: Verify `setup.yml` doesn't have a dangling `multi_arch` input

The old caller passed `multi_arch: true` to `setup.yml`. This input was removed from the caller side but verify `setup.yml` still has a default or no longer has the input.

---

## Recommendations

### By Severity

**❌ BLOCKING (must fix):**
1. Fix `multi_arch_ci_windows.yml` lines 127-163: migrate `build_python_packages` and `build_pytorch_wheels_per_family` to use `fromJSON(inputs.build_config).*`
2. Fix `multi_arch_ci.yml` line 101: remove stale `matrix.variant.build_pytorch == true` reference — either derive from `fromJSON(needs.setup.outputs.windows_build_config).build_pytorch` or remove the `build_pytorch` input from the Windows workflow and use `fromJSON(inputs.build_config).build_pytorch` consistently

**⚠️ IMPORTANT (should fix):**
3. Validate `GITHUB_EVENT_NAME` in `from_environ()` like `GITHUB_REF_NAME`
4. Remove unused `build_variant` parameter from `_append_build_rocm`
5. Add test for `write_outputs` with mocked GHA functions
6. Replace or document the `test_pipeline_calls_all_steps` wiring test

**💡 SUGGESTION (nice to have):**
7. Move `import os` to top of `configure_multi_arch_ci_summary.py`
8. Document `gfx*` label split-on-dash behavior
9. Add test for `from_environ` with missing `GITHUB_REF_NAME`
10. Pass skip reason through to summary formatting

### Testing Recommendations

- The contract test pattern (`TestBuildConfigWorkflowContract`) is excellent and should be kept
- Coverage is good for the pure pipeline functions
- The main gap is `write_outputs` — this is the serialization boundary where type mismatches could bite
- Consider adding a "smoke test" that runs the full pipeline for each event type and validates the output dict has all expected keys with correct types

---

## Conclusion

The pipeline architecture is a substantial improvement in testability and maintainability over the old `configure_ci.py` multi-arch codepath. The dataclass-driven design, pure functions, and structural tests are well done.

The two blocking issues are both in the workflow YAML — an incomplete migration of the Windows workflow and a stale matrix reference in the top-level workflow. These will cause silent runtime failures and should be straightforward to fix. The remaining items are minor style and coverage improvements.
