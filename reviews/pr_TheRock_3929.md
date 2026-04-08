# PR Review: [CI] Run full PyTorch UT suite

* **PR:** https://github.com/ROCm/TheRock/pull/3929
* **Author:** ethanwee1
* **Base:** `main`
* **Reviewed:** 2026-04-07
* **Status:** OPEN

---

## Summary

Adds a nightly CI workflow (`ci_nightly_pytorch_full_test.yml`) that runs the complete PyTorch unit test suite across three test configs (default, distributed, inductor) against nightly staging wheels. Extends `test_pytorch_wheels_full.yml` with inductor config support, ROCm SDK devel packages, `pytest-timeout`, container hardening (`--shm-size`, `SYS_PTRACE`), JUnit failure scanning, and a `pytorch_git_repo` input. Adds 170 known-failing test skips for gfx94X in `pytorch_2.12.py`.

**Net changes:** +717 lines, -40 lines across 6 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The core design is sound and the PR clearly represents significant debugging/triage effort to catalog 170 test skips. However, there are several issues that should be addressed before merge.

**Strengths:**
- Well-structured nightly workflow with good TODOs for future improvements
- Inductor config properly mirrors upstream `test_inductor_shard()` two-phase pattern
- JUnit XML failure scanning catches `--keep-going` false-positives
- Container changes (`--shm-size=10g`, `SYS_PTRACE`) are appropriate for PyTorch's multiprocessing tests
- Test report upload with `if: always()` ensures artifacts survive failures
- Good separation: nightly orchestrator calls the reusable workflow

**Issues:**

- 1 blocking (complex inline bash in nightly workflow)
- 3 important (breaking default changes, `os._exit()`, missing `--distributed-tests` for workflow_call)
- Several suggestions

---

## Detailed Review

### 1. `ci_nightly_pytorch_full_test.yml` (new)

#### ❌ BLOCKING: Complex inline bash in `resolve_torch_version`

The `resolve_torch_version` job has a `run:` block with conditionals (`if/fi`), string manipulation (`sed`), and multi-step logic. Per the [GitHub Actions style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/github_actions_style_guide.md#prefer-python-scripts-over-inline-bash), this belongs in a Python script.

The logic includes:
- Conditional branch on `inputs.torch_version` emptiness
- `pip index versions` invocation with variable expansion
- `sed` parsing of version output
- Error handling with `exit 1`

**Required action:** Extract to a Python script (e.g., `external-builds/pytorch/resolve_torch_version.py`) that accepts the index URL, python version, and optional explicit version as arguments. This also makes the version resolution logic testable.

#### 💡 SUGGESTION: Schedule trigger has no dependency on build completion

The TODO comment acknowledges this, but it's worth noting that `cron: "0 12 * * *"` is a time-based guess. If the nightly build is late or fails, this workflow will either test stale wheels or fail to find them. Consider adding a `workflow_run` trigger on the nightly build workflow as a follow-up.

### 2. `test_pytorch_wheels_full.yml` (modified)

#### ⚠️ IMPORTANT: Breaking default changes for `workflow_dispatch`

Two defaults were changed that affect manual `workflow_dispatch` users:

1. `package_index_url` default: `v2` → `v2-staging` — Users who manually dispatch this workflow expecting production wheels will now get staging wheels.
2. `tests_to_include` default: specific test list → `""` (run all) — Manual dispatch now runs the entire test suite instead of a quick subset.

These are breaking changes for anyone who uses the "Run workflow" button in the GitHub UI and relies on the defaults.

**Recommendation:** Either revert the `workflow_dispatch` defaults (keep them as-is for manual users, since the nightly caller passes its own values), or document the change in the PR description.

#### ⚠️ IMPORTANT: `pytorch_git_repo` input added to `workflow_dispatch` but caller-consistency issue

The new `pytorch_git_repo` input is added to both `workflow_dispatch` and `workflow_call`, which is correct. However, the `workflow_dispatch` default is `"rocm/pytorch"` while the old behavior was split: `pytorch/pytorch` for nightly, `ROCm/pytorch` for stable. The consolidation to a single input is cleaner, but the default silently changes behavior for the nightly ref case.

**Recommendation:** Add a note in the PR description about this intentional change.

#### 💡 SUGGESTION: Removed `Summarize workflow inputs` step

The step calling `summarize_test_pytorch_workflow.py` was removed but no replacement summary is added. This was presumably generating a `$GITHUB_STEP_SUMMARY`. Consider whether the loss of that summary is acceptable.

### 3. `run_pytorch_tests_full.py` (modified)

#### ⚠️ IMPORTANT: `os._exit()` bypasses cleanup and makes `main()` untestable

The PR adds `os._exit(return_code)` at the end of `main()`, which:
1. Prevents any cleanup or `finally` blocks from running
2. Makes `main()` impossible to test in a test suite (it kills the test process)
3. Bypasses `atexit` handlers

The comment explains this is to work around PyTorch leaking daemon threads. While the workaround is understandable, `os._exit()` at the end of `main()` is aggressive.

**Recommendation:** Move the `os._exit()` to the `if __name__ == "__main__"` block instead:
```python
if __name__ == "__main__":
    rc = main(sys.argv[1:])
    os._exit(rc if rc >= 0 else 1)
```
This keeps `main()` testable while still force-killing leaked threads at the process boundary.

#### 💡 SUGGESTION: `has_junit_failures` silently swallows `ET.ParseError`

The function catches `ET.ParseError` and `continue`s. If JUnit XML is corrupted, this means failures could be missed. Consider at least logging a warning.

#### 💡 SUGGESTION: `_run_inductor` doesn't propagate `--exclude` args

The `build_inductor_cmds` function doesn't include `EXCLUDED_TEST_MODULES` or `args.exclude` in the commands. Since the inductor config uses `--include` to pick specific test modules, the `--exclude` list may not apply, but it's worth verifying that `nn/test_convolution` (the hanging module) isn't in the inductor test lists.

#### 💡 SUGGESTION: `build_inductor_cmds` duplicates logic from `build_run_test_cmd`

The two functions share several patterns (cache disabling, timeout, shard args, dry-run). Consider extracting shared logic to reduce divergence over time.

### 4. `generate_test_sharding_matrix.py`

No issues — the comment trimming is a minor cleanup.

### 5. `requirements-test.txt`

`pytest-timeout` added without version pin. This is consistent with other entries (e.g., `hypothesis`, `expecttest>=0.3.0`), so acceptable.

### 6. `skip_tests/pytorch_2.12.py`

#### 💡 SUGGESTION: All skips under "common" key

The PR description notes this: all 170 skips are under the `common` key (applied to all GPU families). The PR correctly calls this out as something to split once more GPU families are tested. No action needed now, but the volume is notable.

#### 💡 SUGGESTION: Some skip comments reference test class names inconsistently

Some entries use the actual error type (e.g., `RuntimeError`, `AssertionError`, `SIGSEGV`) while others use test class names. Consider standardizing to test class + brief failure reason for easier triage.

### 7. Container changes

The `--ipc host` → `--shm-size=10g` change is a security improvement (host IPC namespace sharing is broader than needed). Adding `--cap-add=SYS_PTRACE` enables gdb/strace debugging in the container, which is appropriate for test runners.

### 8. CI Evidence

The linked run (24086897853) shows inductor shard 1/2 completed successfully in ~90 minutes. Most other shards are still running. The "Install ROCm devel packages" step completed in ~19s and "Initialize ROCm SDK" in ~5s, indicating the new workflow steps are efficient.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Extract `resolve_torch_version` inline bash to a Python script

### ✅ Recommended:

1. Revert `workflow_dispatch` defaults for `package_index_url` and `tests_to_include` (or document the intentional breaking change)
2. Move `os._exit()` from inside `main()` to the `__main__` block
3. Document the `pytorch_git_repo` default change (nightly previously used `pytorch/pytorch`)

### 💡 Consider:

1. Add a warning log in `has_junit_failures` when XML parsing fails
2. Extract shared command-building logic between `build_run_test_cmd` and `build_inductor_cmds`
3. Standardize skip test comment format in `pytorch_2.12.py`

### 📋 Future Follow-up:

1. Replace `schedule` trigger with `workflow_run` trigger on nightly build completion
2. Split GPU-family-specific skips once additional families are enabled in CI
3. Investigate root causes for `EXCLUDED_TEST_MODULES` (nn/test_convolution hang)

---

## Testing Recommendations

- Verify `workflow_dispatch` works with the new defaults (or reverted defaults)
- Once all shards complete, confirm the JUnit failure scanning correctly catches any remaining failures
- Test the inductor config with `--dry-run` to verify the two-phase command generation

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The complex inline bash in the nightly workflow is a blocking style guide violation. The `workflow_dispatch` default changes and `os._exit()` placement should also be addressed. The overall approach is solid and the test skip triage work is thorough.
