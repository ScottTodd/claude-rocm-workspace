# PR Review: #4168 — Split out index file generation from post upload script

* **PR:** https://github.com/ROCm/TheRock/pull/4168
* **Author:** marbre (Marius Brehler)
* **Base:** `main`
* **Branch:** `users/marbre/post_build_index`
* **Reviewed:** 2026-03-25
* **Status:** Open

---

## Summary

Removes client-side HTML index generation from `post_build_upload.py` and
introduces a standalone `generate_s3_index.py` script for server-side index
generation (to be called from an AWS Lambda handler). Also moves the
`github_actions_api` import in `workflow_outputs.py` to a lazy import inside
`_retrieve_bucket_info()` to keep the Lambda deployment package small.

**Net changes:** +601 lines, -86 lines across 6 files

---

## Overall Assessment

**✅ APPROVED** — Clean separation of concerns. The index generation logic is
well-structured, handles both single-arch and multi-arch layouts, and has good
test coverage. A few suggestions below.

**Strengths:**
- Good architectural decision: server-side index generation decouples CI runners
  from index page concerns
- Layout-agnostic directory discovery (works with any nesting depth)
- Lazy import of `github_actions_api` keeps Lambda deployment minimal
- Comprehensive test coverage (local mode) for listing, discovery, HTML generation,
  and integration

**Issues:**
- One important item re: composability with multi-arch log uploads
- A few suggestions

---

## Detailed Review

### 1. `build_tools/generate_s3_index.py`

#### ⚠️ IMPORTANT: Per-directory indexes only — no recursive/flat listing

The current implementation generates per-directory indexes that list only
immediate files (`_list_files_local` and `_list_files_s3` both skip files
in subdirectories). This is correct for single-arch CI where all logs are
flat in `logs/{group}/`.

For multi-arch CI, logs are nested: `logs/{stage}/{family}/`. A developer
debugging a build failure will want to search across all stages (e.g., Ctrl+F
for `_install.log` to find which subproject failed). The current per-directory
indexes require opening each stage/family directory separately.

A recursive index at the top level (e.g., `logs/index.html` listing files
like `math-libs/gfx1151/rocBLAS_build.log`) would preserve the "search
across everything" workflow that single-arch CI provides today.

**Recommendation:** Consider adding a recursive listing mode for parent
directories (where immediate children are subdirectories, not files). This
could be a follow-up — the per-directory indexes are useful on their own,
and the Lambda can be extended later. Just noting it as a design gap for
multi-arch composability.

#### 💡 SUGGESTION: `_upload_html` takes `dry_run` but doesn't use it

`_upload_html()` accepts a `dry_run` parameter (line 263) but never uses it —
the dry-run behavior is already handled by the backend. The parameter can be
removed.

```python
def _upload_html(html: str, dest: StorageLocation, backend: StorageBackend, dry_run: bool) -> None:
```

The `dry_run` parameter is passed through from `generate_index_for_directory`
but the backend already handles dry-run mode internally.

#### 💡 SUGGESTION: `generate_index_for_directory` has mixed abstraction levels

The function takes both `s3_client` and `staging_dir` as optional kwargs, with
the caller responsible for knowing which to pass. This works but means every
caller needs to implement the same if/else dispatch. Consider whether the
backend abstraction could be extended to handle listing (not just upload), or
at least document the mutual exclusivity clearly.

This is fine for now since there are only two callers (CLI `run()` and the
future Lambda handler).

### 2. `build_tools/github_actions/post_build_upload.py`

Clean removal. The `index_log_files()`, `index_artifact_files()`,
`run_command()`, and the `indexer` import are all gone. The artifact index
upload (`artifact_index(artifact_group)`) is also removed since index pages
are now server-side.

The `write_gha_build_summary` still references `log_index_url` and
`artifact_index` for building summary links. These URLs will now point to
server-generated pages. This should still work as long as the Lambda runs
before anyone clicks the links — which is fine since the Lambda is triggered
by PutObject events.

### 3. `build_tools/_therock_utils/workflow_outputs.py`

Lazy import change is clean and correct. The import only runs when
`workflow_run_id` is provided, which doesn't happen in the Lambda path.

### 4. Test changes

#### `build_tools/tests/generate_s3_index_test.py`

Good coverage of local-mode listing, discovery, HTML generation, and
integration. Tests both single-arch and multi-arch layouts.

The mock patch path in `workflow_outputs_test.py` correctly updates from
`_therock_utils.workflow_outputs.gha_query_workflow_run_by_id` to
`github_actions.github_actions_api.gha_query_workflow_run_by_id` to match
the lazy import location.

#### `build_tools/github_actions/tests/post_build_upload_test.py`

Test updates are minimal and correct — removes `index.html` creation from
test fixtures and flips the assertion from `assertTrue` to `assertFalse`
for the artifact index path.

---

## Composability with Multi-Arch Log Uploads

We're working on `post_stage_upload.py` (branch `multi-arch-log-upload`)
which uploads logs to `logs/{stage_name}/` or `logs/{stage_name}/{family}/`.
This PR's `generate_s3_index.py` already handles both layouts via
`_discover_dirs_with_files_s3` — it finds all directories at any depth that
contain files and generates an index for each. The two PRs compose cleanly.

The one gap is the recursive index discussed above — a parent `logs/index.html`
that lists files from all subdirectories. This would bridge the UX gap between
single-arch (flat, searchable) and multi-arch (nested, browsable). Can be a
follow-up.

---

## Recommendations

### ✅ Recommended:
1. No blocking changes needed

### 💡 Consider:
1. Remove unused `dry_run` parameter from `_upload_html()`
2. Add a note/TODO about recursive parent indexes for multi-arch composability

### 📋 Future Follow-up:
1. Recursive index generation for parent directories (bridges single-arch
   searchability with multi-arch nesting)
2. Lambda handler deployment (noted as out of scope in PR description)
3. Removal of `third-party/indexer.py` (noted as out of scope)

---

## Testing Recommendations

```bash
python -m pytest build_tools/tests/generate_s3_index_test.py \
                 build_tools/tests/workflow_outputs_test.py \
                 build_tools/github_actions/tests/post_build_upload_test.py
```

Also test composability with `post_stage_upload.py` once both PRs land:
upload stage logs, then run `generate_s3_index.py` against the same
output directory to verify indexes are generated for the nested layout.

---

## Conclusion

**Approval Status: ✅ APPROVED**

Well-structured extraction of index generation to a standalone, server-side
script. Composes cleanly with our multi-arch log upload work. The per-directory
index approach works for both single-arch and multi-arch layouts, with recursive
parent indexes as a natural follow-up.
