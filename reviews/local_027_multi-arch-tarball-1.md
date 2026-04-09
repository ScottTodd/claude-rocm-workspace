# Branch Review: multi-arch-tarball-1

* **Branch:** `multi-arch-tarball-1`
* **Base:** `main`
* **Reviewed:** 2026-04-10
* **Commits:** 17 commits (9 tarball-specific, rest from merged/in-review PRs)

---

## Summary

Adds infrastructure for building multi-arch ROCm tarballs from CI artifacts.
The core workflow fetches pre-built artifacts per GPU family, flattens them
into install-prefix layouts, compresses into per-family tarballs (and an
optional multi-arch tarball when KPACK split is enabled), then uploads to S3.

Also includes download caching in `artifact_manager.py`, `--run-github-repo`
threading for fork testing, and `WorkflowOutputRoot.tarballs()` for the
upload path.

**Net changes:** +1268 lines, -404 lines across 37 files

---

## Overall Assessment

**:white_check_mark: APPROVED** — Well-structured, thoroughly prototyped, good separation of
concerns. A few suggestions below but nothing blocking.

**Strengths:**

- Clean script design: `build_tarballs.py` separates fetch (sequential, shared
  cache) from compress (parallel), with KPACK split detection driving the
  multiarch tarball decision.
- Thorough benchmarking drove good decisions (subprocess tar over tarfile,
  parallel compression in-process over matrix sharding).
- `--download-cache-dir` is a useful general-purpose addition to
  `artifact_manager.py`.
- `--run-github-repo` threading through all layers (backend, manager, script,
  workflow) enables fork testing cleanly.
- Good test coverage for the unit-testable parts (`is_kpack_split`,
  `compress_tarball`).

---

## Detailed Review

### 1. `build_tarballs.py`

**:bulb: SUGGESTION: `test_missing_flag` and `test_no_manifest` are identical**

Both test `is_kpack_split` on an empty directory (no manifest file).
`test_missing_flag` writes a manifest with empty `flags: {}` — the flag
key is missing. `test_no_manifest` has no manifest at all. These are
genuinely different cases so this is fine — the names just read similarly.

**:bulb: SUGGESTION: Consider `--compress-workers` flag**

`max_workers=len(compress_tasks)` creates one worker per family. On a
machine with fewer cores than families this could oversaturate. A
`--compress-workers` flag (defaulting to `len(compress_tasks)` or
`os.cpu_count()`) would give CI tuning knobs without changing default
behavior. Low priority — current runners have 64+ cores.

### 2. `upload_tarballs.py`

**:bulb: SUGGESTION: `upload_tarballs.py` doesn't log the S3 URI per file**

`upload_python_packages.py` logs each file being uploaded.
`upload_tarballs.py` only logs the count. For tarballs (few files, large
size) logging each file name + destination would help debugging CI issues.

### 3. `artifact_manager.py` download cache

**:clipboard: FUTURE WORK: Cache validation**

The download cache checks `request.dest_path.exists()` but doesn't validate
file size or integrity. A partial download from a killed process would be
treated as cached. Could add size comparison against the S3 object metadata,
or a `--no-cache` bypass flag. Low risk in practice since CI runners start
clean, but worth noting for local development workflows.

### 4. `multi_arch_build_tarballs.yml`

No issues. Inputs match script args, `RELEASE_TYPE` set at job level,
`artifact_github_repo` enables fork testing.

### 5. `workflow_outputs.py` / `workflow_outputs.md`

`tarballs()` method and doc updates are clean. The tarballs layout is
documented in both single-stage and multi-arch sections.

### 6. `artifact_backend.py`

`github_repository` param addition is clean — keyword-only callers
unaffected by the arg reordering.

---

## Recommendations

### :bulb: Consider:

1. Add `--compress-workers` flag for tuning on smaller runners.
2. Log individual file names in `upload_tarballs.py` for CI debugging.

### :clipboard: Future Follow-up:

1. Cache validation for `--download-cache-dir` (size check or `--no-cache` flag).
2. Wire `multi_arch_build_tarballs.yml` into `multi_arch_ci_linux.yml` as downstream job.
3. Address #4433 (family→target expansion) for KPACK split builds.
4. Benchmark `.tar.zst` on CI runners and propose format switch if consumers support it.

---

## Testing Recommendations

- Fork CI run with `workflow_dispatch` (in progress — initial results passing).
- Verify disk space is sufficient for multi-family builds on github-hosted runners.
- Run `python -m pytest build_tools/tests/build_tarballs_test.py` locally.
- Test `upload_tarballs.py --output-dir` for local validation without S3.

---

## Conclusion

**Approval Status: :white_check_mark: APPROVED**

The tarball infrastructure is well-designed and thoroughly tested locally.
Ready for PR split and CI validation. The three-PR split (run-github-repo,
download cache, tarball scripts+workflow) is a good decomposition.
