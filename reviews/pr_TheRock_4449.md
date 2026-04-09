# PR Review: #4449 — Add --expand-family-to-targets to artifact_manager fetch

* **PR:** https://github.com/ROCm/TheRock/pull/4449
* **Author:** marbre (Marius Brehler)
* **Reviewed:** 2026-04-10
* **Base:** `main`
* **Status:** OPEN

---

## Summary

Adds `--expand-family-to-targets` flag to `artifact_manager.py fetch` that
resolves family names (e.g. `gfx110X-all`) to their constituent gfx targets
(e.g. `gfx1100`, `gfx1101`, `gfx1102`, `gfx1103`) by parsing
`cmake/therock_amdgpu_targets.cmake`. This addresses
[#4433](https://github.com/ROCm/TheRock/issues/4433) — KPACK split builds
produce per-target artifacts but callers pass family names.

**Net changes:** +326 lines, -1 line across 4 files

---

## Overall Assessment

**:white_check_mark: APPROVED** — Clean implementation with good test coverage. The approach
of parsing the CMake file as the single source of truth for the family→target
mapping is the right choice. A few suggestions below.

**Strengths:**

- Uses `cmake/therock_amdgpu_targets.cmake` as the authoritative source —
  no duplicate mapping to maintain.
- Safe to pass against non-KPACK-split buckets (family name is still matched,
  extra per-target lookups find nothing).
- Good test coverage: CMake parser tested with various formats (single-line,
  multi-line, with/without EXCLUDE_TARGET_PROJECTS, with/without FAMILY),
  family-to-targets mapping tested for self-family, explicit families, and
  deduplication. `parse_target_families` tested with mock maps.
- Lazy-loaded cache for the CMake parse avoids repeated file I/O.

---

## Detailed Review

### 1. `cmake_amdgpu_targets.py` — CMake parser

Clean implementation. The regex-based parser handles the relevant CMake
patterns well. A few observations:

### :bulb: SUGGESTION: Consider handling quoted product names with spaces in FAMILY

The tokenizer handles `"MI300A/MI300X CDNA"` correctly (quoted strings), and
the parser assumes positional args are `tokens[0]` (gfx_target) and `tokens[1]`
(product_name). This works because quoted strings with spaces are a single
token. Good.

### :bulb: SUGGESTION: `cmake_keywords` could include `FAMILY` itself

In `parse_amdgpu_targets_cmake`, the keyword set used to terminate FAMILY
collection is `{"EXCLUDE_TARGET_PROJECTS"}`. If a future CMake keyword is
added after FAMILY, this would need updating. Consider extracting the known
keywords from the `cmake_parse_arguments` call pattern, or adding a comment
noting this is intentionally minimal.

### 2. `artifact_manager.py` — Integration

### :bulb: SUGGESTION: Top-level import may fail in environments without the CMake file

The import `from _therock_utils.cmake_amdgpu_targets import ...` is at the
top of `artifact_manager.py`. The imported functions themselves are safe
(they take a path argument), but `_get_family_to_targets()` hardcodes the
path relative to `__file__`. This is fine for normal usage (the script is
always run from the repo), but if `artifact_manager.py` is ever imported
from a different context (e.g. a deployed Lambda), the hardcoded path
would fail. The lazy-load pattern mitigates this — the path is only resolved
when `--expand-family-to-targets` is actually used.

### :bulb: SUGGESTION: `getattr(args, "expand_family_to_targets", False)` in `parse_target_families`

This uses `getattr` with a default, suggesting `parse_target_families` might
be called with args that don't have this attribute (e.g. from push/copy
commands that use `_add_target_args` but not the fetch-specific flag).
Actually, looking again — `--expand-family-to-targets` is added in
`_add_target_args` which is shared by fetch, push, and copy. So the
attribute should always be present. The `getattr` is defensive but
unnecessary. Not a problem, just noting the inconsistency.

Wait — looking more carefully, `_add_target_args` is where the flag is added,
and it's called for all subparsers that need target args. So `getattr` isn't
needed. But it's harmless and defensive, so fine either way.

### 3. Tests

Good coverage. Tests use mock maps to avoid depending on the actual CMake
file contents, which makes them stable across target additions/removals.

### :bulb: SUGGESTION: `cmake_amdgpu_targets_test.py` has an extra blank line before `if __name__`

Minor formatting — there's a double blank line before `if __name__ == "__main__":`
at the end. `black` should catch this if pre-commit is run.

### 4. Integration with existing code

### :clipboard: FUTURE WORK: Wire `--expand-family-to-targets` into downstream workflows

The flag exists but no workflow passes it yet. The next step would be to add
it to workflows that call `artifact_manager.py fetch` with family names
when KPACK split is enabled:
- `build_portable_linux_python_packages.yml`
- `build_windows_python_packages.yml`
- `multi_arch_build_tarballs.yml`
- `test_artifacts_structure.yml`

This could be unconditional (the flag is safe with non-KPACK builds) or
conditional on a build config flag.

### :clipboard: FUTURE WORK: Consolidate with `amdgpu_family_matrix.py`

`amdgpu_family_matrix.py` has hardcoded `fetch-gfx-targets` per runner.
The new `cmake_amdgpu_targets.py` provides the authoritative mapping.
Consider having the matrix code use `build_family_to_targets()` instead
of maintaining a separate hardcoded list, reducing the chance of the
two going out of sync.

---

## Recommendations

### :bulb: Consider:

1. Add a comment in `_add_target_args` noting that `--expand-family-to-targets`
   is safe to pass unconditionally (even with non-KPACK builds).

### :clipboard: Future Follow-up:

1. Wire `--expand-family-to-targets` into downstream workflows.
2. Consider consolidating `amdgpu_family_matrix.py` fetch-gfx-targets with
   the new CMake-based mapping.

---

## Testing Recommendations

- `python -m pytest build_tools/tests/cmake_amdgpu_targets_test.py build_tools/tests/artifact_manager_tool_test.py -v`
- Manual test per the PR description against run 24187929660 with KPACK split artifacts
- Verify the flag is a no-op against a non-KPACK-split run (existing family names still match)

---

## Conclusion

**Approval Status: :white_check_mark: APPROVED**

Good solution to #4433. The CMake file is the right source of truth for the
family→target mapping, and the implementation is clean with thorough tests.
Ready to merge once pre-commit formatting is verified.
