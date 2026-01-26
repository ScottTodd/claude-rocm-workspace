# Branch Review: artifacts-for-commit

* **Branch:** `artifacts-for-commit`
* **Base:** `main`
* **Reviewed:** 2026-01-26 (updated after typo fixes)
* **Commits:** 11 commits

---

## Summary

This PR adds two new Python scripts for finding CI artifacts by commit SHA:
- `find_artifacts_for_commit.py` — Query GitHub API for workflow runs and determine S3 artifact location
- `find_latest_artifacts.py` — Search through recent branch commits to find one with available artifacts

It also adds `gha_query_recent_branch_commits()` to `github_actions_utils.py` and includes comprehensive unit tests for all new functionality.

**Net changes:** +790 lines, -4 lines across 7 files

---

## Overall Assessment

**✅ APPROVED** - Well-structured implementation with good test coverage. The code follows project conventions and the test mocking strategy is sound.

**Strengths:**

- Clear separation between commit-specific and branch-scanning functionality
- Good mocking strategy: mock S3 checks (subject to retention), use real GitHub API (stable history)
- Descriptive field names in `ArtifactRunInfo` dataclass
- Tests cover multiple repositories (TheRock, rocm-libraries) and configurations (main, fork, Windows)
- Docstrings explain rationale (e.g., why use API vs local git log)

**No blocking or important issues.**

---

## Detailed Review

### 1. `find_artifacts_for_commit.py`

**Code Quality: Good**

The `ArtifactRunInfo` dataclass is well-designed with computed properties (`s3_path`, `s3_uri`, `s3_index_url`) that reduce duplication. The TODO comment about consolidating with `ArtifactBackend` is appropriate future work.

### 💡 SUGGESTION: Consider using logging module

The `print(..., file=sys.stderr)` calls in error paths could use Python's `logging` module for consistency with other scripts. Not blocking since verbose output is opt-in.

---

### 2. `find_latest_artifacts.py`

**Code Quality: Good**

Clean implementation that builds on `find_artifacts_for_commit`. The verbose mode provides useful progress feedback.

No issues found.

---

### 3. `github_actions_utils.py` changes

**Code Quality: Good**

The `gha_query_recent_branch_commits()` function is simple and well-documented. Good note about why API is preferred over local git log.

No issues found.

---

### 4. Tests

**Test Quality: Good**

The mocking strategy is well-documented and sound:
- Mock `check_if_artifacts_exist()` — S3 artifacts may be deleted due to retention
- Mock `gha_query_recent_branch_commits()` — Controls which commits are searched
- Real GitHub API calls — Workflow run history is stable for pinned commits

Tests cover:
- TheRock main branch commits
- Fork commits (external bucket)
- rocm-libraries (different workflow, different bucket)
- Windows platform
- Missing artifacts scenarios

**Test file naming:** Follows project convention (`*_test.py`)

**No anti-patterns detected:**
- Tests verify real GitHub API responses, not mocked data
- Mocks are targeted (S3 checks) not excessive
- Tests verify specific field values, not just that code runs

---

### 5. `upload_package_repo.py` changes

This removes the "prerelease" job option. Appears to be cleanup of unused functionality.

No issues found.

---

## Recommendations

### 💡 Consider:

1. Switch from `print()` to Python `logging` module for verbose output (can be done in follow-up)

### 📋 Future Follow-up:

1. Consolidate `ArtifactRunInfo` with `RunOutputRoot` after PR #3000 lands (noted in task file)
2. Add scenario 2: fallback search for baseline commit when direct lookup fails

---

## Testing Recommendations

Run the test suite to verify:

```bash
# All new tests
python -m pytest build_tools/tests/find_artifacts_for_commit_test.py -v
python -m pytest build_tools/tests/find_latest_artifacts_test.py -v
python -m pytest build_tools/github_actions/tests/github_actions_utils_test.py::GitHubActionsUtilsTest::test_gha_query_recent_branch_commits -v

# CLI smoke tests
python build_tools/find_artifacts_for_commit.py --commit 77f0cb2112d1d0aaae0de6088a6e4337f2488233 --artifact-group gfx110X-all
python build_tools/find_latest_artifacts.py --artifact-group gfx110X-all -v
```

---

## Conclusion

**Approval Status: ✅ APPROVED**

The implementation is solid with good test coverage. No blocking or important issues remain. The code is ready for human review.
