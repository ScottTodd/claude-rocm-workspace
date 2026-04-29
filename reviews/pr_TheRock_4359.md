# PR Review: Add native package builds and tests to multi-arch CI pipeline

* **PR:** [#4359](https://github.com/ROCm/TheRock/pull/4359)
* **Author:** nunnikri (Nirmal Unnikrishnan)
* **Reviewed:** 2026-04-29
* **Status:** OPEN
* **Base:** `main` ← `users/nunnikri/multi_arch_ci_enable`

---

## Summary

Integrates native DEB and RPM package builds and tests into the multi-arch CI pipeline. Changes `compute_rocm_package_version.py` to emit all three version formats (wheel, deb, rpm) when `--package-type` is omitted, threads the new deb/rpm versions through the workflow chain (setup → CI → CI Linux), and adds 5 new jobs: build DEB packages, build RPM packages, test DEB install on Ubuntu 24.04, test RPM install on RHEL 10, and test RPM install on SLES 16.

**Net changes:** +216 lines, -17 lines across 6 files

---

## Overall Assessment

**✅ APPROVED** — Clean, well-structured PR with good test coverage and a passing CI validation run.

**Strengths:**

- Backward compatibility maintained: existing workflows calling `compute_rocm_package_version.py` with or without `--package-type` continue to work
- Good test coverage for the new Python behavior (3 new tests covering multi-type output, backward compat, and existing workflow behavior)
- CI validation run ([#25095078749](https://github.com/ROCm/TheRock/actions/runs/25095078749)) shows all 5 new jobs (build DEB, build RPM, test ubuntu2404, test rhel10, test sles16) passing successfully
- New jobs follow established workflow patterns (same `if` condition, same permissions model)
- Clean data flow: setup → CI → CI Linux with proper input threading

**No blocking issues.**

---

## CI Evidence

The linked CI run (25095078749) completed with all build and test jobs passing:

| Job | Status |
|-----|--------|
| Build DEB Packages | ✅ success |
| Build RPM Packages | ✅ success |
| Test DEB Install - ubuntu2404 | ✅ success |
| Test RPM Install - rhel10 | ✅ success |
| Test RPM Install - sles16 | ✅ success |

The only failure was the "CI Summary" job (step: "Evaluate workflow results"), which appears unrelated to this PR's changes.

---

## Detailed Review

### 1. `compute_rocm_package_version.py`

Well-done refactor. The loop over `package_types` is clean and the single `gha_set_output(outputs)` call at the end is simpler than the old per-type branching.

#### 💡 SUGGESTION: `--release-type=release` incompatible with "compute all" mode

When `--package-type` is omitted and `--release-type=release` is used, the validation `"wheel" in package_types` triggers an error. This is the right behavior for now (release versions are only meaningful for specific package types), but if you ever want to compute both deb and rpm release versions in one call, you'd need to either exclude wheel from the default set or add a `--package-type=native` option.

Not needed for this PR — just noting the design boundary.

### 2. `.github/workflows/multi_arch_ci_linux.yml`

The 5 new jobs are well-structured and follow existing patterns.

#### 💡 SUGGESTION: Consider passing `repository` and `ref` for consistency

The new build and test jobs don't pass `repository` or `ref` to the called workflows (`multi_arch_build_native_linux_packages.yml`, `test_native_linux_packages_install.yml`). This works because those inputs have defaults, and the CI run confirms it. However, other jobs in this file and in the release workflows pass these explicitly. Consider adding them for consistency, especially since these job definitions may serve as templates when native packages are added to `multi_arch_release_linux.yml`.

#### 💡 SUGGESTION: `release_type: ""` vs `release_type: ci` asymmetry

The build jobs use `release_type: ""` while the test jobs use `release_type: "ci"`. This is functionally correct (the build workflow uses release_type for S3 path/bucket selection, while the test workflow uses it for test configuration), but the semantic difference isn't immediately obvious. A brief comment on the build jobs explaining the empty string choice would help future readers.

### 3. `.github/workflows/multi_arch_release.yml`

#### 💡 SUGGESTION: Pre-wired inputs not yet consumed

The PR adds `rocm_deb_package_version` and `rocm_rpm_package_version` to the call to `multi_arch_release_linux.yml`, but that workflow doesn't declare these inputs yet (it has a `# TODO(#3334): build native packages` comment). GitHub Actions silently ignores undeclared inputs, so this is harmless, but it is dead code until the release pipeline is updated. Consider adding this in a follow-up PR when native packages are actually wired into the release pipeline, to keep changes atomic.

### 4. `.github/workflows/setup_multi_arch.yml`

Clean additions. The new outputs are properly declared and wired from the step outputs.

### 5. `.github/workflows/multi_arch_ci.yml`

Clean additions. Threads the new outputs to the Linux CI workflow.

### 6. `compute_rocm_package_version_test.py`

#### 💡 SUGGESTION: Use `unittest.mock.patch` for cleaner test setup

The tests manually save/restore `gha_set_output` with try/finally blocks. Using `unittest.mock.patch` (or `@patch` decorator) would be more idiomatic and less error-prone:

```python
from unittest.mock import patch

def test_compute_all_package_types_without_flag(self):
    captured_outputs = {}
    with patch.object(
        compute_rocm_package_version, "gha_set_output",
        side_effect=lambda outputs: captured_outputs.update(outputs),
    ):
        compute_rocm_package_version.main(
            ["--release-type", "dev", "--override-base-version", "8.0.0"]
        )
    self.assertIn("rocm_package_version", captured_outputs)
    # ...
```

This applies to all three new tests.

---

## Recommendations

### ✅ Recommended:

1. Consider passing `repository` and `ref` to new build/test jobs for consistency with existing patterns
2. Add a comment on the build jobs explaining why `release_type: ""` (vs the test jobs' `release_type: "ci"`)

### 💡 Consider:

1. Use `unittest.mock.patch` instead of manual save/restore in new tests
2. Add the `multi_arch_release.yml` input wiring in a follow-up PR alongside the release pipeline native package integration, rather than pre-wiring now

### 📋 Future Follow-up:

1. Wire native package builds into `multi_arch_release_linux.yml` (tracked by #3334 TODO)
2. Consider a `--package-type=native` option if both deb+rpm release versions need to be computed in one call

---

## Testing

- All 18 existing tests pass locally
- CI validation run confirms all new jobs (build + test for 3 distros) pass
- The only CI failure is the "CI Summary" job, which is unrelated to this PR

---

## Conclusion

**Approval Status: ✅ APPROVED**

The PR is well-structured with good backward compatibility, proper test coverage, and a validated CI run. The suggestions above are all non-blocking improvements. Ready for human review and merge.
