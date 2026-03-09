# Review: users/scotttodd/multi-arch-prebuilt-3

- **Branch:** `users/scotttodd/multi-arch-prebuilt-3`
- **Base:** `upstream/main`
- **Date:** 2026-03-09
- **Commits:** 6
- **Files changed:** 13 (+261/-106)
- **Review type:** Comprehensive

## Summary of Changes

Replaces the all-or-nothing `use_prebuilt_artifacts` boolean with per-stage `prebuilt_stages` (comma-separated list) and `baseline_run_id` across all multi-arch CI workflows. Key changes:

1. **Workflow input consolidation**: Removed per-platform `linux_use_prebuilt_artifacts`, `windows_use_prebuilt_artifacts`, and `artifact_run_id`. Added unified `prebuilt_stages` and `baseline_run_id` inputs.
2. **Copy jobs**: Added `copy_prebuilt_stages` jobs to both `multi_arch_ci_linux.yml` and `multi_arch_ci_windows.yml` that invoke `artifact_manager.py copy`.
3. **Per-stage skip conditions**: Added `if: !contains(inputs.prebuilt_stages, 'stage-name')` to all stage jobs in both Linux (8 stages) and Windows (3 stages) build pipelines.
4. **Job dependency flow**: Build and test jobs use `!cancelled() && !failure()` to proceed when copy/build predecessors are skipped.
5. **configure_ci.py fix**: `workflow_dispatch` now always sets `enable_build_jobs = True`.
6. **Semicolon separator**: `artifact_manager.py --amdgpu-families` changed from comma to semicolon separator (matching `configure_stage.py` convention).
7. **Documentation**: New "Prebuilt stages (Multi-Arch CI)" section in `ci_behavior_manipulation.md`.

## Overall Assessment: ✅ APPROVED

No blocking issues. The changes are well-structured, consistent across platforms, and tested via workflow dispatch runs. A few items to discuss before sending the PR.

## Findings

### ⚠️ IMPORTANT: `enable_build_jobs` removed from multi_arch_ci.yml conditions

The diff removes the `enable_build_jobs == 'true'` check from both `linux_build_and_test` and `windows_build_and_test` job conditions in `multi_arch_ci.yml`. Combined with the `configure_ci.py` fix (workflow_dispatch always enables builds), this works correctly for workflow_dispatch and push triggers.

However, if `pull_request` triggers are ever uncommented for multi_arch_ci.yml, the `skip-ci` label would be ignored since `enable_build_jobs` is no longer checked. This is likely acceptable given:
- PR triggers are currently commented out
- The plan is to rewrite `configure_ci.py` anyway
- When PR triggers are enabled, the guard should be re-added

**Recommendation:** Add a brief comment near the PR trigger section noting this dependency, or note it in the PR description.

### ⚠️ IMPORTANT: `contains()` substring matching for stage names

`contains(inputs.prebuilt_stages, 'foundation')` uses substring matching. If a future stage name is a substring of another (e.g. `compiler` matching `compiler-runtime`), this could cause false skips. Current stage names don't have this problem:
- foundation, compiler-runtime, math-libs, comm-libs, debug-tools, dctools-core, profiler-apps, media-libs

No action needed now, but worth noting in a comment or tracking issue.

### 💡 SUGGESTION: Fork guard on copy step

Both copy jobs have `if: ${{ !github.event.pull_request.head.repo.fork }}` on the AWS credentials and copy steps but not on the checkout/python/pip steps. Since multi_arch_ci.yml doesn't have PR triggers enabled, the fork guard is a no-op currently. When PR triggers are enabled, the copy job will still run checkout/setup but skip the actual copy — which wastes ~1-2 minutes on fork PRs. Consider moving the fork guard to the job-level `if` condition alongside the prebuilt_stages check.

### 💡 SUGGESTION: Test for configure_ci.py workflow_dispatch change

The `configure_ci.py` change to enable builds for workflow_dispatch is small but has no test. Consider adding a unit test to prevent regression:
```python
def test_workflow_dispatch_always_enables_builds(self):
    # ...set GITHUB_EVENT_NAME=workflow_dispatch...
    # ...assert enable_build_jobs == True...
```

### 📋 FUTURE WORK: Unrelated JAX changes from rebase

The diff includes changes to 3 JAX-related files (`build_linux_jax_wheels.yml`, `release_portable_linux_jax_wheels.yml`, `test_linux_jax_wheels.yml`) that came from the rebase onto upstream/main. These should be noted in the PR description as not part of this change, or the branch should be rebased again to minimize upstream noise.

### 📋 FUTURE WORK: setup.yml passthrough input

The `prebuilt_stages` input was added to `setup.yml` as a passthrough for future automatic stage selection. It's not consumed by any step yet. This is fine as scaffolding but should be connected or removed when the feature evolves.

## Recommendations

### Before PR submission
1. Note the `enable_build_jobs` removal rationale in the PR description
2. Rebase to minimize JAX diff noise (or note it explicitly in PR)
3. Verify test run 22874804188 results (Windows gfx110X with prebuilt stages)

### Testing recommendations
- [x] Linux workflow_dispatch with prebuilt stages (verified)
- [x] Windows workflow_dispatch with prebuilt stages (in progress: run 22874804188)
- [ ] Workflow_dispatch without prebuilt stages (normal build — should be unaffected)
- [ ] Push to main (should be unaffected by changes)

## Conclusion

Clean, well-scoped change that replaces the boolean prebuilt mechanism with a flexible per-stage approach. The workflow structure follows established patterns (`!cancelled() && !failure()`, `!contains()` guards). No blocking issues found.
