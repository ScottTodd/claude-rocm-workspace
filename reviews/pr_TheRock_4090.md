# PR Review: Switch wheel filtering from blacklist to whitelist

* **PR:** [ROCm/TheRock#4090](https://github.com/ROCm/TheRock/pull/4090)
* **Author:** marbre (Marius Brehler)
* **Branch:** `users/marbre/update_dependencies-whitelist` → `main`
* **Reviewed:** 2026-03-20
* **Commits:** 2

---

## Summary

Replaces 13 fragile substring-based blacklist checks in `update_dependencies.py` with
a structured `is_wheel_allowed()` function that parses PEP 427 wheel filenames and
checks platform and Python tags against explicit allowlists. Adds comprehensive test
coverage for allowed, rejected, and edge-case wheel filenames.

**Net changes:** +183 lines, -39 lines across 3 files

---

## Overall Assessment

**✅ APPROVED** — Clean, well-motivated refactor with good test coverage.

**Strengths:**

- Correctly identifies the fragility of blacklist-based filtering — new PyPI platforms
  are admitted by default, which is the wrong default for an S3 upload tool
- `is_wheel_allowed()` is well-structured: parses the PEP 427 stem, checks platform
  and Python tags independently against explicit sets
- The manylinux `startswith`/`endswith` guard correctly rejects `musllinux_*_x86_64`
  and `macosx_*_x86_64` which share the `_x86_64` suffix
- Test cases are thorough, covering allowed, rejected-platform, rejected-python, and
  edge cases (non-wheels, malformed filenames, empty string)
- Extracting `is_wheel_allowed()` as a standalone function makes it testable without
  mocking S3/network — good design

**No blocking issues.**

---

## Detailed Review

### 1. `update_dependencies.py` — `is_wheel_allowed()`

#### 💡 SUGGESTION: Behavioral change with `typing_extensions` / `py310` tags

The PR description says Python tags `py3` (pure-Python) are allowed. The second commit
tightened `python_tag.startswith("py")` to `python_tag == "py3"`, which is good — it
rejects `py2` and `py2.py3`. However, this also means `py310` or similar compound
pure-Python tags would be rejected.

In practice this is fine — PyPI pure-Python wheels use `py3`, not `py310` — but it's
worth noting the original first commit allowed `typing_extensions-4.12.0-py310-none-any.whl`
and the second commit removed that test case. The first commit's test file had this as
an allowed case. The tightening to `== "py3"` is the correct choice since `py310` is not
a real PyPI tag pattern.

No action needed — just noting the deliberate design choice.

#### 💡 SUGGESTION: Consider `py3`-prefixed tags like `py312`

Pure-Python wheels with minimum version constraints can use tags like `py312`
(meaning "Python 3.12+"). The current `== "py3"` check would reject these. This
is unlikely to appear for the packages in `PACKAGES_PER_PROJECT` today, but if
it does in the future, the whitelist approach will correctly reject them (and a
maintainer would need to add the tag). This is arguably the right behavior — just
documenting it.

#### 💡 SUGGESTION: Comment terminology — "blacklist" / "whitelist"

The comments use "Whitelist" and reference "the blacklist." Some projects prefer
"allowlist" / "blocklist." The PR title already says "whitelist" so this is
consistent with the PR's own language, but if the project has a preference for
inclusive terminology, the comments could be updated. Minor nit.

### 2. `test_update_dependencies.py`

Tests are well-structured and cover the important cases:

- **Allowed:** linux_x86_64, manylinux variants, pure-Python, win_amd64
- **Rejected platforms:** win32, win_arm64, musllinux, macOS (including `_x86_64` suffix
  variant), aarch64, i686, iOS, RISC-V
- **Rejected Python:** cp39 (too old), PyPy, free-threaded (cp313t), future (cp314),
  py2, py2.py3
- **Edge cases:** tar.gz, zip, malformed, empty string

This is a good test suite that tests behavior, not implementation.

### 3. `README.md`

The added "Running tests" section is appropriate — concise, tells the reader how to
run the tests and that no AWS credentials are needed.

### 4. Behavioral difference: `win_amd64` now allowed

The old blacklist didn't filter `win_amd64`, so Windows x64 wheels were uploaded.
The new allowlist explicitly includes `win_amd64`, preserving this behavior. This is
correctly documented in the code comment. Good.

### 5. Behavioral difference: old blacklist used substring matches

The old code used bare `in` checks like `if "-pp3" in pkg`. This would match anywhere
in the filename (including the package name or version string). The new approach parses
the wheel stem and checks specific tag positions, which is more precise. This is a
strict improvement.

---

## Recommendations

### ✅ Recommended:

1. None — the PR is ready as-is.

### 💡 Consider:

1. Terminology: "allowlist" / "blocklist" instead of "whitelist" / "blacklist" in
   comments if the project has a preference.

### 📋 Future Follow-up:

1. The `upload_missing_whls` function still uses `print()` for warnings/errors rather
   than logging or exceptions (e.g., `print(f"Warning: Version {target_version} not found")`).
   This predates this PR and is out of scope.

---

## Testing Recommendations

- Run `python -m pytest build_tools/third_party/s3_management/test_update_dependencies.py -v`
  to verify all test cases pass
- Consider a quick manual check with `--dry-run` to verify the new filtering matches
  the old behavior for actual PyPI package listings (e.g., `numpy`, `sympy`)

---

## Conclusion

**Approval Status: ✅ APPROVED**

Well-motivated refactor that replaces fragile substring blacklist checks with structured
PEP 427 wheel filename parsing against explicit allowlists. Test coverage is thorough.
No correctness issues found. The behavioral changes (tighter matching, explicit
`win_amd64` inclusion) are all improvements or preservation of existing behavior.
