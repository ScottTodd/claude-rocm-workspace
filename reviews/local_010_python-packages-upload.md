# Branch Review: python-packages-upload

* **Branch:** `python-packages-upload`
* **Base:** `upstream/main`
* **Reviewed:** 2026-01-28
* **Commits:** 6 commits

---

## Summary

This PR adds `upload_python_packages.py` for uploading Python packages to S3 with pip-compatible index generation, and updates the Python packaging documentation with improved workflows for building and installing packages locally.

**Net changes:** +391 lines, -26 lines across 2 files

---

## Overall Assessment

**✅ APPROVED** - Well-structured script with good documentation. Ready for human review.

**Strengths:**
- Clean, focused PR with only relevant changes
- `UploadPath` dataclass provides clean abstraction for path computation
- Uses existing `indexer.py` instead of adding dependencies
- Supports multiple modes: S3 upload, local output, dry-run
- Good documentation with concrete examples
- Follows project coding conventions

---

## Detailed Review

### 1. build_tools/github_actions/upload_python_packages.py (NEW, 317 lines)

Well-structured script with clear separation of concerns:

- **`UploadPath` dataclass** - Clean abstraction for bucket/prefix with computed properties for `s3_uri` and `s3_url`
- **`generate_index()`** - Uses existing `third-party/indexer/indexer.py` (no new dependencies)
- **`run_aws_cp()` / `run_local_cp()`** - Clear upload/copy helpers with dry-run support
- **`write_gha_upload_summary()`** - GitHub Actions job summary with install instructions

**💡 SUGGESTION: Log index URL to stdout**

The index URL is written to GHA summary but not stdout. Consider adding:
```python
log(f"[INFO] Index URL: {index_url}")
```
This helps when reviewing logs outside of the GHA summary view.

**💡 SUGGESTION: Consider return type for `generate_index`**

Currently returns `None`. Could return the path to the generated `index.html` for chaining/verification.

### 2. docs/packaging/python_packaging.md

Improved structure with clearer workflows:

**New sections:**
- "Build Package Versions" - Moved version info to top
- "Building from CI Artifacts" - Complete workflow with `fetch_artifacts.py`
- "Installing Locally Built Packages" - Using `indexer.py` and `--find-links`

**Changes:**
- Replaced piprepo instructions with `indexer.py` approach
- Added concrete example with environment variables
- Added tip about `upload_python_packages.py` for CI-style testing

**💡 SUGGESTION: Minor - example output shows Windows filenames**

The `ls ${PACKAGES_DIR}` example shows `win_amd64` wheel names. Consider using `linux_x86_64` for consistency with the bash/Linux context, or note that output varies by platform.

---

## Recommendations

### 💡 Consider (Optional):

1. Log the index URL to stdout (not just GHA summary)
2. Return path from `generate_index()` for verification

### 📋 Future Follow-up:

1. Integrate upload step into `build_portable_linux_python_packages.yml` workflow
2. Update `test_rocm_wheels.yml` to accept CI artifact URLs
3. Consolidate path computation with `RunOutputRoot` (PR #3000)
4. Add S3 upload to Windows workflow

---

## Testing Recommendations

The script has been manually tested (per conversation). For CI integration:

1. **Local output mode:**
   ```bash
   python ./build_tools/github_actions/upload_python_packages.py \
     --packages-dir=${PACKAGES_DIR} \
     --artifact-group=gfx110X-all \
     --run-id=21440027240 \
     --output-dir=/tmp/upload-test
   ```

2. **Verify pip install works:**
   ```bash
   pip install rocm[libraries,devel] --pre \
     --find-links=/tmp/upload-test/.../index.html
   ```

---

## Conclusion

**Approval Status: ✅ APPROVED**

Clean, focused PR that adds useful functionality for Python package uploads. The script is well-designed with good separation of concerns, and the documentation improvements make the local development workflow much clearer. Ready for human review.
