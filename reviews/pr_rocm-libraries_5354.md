# PR Review: [hipBLASLt] Fix shard overlay convergence

* **PR:** [ROCm/rocm-libraries#5354](https://github.com/ROCm/rocm-libraries/pull/5354)
* **Author:** davidd-amd
* **Branch:** `users/davidd-amd/hipblaslt-convergence` → `develop`
* **Reviewed:** 2026-03-31
* **Status:** OPEN

---

## Summary

In TheRock's multi-shard build, each shard builds hipBLASLt for a subset of GPU targets, then all shard install trees are overlaid onto a single filesystem prefix. Three artifacts were last-writer-wins during overlay, causing metadata loss:
- `hipblasltExtOpLibrary.dat` (ExtOp op/kernel metadata)
- `TensileLiteLibrary_lazy_Mapping` (Tensile solution index)
- `hipblasltTransform.hsaco` (matrix-transform fat binary)

The fix moves all three artifacts into per-architecture subdirectories (`library/<arch>/`), making overlay additive rather than destructive. Runtime C++ code is updated to probe the per-arch path first, with fallback to the flat layout for backward compatibility. Tensile's Python build scripts learn a `libraryDir()` helper that routes single-arch builds into `library/<arch>/`. A 718-line convergence test script is included.

**Net changes:** +819 lines, -42 lines across 12 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The core approach (per-arch subdirectories + runtime fallback) is sound and well-structured. Several issues need attention before merge.

**Strengths:**

- Clean separation: build-time layout change + runtime discovery with backward-compatible fallback
- Tensile subdir guard in `tensile_host.cpp` is smart — only enters per-arch subdir if a Tensile mapping file is actually present, preventing false matches from ExtOp/Transform-only directories
- Same fix applied consistently to hipsparselt's `tensile_host.cpp`
- The `libraryDir()` helper centralizes the routing logic in one place

**Issues:**

- PR description is stale (describes HIPBLASLT_DIST_TARGETS approach; actual code uses per-arch subdirectory approach)
- Test script has hardcoded developer paths and style issues
- Code duplication in arch name trimming between two C++ files

---

## Detailed Review

### 1. PR Description vs. Actual Implementation

### ⚠️ IMPORTANT: PR description does not match implementation

The PR body describes introducing `HIPBLASLT_DIST_TARGETS`, a CMake cache variable that would make all shards produce byte-for-byte identical metadata. The actual implementation takes a different (and arguably better) approach: per-arch subdirectories that make shard output additive. There is no `HIPBLASLT_DIST_TARGETS` variable in the diff.

- **Recommendation:** Update the PR description to accurately describe the per-arch subdirectory approach. Reviewers will be confused looking for HIPBLASLT_DIST_TARGETS in the code.

### 2. extops/CMakeLists.txt

The changes move code objects and `.dat` files from `library/` to `library/<arch>/`:
- Removes premature copy of code object file (was done before ExtOpCreateLibrary.py ran)
- Creates `library/<arch>/` directory
- Copies both `.dat` and `.co` into the per-arch subdirectory

This looks correct. The `make_directory` before copy is good practice.

### 3. matrix-transform/CMakeLists.txt

Splits the single fat-binary build into per-arch single-arch HSACO builds. Each arch gets its own `hipblasltTransform_<arch>.hsaco` build artifact, copied to `library/<arch>/hipblasltTransform.hsaco`.

This is a clean refactor — the foreach loop now creates per-arch targets (`matrix-transform-cp-${arch}`) instead of a single fat-binary target.

### 4. hipblaslt-ext-op.cpp (Runtime Discovery)

### 💡 SUGGESTION: Minor — good use of `trimArchName`

The new probe uses `trimArchName(props.gcnArchName)` to strip the colon suffix (e.g., `gfx942:sramecc+:xnack-` → `gfx942`). This is consistent with existing code in the file.

The fallback to the flat path ensures backward compatibility with pre-patch installs.

### 5. rocblaslt_transform.cpp (Runtime Discovery)

### ⚠️ IMPORTANT: Duplicated arch name trimming logic

`rocblaslt_transform.cpp` manually trims the arch name:

```cpp
std::string archName = props.gcnArchName;
auto        colonPos = archName.find(':');
if(colonPos != std::string::npos)
    archName = archName.substr(0, colonPos);
```

Meanwhile `hipblaslt-ext-op.cpp` uses the existing `trimArchName()` helper for the same operation. This creates a maintenance risk — if the trimming logic needs to change (e.g., to handle a new suffix format), only one site might get updated.

- **Recommendation:** Either extract `trimArchName` to a shared header, or at minimum add a comment in `rocblaslt_transform.cpp` referencing the canonical implementation in `hipblaslt-ext-op.cpp`. Alternatively, inline the same `trimArchName` pattern if the headers don't easily share.

### 6. tensile_host.cpp (hipBLASLt) — Subdir Guard

The tightened check is well-designed:

```cpp
auto mapping_msgpack = processor_path / ("TensileLibrary_lazy_" + processor + ".dat");
auto mapping_yaml    = processor_path / ("TensileLibrary_lazy_" + processor + ".yaml");
if(std::filesystem::exists(mapping_msgpack) || std::filesystem::exists(mapping_yaml))
    path = std::move(processor_path);
```

This prevents the runtime from entering a `library/<arch>/` directory that only contains ExtOp/Transform files but no Tensile library. Good defensive coding.

### 💡 SUGGESTION: Comment accuracy

The comment says "multi-arch non-TheRock builds" — consider clarifying this to also cover the case where per-arch subdirs exist from the new layout but Tensile data is in the flat location (e.g., mixed old/new install scenarios).

### 7. tensile_host.cpp (hipsparselt)

Same guard pattern applied to hipsparselt. Consistent with the hipblaslt change.

### 8. TensileCreateLibrary/Run.py — `libraryDir()` Helper

```python
def libraryDir(outputPath: Union[str, Path], archs: Collection[str]) -> Path:
    path = Path(outputPath)
    archs = list(archs)
    if len(archs) == 1:
        return path / "library" / archs[0]
    return path / "library"
```

This is the routing logic: single-arch → per-arch subdir, multi-arch or zero-arch → flat. The single-arch case is what TheRock shards hit (each shard builds one GPU family). Standalone builds with multiple archs stay flat.

### 💡 SUGGESTION: Document the zero-arch case

When `archs` is empty (e.g., `GenerateSummations.py` passes `[]`), this falls through to flat `library/`. A brief inline comment explaining this is intentional would help future readers.

### 9. BenchmarkProblems.py, ClientWriter.py, GenerateSummations.py

These files are updated to use `libraryDir()` instead of hardcoded `library/` paths. The changes are mechanical and consistent.

One note: `CreateBenchmarkClientParametersForSizes` gains an `archs=None` parameter with `archs or []` defaulting — this is fine for backward compatibility.

### 10. test_shard_convergence.py

### ❌ BLOCKING: Hardcoded developer-specific venv path

Lines 148-151:
```python
_venv_site = "/data/davdixon/TheRock/.venv/lib/python3.12/site-packages"
if _os.path.isdir(_venv_site) and _venv_site not in _sys.path:
    _sys.path.insert(0, _venv_site)
```

This is a developer's personal path that will not exist on any other machine. It should be removed entirely — the docstring already tells users to install msgpack or activate the venv.

- **Required action:** Remove the hardcoded `_venv_site` path hack (lines 148-151).

### ⚠️ IMPORTANT: Hardcoded Python version in shebang

Line 142: `#!/usr/bin/env python3.12`

This restricts the script to Python 3.12 specifically. Should be `#!/usr/bin/env python3` unless there's a specific 3.12 feature requirement (there isn't — the code uses `3.8+` features at most: `dirs_exist_ok`, walrus operator absent, etc.).

- **Recommendation:** Change to `#!/usr/bin/env python3`.

### ⚠️ IMPORTANT: `sys.exit(1)` on import failure instead of raising exception

Lines 213-214:
```python
print("ERROR: msgpack not available.  Install via: pip install msgpack")
sys.exit(1)
```

This is a top-level script entry point, so `sys.exit` is acceptable here (it's not a library function). However, the `print("ERROR: ...")` + `sys.exit(1)` pattern makes the error invisible to callers who might `import` this module for its helpers. A bare `raise ImportError(...)` would be more Pythonic and still crash with a clear message.

- **Recommendation:** Replace with `raise ImportError("msgpack not available. Install via: pip install msgpack")`.

### 💡 SUGGESTION: Docstring placement

The module docstring (lines 152-197) appears *after* the venv site-packages hack, which means `help(test_shard_convergence)` may not pick it up correctly. Move the docstring to be the first string literal after imports.

### 💡 SUGGESTION: Mode A tests are more demonstration than test

The "before-fix" tests in Mode A simulate the bug by constructing mock data and showing that flat overlay loses entries. These are useful as documentation but they test mock behavior, not actual code. The "after-fix" tests use `shutil.copytree` to simulate overlay, which does test the directory layout. This is fine as-is but worth noting the distinction.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Remove hardcoded developer venv path from `test_shard_convergence.py` (lines 148-151)

### ✅ Recommended:

1. Update PR description to match actual implementation (per-arch subdirectory approach, not HIPBLASLT_DIST_TARGETS)
2. Fix shebang to `#!/usr/bin/env python3`
3. Share or align arch name trimming logic between `hipblaslt-ext-op.cpp` and `rocblaslt_transform.cpp`
4. Use `raise ImportError(...)` instead of `print` + `sys.exit(1)` for msgpack import failure

### 💡 Consider:

1. Add inline comment in `libraryDir()` explaining the zero-arch fallback case
2. Fix docstring placement in test script

### 📋 Future Follow-up:

1. The test script's Mode B (integration test against real build trees) is valuable — consider wiring it into CI once multi-shard builds are available in CI
2. Consider whether hipsparselt needs the same per-arch subdirectory treatment for its own ExtOp/Transform artifacts (this PR only applies the Tensile guard to hipsparselt)

---

## Testing Recommendations

- Run Mode A of `test_shard_convergence.py` (no build required) to validate the overlay simulation
- Build hipBLASLt for two different GPU targets (e.g., `gfx942` and `gfx1100`) separately, then overlay — verify all per-arch subdirectories are present
- Verify standalone single-arch and multi-arch builds still produce correct Tensile library layouts
- Test runtime loading on a real GPU to confirm the per-arch path probe works correctly

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The approach is well-designed — per-arch subdirectories with backward-compatible fallback is the right solution for shard overlay convergence. The one blocking item (hardcoded developer path in the test script) is a quick fix. The recommended items around PR description accuracy and code duplication should also be addressed before merge.
