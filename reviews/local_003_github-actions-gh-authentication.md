# Branch Review: github-actions-gh-authentication

* **Branch:** `github-actions-gh-authentication`
* **Base:** `main`
* **Reviewed:** 2026-01-14
* **Commits:** 1 commit (eeb69681)

---

## Summary

This PR adds `gh` CLI authentication support to `github_actions_utils.py`, allowing developers to use the GitHub CLI's OAuth tokens instead of requiring a Personal Access Token (PAT) in the `GITHUB_TOKEN` environment variable. The implementation introduces a `GitHubAPI` class that auto-detects the best available authentication method (GITHUB_TOKEN → gh CLI → unauthenticated).

**Net changes:** +358 lines, -68 lines across 2 files

---

## Overall Assessment

**✅ APPROVED** - The implementation is well-structured, properly tested, and follows good Python practices. The class-based design enables clean encapsulation of authentication state and makes testing straightforward.

**Strengths:**

- Clean class-based architecture with `GitHubAPI` encapsulating authentication state
- Proper auth priority: GITHUB_TOKEN takes precedence over gh CLI (important for CI)
- Good test coverage including mocked unit tests for auth detection
- Maintains backwards compatibility via module-level wrapper functions
- Comprehensive docstrings with reference links
- Custom `GitHubAPIError` exception for clear error handling

**No Blocking Issues**

---

## Detailed Review

### 1. GitHubAPI Class Design

**Well Designed:**
- Inner `AuthMethod` enum keeps related code together
- Private methods (`_detect_auth_method`, `_send_request_via_gh_cli`, `_send_request_via_rest_api`) clearly separate concerns
- Authentication state is cached per-instance, making tests simple (fresh instances = fresh state)
- Module singleton `_default_github_api` maintains backwards compatibility

### 2. Authentication Detection (`_detect_auth_method`)

**💡 SUGGESTION: Consider logging which auth method was selected**

Currently, users only see "Warning: No GitHub auth available" for unauthenticated mode. It could be helpful (especially for debugging) to log when gh CLI auth is being used.

```python
if result.returncode == 0:
    self._gh_cli_path = gh_path
    _log("Using gh CLI for GitHub API authentication")  # Optional
    return GitHubAPI.AuthMethod.GH_CLI
```

This is purely optional - the current behavior is fine.

### 3. gh CLI Request Handling (`_send_request_via_gh_cli`)

**Good:**
- Assertion ensures `_gh_cli_path` is set before use
- Strips base URL correctly for `gh api` command
- Explicit `encoding="utf-8"` prevents Windows encoding issues
- Error handling for both non-zero return code and empty response

### 4. REST API Request Handling (`_send_request_via_rest_api`)

**💡 SUGGESTION: Consider handling HTTP errors more robustly**

The current implementation checks status codes inside the `with urlopen()` block, but `urlopen()` will raise `HTTPError` for 4xx/5xx responses before you can check `response.status`. The 403 and non-200 checks may never execute.

```python
# Current code - status checks may not execute for error codes
with urlopen(request) as response:
    if response.status == 403:  # This won't run - HTTPError raised first
        ...
```

However, this matches the previous implementation's behavior, so it's not a regression. Consider addressing in a follow-up if HTTP error handling needs improvement.

### 5. Test Coverage

**Good:**
- `GitHubAPITest` class covers all auth detection scenarios
- Proper use of `mock.patch` to control environment
- Tests verify caching behavior and fresh instance behavior
- `setUp`/`tearDown` properly save and restore `GITHUB_TOKEN`
- Skip decorator `_skip_unless_authenticated_github_api_is_available` works with either auth method

**💡 SUGGESTION: Consider adding a test for `_send_request_via_gh_cli` error cases**

The error paths (non-zero return code, empty stdout) aren't unit tested. These could be tested with mocking:

```python
def test_gh_cli_request_failure(self):
    """gh api returning error should raise GitHubAPIError."""
    # Mock setup and assertion
```

This is optional since the integration tests exercise the happy path.

### 6. Backwards Compatibility

**Good:**
- `gha_send_request()` unchanged in signature
- `gha_get_request_headers()` unchanged in signature
- New `is_authenticated_github_api_available()` function added (not breaking)
- Existing tests continue to work

### 7. Documentation

**Good:**
- Class docstring explains the auth priority and usage
- Reference links to GitHub docs are helpful
- Method docstrings are clear and accurate

---

## Recommendations

### ✅ Recommended Before Human Review:

1. Run the full test suite to verify no regressions:
   ```bash
   python build_tools/github_actions/tests/github_actions_utils_test.py -v
   ```

### 💡 Consider:

1. Add debug logging when gh CLI auth is selected (helps users understand which auth is being used)
2. Add unit tests for `_send_request_via_gh_cli` error cases

### 📋 Future Follow-up:

1. Consider improving HTTP error handling in `_send_request_via_rest_api` - the current status checks may not execute due to `HTTPError` being raised first
2. Consider exporting `GitHubAPIError` from the module's public API if callers need to catch it specifically

---

## Testing Recommendations

1. **Already done:** Unit tests for auth detection pass
2. **Manual testing:** Verify both auth methods work:
   ```bash
   # With GITHUB_TOKEN
   GITHUB_TOKEN=... python -c "from github_actions_utils import gha_send_request; print(gha_send_request('https://api.github.com/repos/ROCm/TheRock'))"

   # With gh CLI (no GITHUB_TOKEN)
   python -c "from github_actions_utils import gha_send_request; print(gha_send_request('https://api.github.com/repos/ROCm/TheRock'))"
   ```
3. **CI verification:** Ensure CI workflows still work with GITHUB_TOKEN auth

---

## Conclusion

**Approval Status: ✅ APPROVED**

This is a well-implemented feature that improves developer experience by allowing `gh auth login` instead of requiring PATs. The code is clean, well-tested, and maintains backwards compatibility. Ready for human review.
