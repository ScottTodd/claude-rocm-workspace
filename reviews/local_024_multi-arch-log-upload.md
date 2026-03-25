# Branch Review: multi-arch-log-upload

* **Branch:** `multi-arch-log-upload`
* **Base:** `main`
* **Reviewed:** 2026-03-25
* **Commits:** 5 commits

---

## Summary

Adds multi-arch CI stage log uploads — ninja log archiving and per-stage log
directory upload to S3. Also documents the multi-arch log/python layout in
`workflow_outputs.md` and removes the upload_directory log truncation limit.

**Net changes:** +507 lines, -4 lines across 8 files

---

## Overall Assessment

**✅ APPROVED** — Clean, focused addition. The script is well-structured,
tested, and wired into both Linux and Windows workflows. The S3 path design
avoids collisions between parallel per-arch stage jobs.

**Strengths:**
- Minimal script with clear scope (ninja archive + log upload, nothing else)
- Path structure `logs/{stage}/` and `logs/{stage}/{family}/` maps naturally
  to the job structure and avoids file collisions
- Backend passed as argument, not constructed internally — good for testing
- Graceful handling of missing build dir (log + return, don't steal error focus)
- Tests cover all key paths: generic stages, per-arch stages, fork repos,
  platform propagation, missing dirs, CLI validation
- Docs updated with multi-arch layout including python packages

---

## Detailed Review

### 1. `build_tools/github_actions/post_stage_upload.py`

No issues. The script is focused and follows established patterns from
`post_build_upload.py`. Key design decisions are sound:

- `create_ninja_log_archive` only creates `logs/` when files exist to archive
- `upload_stage_logs` delegates entirely to `backend.upload_directory`
- Missing build dir logs and returns (doesn't mask upstream failures)
- `--stage` naming matches `artifact_manager.py push`
- Arg order (`--run-id`, `--stage`, `--build-dir`, `--amdgpu-family`) matches
  `artifact_manager.py push` for the common args

#### 💡 SUGGESTION: Docstring still references `--stage-name`

The module docstring usage example on line 24 shows `--stage-name` but the
actual CLI arg is `--stage`.

```python
Usage:
    python post_stage_upload.py \\
        --build-dir build \\
        --stage-name math-libs \\       # <-- should be --stage
```

### 2. `build_tools/_therock_utils/workflow_outputs.py`

`stage_log_dir()` is clean. The docstring mentions comm-libs as a per-arch
stage example — may want to soften that since comm-libs might become generic.

### 3. Workflow wiring

Both Linux and Windows workflows are identical — `if: !cancelled()` on the
upload step is correct (upload even on build failure, which is the most
important case for log access).

The step runs after artifact push (which has no `!cancelled()`) so the push
step failure propagates correctly as the "real" error.

### 4. `build_tools/_therock_utils/storage_backend.py`

Removing the 100-file truncation is fine. CI logs are cheap and the full list
helps debugging.

### 5. `docs/development/workflow_outputs.md`

Good addition. Both generic and per-arch layouts are clearly documented with
concrete examples. Python package layout matches observed CI output.

### 6. Tests

11 tests total (8 in post_stage_upload_test, 3 in workflow_outputs_test).
Coverage is good:

- Ninja archive: creation with files, skip when none
- Upload paths: generic, per-arch, fork+windows combo, missing log dir
- CLI: missing run-id (with env override for CI), missing build dir
- stage_log_dir: per-arch, generic, empty string

---

## Recommendations

### ❌ REQUIRED (Blocking):
(none)

### ✅ Recommended:
1. Fix docstring usage example: `--stage-name` → `--stage` (line 24)
2. Soften `stage_log_dir` docstring — replace "comm-libs" mention with
   just "e.g., math-libs" since comm-libs might go generic

### 💡 Consider:
(none)

### 📋 Future Follow-up:
1. GHA build summary with log links (centralized, not per-stage)
2. Server-side recursive index generation (#3331) for cross-stage searchability

---

## Testing Recommendations

```bash
python -m pytest build_tools/github_actions/tests/post_stage_upload_test.py \
                 build_tools/tests/workflow_outputs_test.py -v
```

Already validated on CI via PR #4169 — foundation stage uploaded 87 files
successfully to `logs/foundation/`.

---

## Conclusion

**Approval Status: ✅ APPROVED**

Two minor docstring fixes recommended, then ready to merge.
