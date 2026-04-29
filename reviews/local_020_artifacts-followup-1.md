# Branch Review: artifacts-followup-1

* **Branch:** `artifacts-followup-1`
* **Base:** `main`
* **Reviewed:** 2026-03-10
* **Commits:** 2 commits

---

## Summary

Reorders component sections in all 47 artifact TOML descriptors to follow the extends chain order (`lib → run → dbg → dev → doc → test`), replacing the previous alphabetical ordering. Also updates TOML examples and the CMake COMPONENTS list in `docs/development/artifacts.md` to match.

**Net changes:** +199 lines, -205 lines across 48 files

---

## Overall Assessment

**✅ APPROVED** - Pure cosmetic reordering. TOML content is semantically identical (verified programmatically). All existing tests pass.

**Strengths:**

- Makes the processing priority visible at a glance — earlier components in the file claim files first
- Consistent ordering across all 47 descriptors (previously a mix of alphabetical and ad-hoc)
- Docs updated to match
- Verified TOML semantic equivalence via `tomllib.loads()` comparison
- Pre-commit and all artifact tests pass

---

## Detailed Review

### 1. TOML Descriptor Reordering (47 files)

No issues. The transformation is mechanical and preserves:
- Comment-block boundaries (subproject grouping)
- Basedir sub-grouping within each comment block
- Trailing blank lines between blocks
- All key-value content (includes, excludes, optional flags, etc.)

### 2. Documentation Update (`docs/development/artifacts.md`)

### 💡 SUGGESTION: CMake COMPONENTS list in docs may not match actual source

The COMPONENTS list on line ~122 was reordered from `dev, doc, lib, run` to `lib, run, dev, doc`. This is a docs-only example, but if anyone copies it, the CMake side doesn't care about ordering (it's just a list of component names to activate). Fine as-is — the ordering serves as documentation of the extends chain.

### 💡 SUGGESTION: `ls` output still shows alphabetical order

The `ls -1d` output on lines 18-33 still shows alphabetical order (base_dbg before base_lib). This is correct since `ls` sorts alphabetically, but it doesn't match the extends chain emphasis of the rest of the doc. Not worth changing since it's realistic command output.

### 3. Test File (`artifacts_test.py`)

Correctly left unchanged. The reverse-ordering in `ComponentScannerTest` (doc, dev, dbg, lib, run) is intentional — the comment says "Note: in reverse extends order, this ensures that the worklist traverses properly." This tests that the worklist resolver handles arbitrary descriptor ordering.

---

## Recommendations

### ✅ Recommended:

1. None — ready to land.

### 💡 Consider:

1. Adding a comment in `artifact_builder.py` near `ComponentDefaults.ALL` noting that TOML files follow this ordering convention, so future contributors maintain it.

### 📋 Future Follow-up:

1. A lint check (pre-commit or CI) that verifies TOML component ordering matches the extends chain, preventing drift as new descriptors are added.

---

## Testing Recommendations

- All existing artifact tests pass (`artifacts_test.py`, `artifact_descriptor_overlap_test.py`)
- No functional behavior change — TOML semantic content verified identical
- CI build would confirm no regressions, but this is cosmetic-only

---

## Conclusion

**Approval Status: ✅ APPROVED**

Straightforward cosmetic change that improves readability of artifact descriptors. Ready to merge.
