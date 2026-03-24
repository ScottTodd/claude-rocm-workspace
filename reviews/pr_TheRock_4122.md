# PR Review: Fix missing per-Python multi-arch CI builds

* **PR:** [#4122](https://github.com/ROCm/TheRock/pull/4122)
* **Author:** marbre (Marius Brehler)
* **Reviewed:** 2026-03-24
* **Status:** OPEN
* **Base:** `main` ← `users/marbre/multi-arch-per-python-builds`

---

## Summary

The multi-arch CI path (`configure_stage.py`) was missing `THEROCK_DIST_PYTHON_EXECUTABLES` and `THEROCK_SHARED_PYTHON_EXECUTABLES` CMake vars, causing ~50MB / 115 files to be absent from the `rocm_sdk_core` wheel (GDB binaries, Python site-packages for rocpd/roctx, GDB Python scripting files). This PR adds a `--manylinux` flag to `configure_stage.py` and extracts the Python path constants into a shared module (`manylinux_config.py`) so both `build_configure.py` and `configure_stage.py` use the same source of truth.

**Net changes:** +57 lines, -15 lines across 4 files

---

## Overall Assessment

**✅ APPROVED** — Clean, well-scoped fix for a real parity gap between standard and multi-arch CI. The approach is sound: extract shared constants, wire them into the missing path.

**Strengths:**

- Root cause clearly identified and well-documented in the PR description
- Single source of truth for Python executable paths eliminates future drift
- Intentionally does NOT copy the `THEROCK_ENABLE_SYSDEPS_AMD_MESA/ROCDECODE/ROCJPEG` flags — those are correctly handled by topology-based feature enablement in the multi-arch path
- Quoting of semicolon-containing values is consistent with existing `DIST_AMDGPU_FAMILIES` pattern
- Full multi-arch CI run ([#23356803838](https://github.com/ROCm/TheRock/actions/runs/23356803838)) passes all stages

**No blocking or important issues.**

---

## Detailed Review

### 1. `build_tools/github_actions/manylinux_config.py` (new)

Clean shared module with good docstring explaining what the paths are, where they come from, and who consumes them.

Note: `DIST_PYTHON_EXECUTABLES` has cp310–cp313 (4 versions), while `SHARED_PYTHON_EXECUTABLES` has cp310–cp314 (5 versions). This asymmetry existed before this PR — it's inherited from `build_configure.py`. The cp314 shared entry is presumably for ROCgdb's embedded Python support on a newer Python. Not a concern for this PR.

### 2. `build_tools/configure_stage.py`

The `--manylinux` parameter is cleanly threaded through: CLI arg → `main()` → `generate_cmake_args()`. The quoting with double quotes inside the f-string matches the existing `dist_amdgpu_families` pattern on line 143, which is correct since these values contain semicolons that act as CMake list separators and need quoting when passed through shell expansion in the workflow.

### 3. `build_tools/github_actions/build_configure.py`

Straightforward replacement of inline string literals with the shared constants. The import `from manylinux_config import ...` works because Python adds the script's directory (`build_tools/github_actions/`) to `sys.path[0]`.

### 4. `.github/workflows/multi_arch_build_portable_linux_artifacts.yml`

Single line addition of `--manylinux \` to the `configure_stage.py` invocation. Correctly placed.

---

## Recommendations

### 💡 Consider:

1. **Tests for the new `--manylinux` flag in `configure_stage.py`** — If there are existing tests for `generate_cmake_args()`, adding a case with `manylinux=True` would lock in the behavior. Not blocking since the feature is validated by the full CI run.

### 📋 Future Follow-up:

1. **`DIST_PYTHON_EXECUTABLES` vs `SHARED_PYTHON_EXECUTABLES` version asymmetry** — The cp314 entry only in the shared list is intentional but not documented in `manylinux_config.py`. A comment explaining why would prevent someone from "fixing" the apparent mismatch later.

---

## CI Evidence

Compared PR run [#23356803838](https://github.com/ROCm/TheRock/actions/runs/23356803838) against baseline on main [#23472396826](https://github.com/ROCm/TheRock/actions/runs/23472396826).

### `configure_stage.py` output — debug-tools stage

**PR run** cmake_args include:
```
-DTHEROCK_DIST_PYTHON_EXECUTABLES="/opt/python/cp310-cp310/bin/python;...;/opt/python/cp313-cp313/bin/python"
-DTHEROCK_SHARED_PYTHON_EXECUTABLES="/opt/python-shared/cp310-cp310/bin/python3;...;/opt/python-shared/cp314-cp314/bin/python3"
```

**Baseline (main)** cmake_args: **no `DIST_PYTHON_EXECUTABLES` or `SHARED_PYTHON_EXECUTABLES`** — confirms the root cause. Without these args, per-Python-version builds (rocgdb, rocpd, roctx) are not triggered.

### Stage build timings — debug-tools

| Step | PR run | Baseline |
|------|--------|----------|
| Build stage | 3m43s | 4m4s |

No regression from adding the Python vars. Build times are comparable (ccache covers repeat work).

### Build Python Packages

| Step | PR run | Baseline |
|------|--------|----------|
| Build Python packages | ~21 min | ~33 min |

The baseline is slower but also builds for 5 GPU families vs 3 in the PR run (gfx950-dcgpu and gfx110X-all were added to multi-arch after the PR was branched). Not an apples-to-apples comparison, but no regression signal.

### Test failures in baseline (unrelated)

The baseline has 3 test failures on gfx94X-dcgpu (rccl, rocblas, libhipcxx_hipcc) and a CI Summary failure. These are absent from the PR run and unrelated to this change — likely pre-existing flakes or regressions on main.

### Verdict

CI logs confirm the fix works as intended: `THEROCK_DIST_PYTHON_EXECUTABLES` and `THEROCK_SHARED_PYTHON_EXECUTABLES` are emitted by `configure_stage.py` in the PR run and absent in the baseline. All stages pass.

---

## Conclusion

**Approval Status: ✅ APPROVED**

Well-executed fix. The shared module eliminates a maintenance hazard, the CI validates the behavior, and the scope is appropriately narrow.
