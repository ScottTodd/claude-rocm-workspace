# PR Review: feat: enable windows build for libhipcxx

* **PR:** [#2953](https://github.com/ROCm/TheRock/pull/2953)
* **Author:** obersteiner (Michael Obersteiner)
* **Branch:** `users/moberste/libhipcxx_enable_windows` → `main`
* **Reviewed:** 2026-03-18
* **Status:** OPEN

---

## Summary

Enables Windows build and test support for libhipcxx. Changes include removing the `disable_platforms = ["windows"]` from `BUILD_TOPOLOGY.toml`, removing the Windows exclusion for `libhipcxx` in `fetch_sources.py`, adding Windows platform to the test configuration, adding GPU architecture detection via `offload-arch`, making the test scripts cross-platform, and bumping the libhipcxx submodule.

**Net changes:** +197 lines, -52 lines across 9 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The PR has a clear broken import that will cause immediate runtime failure, plus several code quality issues that should be addressed.

**Strengths:**
- Clear motivation — enabling Windows support for libhipcxx
- Good use of `pathlib.Path` for cross-platform path handling
- Extracts `prepend_env_path` utility to eliminate platform-specific `os.pathsep` bugs
- CI test run linked and passing on Linux

**Blocking Issues:**
- Import from non-existent module `github_actions_utils`
- `shell=True` with string interpolation in `get_gpu_architecture_offload_arch`
- `subprocess.run` without `check=True` in `get_gpu_architecture_offload_arch`
- Silent failure on unsupported platform

---

## Detailed Review

### 1. Import from non-existent module

### ❌ BLOCKING: `github_actions_utils` does not exist

Both `test_libhipcxx_hipcc.py` and `test_libhipcxx_hiprtc.py` import:
```python
from build_tools.github_actions.github_actions_utils import (
    get_gpu_architecture_offload_arch,
    prepend_env_path,
)
```

But the functions are added to `github_actions_api.py`. There is no `github_actions_utils.py` file in the repository. This will cause an `ImportError` at runtime.

- **Required action:** Either change the import to `from build_tools.github_actions.github_actions_api import ...` or create a `github_actions_utils.py` module and move the functions there.

---

### 2. `get_gpu_architecture_offload_arch` quality issues

### ❌ BLOCKING: `shell=True` with f-string interpolation

```python
subprocess.run(
    f"python {THEROCK_DIR}/build_tools/setup_venv.py --index-name nightly --index-subdir gfx110X-all --packages rocm .tmpvenv",
    shell=True,
)
```

`shell=True` with a string that interpolates `THEROCK_DIR` is a command injection risk. If `THEROCK_DIR` ever contains spaces or shell metacharacters, this breaks. Use a list form instead:

```python
subprocess.run(
    ["python", str(THEROCK_DIR / "build_tools" / "setup_venv.py"),
     "--index-name", "nightly", "--index-subdir", "gfx110X-all",
     "--packages", "rocm", ".tmpvenv"],
    check=True,
)
```

- **Required action:** Use list form for `subprocess.run` and remove `shell=True`.

### ❌ BLOCKING: Missing `check=True` on venv setup

The first `subprocess.run` call (venv setup) doesn't use `check=True`. If it fails, the script silently continues and then fails later trying to run `offload-arch` from the non-existent venv — producing a confusing error.

- **Required action:** Add `check=True` to the venv setup `subprocess.run` call, or handle the failure explicitly.

### ⚠️ IMPORTANT: Debug logging left in

```python
logging.info(f"DEBUG:{lines}")
```

This looks like leftover debug output. Use a proper log message or remove it.

- **Recommendation:** Change to a descriptive message like `logging.info(f"offload-arch output: {lines}")` or remove.

### ⚠️ IMPORTANT: Duplication with `get_first_gpu_architecture`

There is already a `get_first_gpu_architecture()` function in the same file (`github_actions_api.py:568`) that detects GPU architecture via `rocminfo`. The new `get_gpu_architecture_offload_arch` adds a second, independent mechanism that installs a temporary venv and runs `offload-arch`.

- **Recommendation:** Document why `offload-arch` is needed instead of `rocminfo` (is `rocminfo` not available on Windows?), or consolidate with a fallback pattern.

### ⚠️ IMPORTANT: Hardcoded `gfx110X-all` artifact group

The venv setup uses `--index-subdir gfx110X-all`, which hardcodes a specific GPU family. This will produce incorrect architecture detection for machines with non-gfx110X GPUs.

- **Recommendation:** Either parameterize the artifact group or document why `gfx110X-all` is always correct here.

---

### 3. Test scripts — platform handling

### ❌ BLOCKING: Silent failure on unsupported platform

Both test scripts have:
```python
if is_windows:
    HIPCC_BINARY_NAME = "hipcc.exe"
elif is_linux:
    HIPCC_BINARY_NAME = "hipcc"
else:
    print("Incompatible platform!")
```

On an unsupported platform, this prints a message but leaves `HIPCC_BINARY_NAME` undefined, causing a `NameError` later. Per the [Python style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/python_style_guide.md#fail-fast-behavior), use `raise RuntimeError(...)` instead.

- **Required action:** Replace `print(...)` with `raise RuntimeError(f"Unsupported platform: {platform.system()}")`.

### ⚠️ IMPORTANT: Module-level side effects

Both test scripts call `get_gpu_architecture_offload_arch(THEROCK_DIR)` at module level (outside any function). This means importing the module triggers a subprocess that installs a venv and runs `offload-arch`. This makes the scripts impossible to test or import without side effects.

- **Recommendation:** Move GPU architecture detection inside the `if __name__ == "__main__":` block or into a function.

### 💡 SUGGESTION: Inconsistent use of `.as_posix()` vs native paths

Some CMake args use `.as_posix()`:
```python
f"-DHIP_HIPCC_EXECUTABLE={(THEROCK_BIN_PATH / HIPCC_BINARY_NAME).as_posix()}",
```
While others don't:
```python
f"-DCMAKE_CXX_COMPILER={THEROCK_BIN_PATH / HIPCC_BINARY_NAME}",
```

Be consistent — if CMake needs forward slashes on Windows, use `.as_posix()` everywhere. If not, don't use it at all.

---

### 4. Build configuration changes

### 💡 SUGGESTION: `-DCMAKE_CXX_STANDARD=17` added without explanation

`math-libs/CMakeLists.txt` adds `-DCMAKE_CXX_STANDARD=17`. Is this Windows-specific? A comment explaining why this is needed would help future maintainers understand if it can be removed later.

---

### 5. Linux test command changes

### ⚠️ IMPORTANT: Linux test commands changed as side effect

The Linux paths in the test scripts also changed — the `test_libhipcxx.sh` and `hiprtc_libhipcxx.sh` invocations now pass additional `-cmake-options` that weren't there before:
```python
f"-DHIP_HIPCC_EXECUTABLE=... -DCMAKE_HIP_COMPILER_ROCM_ROOT=... -DCMAKE_HIP_ARCHITECTURES=..."
```

This changes Linux behavior too, not just Windows. Was this intentional? These additional flags (especially `CMAKE_HIP_ARCHITECTURES`) might constrain builds that previously auto-detected the architecture.

- **Recommendation:** Confirm the Linux test path was intentionally changed and tested.

---

### 6. Submodule bump

The libhipcxx submodule is bumped from `254e50406a` to `e1d468204b`. The review trusts that this is the correct commit with Windows support.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Fix import: `github_actions_utils` → `github_actions_api` (or create the module)
2. Remove `shell=True` and use list form for `subprocess.run` in `get_gpu_architecture_offload_arch`
3. Add `check=True` to the venv setup `subprocess.run` call
4. Replace `print("Incompatible platform!")` with `raise RuntimeError(...)`

### ✅ Recommended:

1. Remove or fix debug logging (`DEBUG:{lines}`)
2. Document why `offload-arch` is used instead of `get_first_gpu_architecture`/`rocminfo`
3. Address hardcoded `gfx110X-all` artifact group
4. Move module-level subprocess calls into functions
5. Confirm Linux test behavior changes are intentional

### 💡 Consider:

1. Consistent `.as_posix()` usage
2. Comment explaining `-DCMAKE_CXX_STANDARD=17`

---

## Testing Recommendations

- Verify Windows CI passes end-to-end (the linked CI run only shows Linux)
- Verify Linux tests still pass with the added `-cmake-options` flags
- Test on a non-gfx110X GPU to confirm `offload-arch` detection works

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The PR has a clear goal and the approach is sound, but the broken import (`github_actions_utils` doesn't exist) will cause immediate runtime failure. The `shell=True` usage and silent platform failure also need fixing before merge. Once the blocking issues are addressed, this should be a straightforward enable.
