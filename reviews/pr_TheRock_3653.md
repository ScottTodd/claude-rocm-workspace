# PR Review: Refactor new_amdgpu_family_matrix to use data classes

* **PR:** [#3653](https://github.com/ROCm/TheRock/pull/3653)
* **Author:** HereThereBeDragons (Laura Promberger)
* **Reviewed:** 2026-04-08
* **Status:** OPEN
* **Base:** `main` ← `users/lpromber/classify_amdgpu_matrix`

---

## Summary

Replaces the nested dictionary format in `new_amdgpu_family_matrix.py` with a
dataclass-based schema split across three files:

- `new_amdgpu_family_matrix_types.py` — dataclass definitions (`MatrixEntry`, `PlatformConfig`, etc.)
- `new_amdgpu_family_matrix_data.py` — matrix data (GPU entries, build variants, predefined groups)
- `new_amdgpu_family_matrix_test.py` — unit tests

Key design improvements: defaults-only-override pattern (only non-default values
specified), auto-discovery of GPU family membership from cmake, validation of
`is_family_default` uniqueness, case-insensitive lookup, and tiered group building.

Also bundles several data changes: gfx90X split into individual entries (#2869),
`push_on_success` removed, `tsan` build variant added, and various runner updates.

**Net changes:** +1393 lines, -508 lines across 4 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — Strong architectural improvement with good test
coverage, but has a code bug (bare `raise`), several unacknowledged data
regressions, and a fragile cmake parser that should be hardened.

**Strengths:**

- Clean dataclass hierarchy with sensible defaults
- `run_tests` auto-inference from runner presence is elegant and reduces error-prone boilerplate
- `is_family_default` validation catches config mistakes at import time
- Auto-discovery of `_GFX*` attributes eliminates registration boilerplate
- Tiered group building (`presubmit ⊂ postsubmit ⊂ nightly`) makes the subset relationship explicit
- Good test coverage (~17 test classes covering lookup, defaults, serialization, validation)
- `__test__ = False` on `TestConfig` to prevent pytest collection — nice touch

**Issues:**

- 1 blocking bug, 1 blocking data regression
- 2 important items (fragile parser, import ordering)
- Several suggestions

---

## Detailed Review

### 1. `new_amdgpu_family_matrix_data.py`

#### ❌ BLOCKING: Bare `raise` in `_parse_amdgpu_targets`

```python
if "FAMILY" not in block:
    raise
```

A bare `raise` outside an `except` block raises `RuntimeError: No active
exception to reraise` in Python 3 — the error message is useless for debugging.

**Required action:** Replace with an explicit exception:
```python
if "FAMILY" not in block:
    target = block.split()[0]
    raise ValueError(
        f"therock_add_amdgpu_target({target}) has no FAMILY argument "
        f"in {cmake_path}"
    )
```

#### ❌ BLOCKING: Data regressions — gfx1152/gfx1153 `expect_failure` dropped

Old data had `expect_failure: True` on the build config for gfx1152 and gfx1153
(both platforms). New entries use bare `PlatformConfig()` which defaults
`expect_failure` to `False`:

```python
# Old: both linux and windows had expect_failure: True in build section
GFX1152 = MatrixEntry(
    target="gfx1152",
    linux=PlatformConfig(),    # ← expect_failure defaults to False
    windows=PlatformConfig(),  # ← expect_failure defaults to False
)
```

If the old matrix had `expect_failure: True`, CI was using `continue-on-error`
for these builds. Dropping it silently will cause build failures on these targets
to block PRs. If this is intentional, it should be called out in the PR
description. If not, add `build=BuildConfig(expect_failure=True)` to both
platforms for GFX1152 and GFX1153.

#### ⚠️ IMPORTANT: Additional data change — gfx103X-dgpu windows `expect_pytorch_failure` dropped

Old gfx103X-dgpu windows test had `expect_pytorch_failure: True`. New GFX1030
windows `TestConfig` doesn't set it (defaults to `False`). This means PyTorch
builds will be attempted on gfx1030 windows where they previously were known-broken.

**Recommendation:** Either restore `expect_pytorch_failure=True` on GFX1030
windows, or confirm this was intentional and note it in the PR description.

#### ⚠️ IMPORTANT: `_parse_amdgpu_targets` is fragile

The cmake parser splits on literal strings (`"therock_add_amdgpu_target("`,
`"FAMILY"`) and takes the remainder of a single line:

```python
family_line = block.split("FAMILY")[1].split("\n")[0]
result[target] = family_line.rstrip(")").split()
```

This breaks if:
- FAMILY args span multiple lines
- A comment contains "FAMILY"
- Additional keyword args appear after FAMILY on the same line

**Recommendation:** Add a comment documenting the expected cmake format, and
consider a slightly more robust approach (e.g., regex matching `FAMILY\s+(.+?)\)`
with `re.DOTALL`). At minimum, add a test that `_parse_amdgpu_targets()` returns
expected families for a few known targets.

#### ⚠️ IMPORTANT: Import ordering

```python
from new_amdgpu_family_matrix_types import (
    ...
)

from pathlib import Path
```

PEP 8 (and the project's Python style guide) requires stdlib imports before
local imports.

**Recommendation:** Move `from pathlib import Path` above the local import.

#### 💡 SUGGESTION: Unacknowledged data additions

Several data changes beyond what the PR description covers:
- `tsan` build variant added to `all_build_variants`
- gfx942 and gfx950 now include `tsan` in their `build_variants`
- gfx942 gets `extra={"test-sandbox": ...}` runner
- gfx1101 gets `fetch_gfx_targets=["gfx1101"]` (old had `[]` with tests disabled,
  and on windows had `["gfx1100"]` → now `["gfx1101"]`)
- gfx1030 linux gets `fetch_gfx_targets=["gfx1030"]` (old had `[]`)

These could all be intentional updates bundled with the refactor. Documenting
them in the PR body helps reviewers distinguish refactor artifacts from
intentional changes.

#### 💡 SUGGESTION: `_build_groups()` comment about tiering

The tiering pattern is nice but the inline comment about `set for dedup` could
be clearer. Consider:

```python
# Groups are cumulative: presubmit ⊂ postsubmit ⊂ nightly.
# Using set union ensures no duplicates when a key appears in multiple tiers.
```

### 2. `new_amdgpu_family_matrix_types.py`

#### 💡 SUGGESTION: `lookup()` vs `get_entry()` overlap

`lookup()` and `get_entry()` have nearly identical logic — `get_entry` is
essentially `lookup` without the `EntryLookupResult` wrapper. Consider having
`get_entry` delegate to `lookup`:

```python
def get_entry(self, key: str) -> Optional[MatrixEntry]:
    result = self.lookup(key)
    return result.entry if result else None
```

This eliminates the duplicated search logic.

#### 💡 SUGGESTION: `get_default_for_family` prefix matching is implicit

The prefix matching behavior (key ending in `X` matches `key + "-*"`) is a
convention that works for the current cmake naming scheme but could surprise
future maintainers. Consider adding an explicit note about why this exists
(matching cmake family naming conventions like `gfx94X` → `gfx94X-dcgpu`).

#### 💡 SUGGESTION: `to_nested_dict` name is slightly misleading

The docstring says "Serialize all entries as a flat dict keyed by target name"
but the method is called `to_nested_dict`. The result is flat at the top level
but nested within each entry. Consider `to_dict()` instead, or keep the name
but update the docstring to clarify the nesting.

### 3. `new_amdgpu_family_matrix_test.py`

#### 💡 SUGGESTION: Add a test for `_parse_amdgpu_targets`

The cmake parser is a critical dependency (family assignment drives CI behavior).
A test that validates known targets exist and have expected families would catch
parser regressions:

```python
def test_cmake_parser_known_families(self):
    entry = amdgpu_family_info_matrix_all.get_entry("gfx942")
    self.assertIn("gfx94X-dcgpu", entry.family)
    self.assertIn("gfx94X-all", entry.family)
```

This already partially exists in `TestFamilyPopulation` — good.

#### 💡 SUGGESTION: Consider parametrizing repetitive test cases

Several test classes have very similar test methods that differ only in the key
being looked up. Using `unittest.TestCase.subTest` or pytest parametrize would
reduce boilerplate while keeping clear failure messages.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Fix bare `raise` in `_parse_amdgpu_targets` — use `raise ValueError(...)` with a descriptive message
2. Restore `expect_failure=True` for gfx1152/gfx1153 build configs (both platforms), or explicitly document the removal in the PR description

### ✅ Recommended:

1. Restore `expect_pytorch_failure=True` on GFX1030 windows, or confirm intentional removal
2. Fix import ordering in `new_amdgpu_family_matrix_data.py` (stdlib before local)
3. Add a comment to `_parse_amdgpu_targets` documenting the expected cmake format

### 💡 Consider:

1. Document all data changes (tsan, extra runners, fetch_gfx_targets changes) in PR body
2. Have `get_entry` delegate to `lookup` to eliminate duplicated logic
3. Add a direct test for the cmake parser output
4. Rename `to_nested_dict` → `to_dict` or clarify the docstring

### 📋 Future Follow-up:

1. The old `amdgpu_family_matrix.py` (non-"new" version) has a sync comment referencing the deleted file — update or remove that comment when the migration is complete
2. Consider making `_parse_amdgpu_targets` more robust (regex-based parsing) when the cmake format evolves

---

## Testing Recommendations

- Run the new test file: `python -m pytest build_tools/github_actions/tests/new_amdgpu_family_matrix_test.py`
- Verify `to_nested_dict()` output matches the old `amdgpu_family_info_matrix_all` dict for entries that should be unchanged (regression test)
- Confirm gfx1152/gfx1153 `expect_failure` behavior is intentional by checking recent CI runs on those targets

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The dataclass refactor is a clear improvement over the nested dict format — it's
more maintainable, self-documenting, and catches errors at construction time.
The test suite is solid. However, the bare `raise` is a genuine bug, and the
silent data regressions (gfx1152/1153 `expect_failure`, gfx1030 windows
`expect_pytorch_failure`) need to be confirmed as intentional or fixed before
merge to avoid breaking CI for those targets.
