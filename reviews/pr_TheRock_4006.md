# PR Review: Implement triton-windows integration

* **PR:** [#4006](https://github.com/ROCm/TheRock/pull/4006)
* **Author:** m-gallus (Michał Gallus)
* **Reviewed:** 2026-03-17
* **Status:** OPEN
* **Branch:** `michal/triton-windows` → `main`

---

## Summary

Adds Windows support for building Triton wheels via the [triton-windows](https://github.com/triton-lang/triton-windows) fork. Changes span two files: `build_prod_wheels.py` (LLVM download + Windows build path) and `pytorch_triton_repo.py` (platform-aware repo selection). A new commit pin file `triton-windows.txt` is added.

**Net changes:** +204 lines, -22 lines across 3 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** - Good feature with clear motivation, but has a security issue (unsafe tarfile extraction), a dead `--patch` flag, and the Windows build path skips version suffix handling and triton installation that the Linux path performs.

**Strengths:**

- Clear motivation and well-documented PR description with test evidence
- Clean platform branching — Windows vs Linux paths are clearly separated
- LLVM caching with hash validation avoids redundant 500MB downloads
- Proper use of existing helpers (`find_built_wheel`, `copy_to_output`, `run_command`)

**Issues:**

- ❌ BLOCKING: Unsafe `tarfile.extractall()` (path traversal)
- ❌ BLOCKING: `--patch` flag added but never consumed
- ⚠️ IMPORTANT: Windows triton build skips version suffix and `pip install`
- ⚠️ IMPORTANT: Windows env constructed from `os.environ` instead of passed `env`
- ⚠️ IMPORTANT: `torch_dir` validation skipped on Windows even when torch_dir is used later

---

## Detailed Review

### 1. `build_prod_wheels.py` — `download_llvm_for_triton_windows()`

#### ❌ BLOCKING: Unsafe `tarfile.extractall()` — path traversal risk

`tarfile.extractall()` without filtering is vulnerable to path traversal attacks via crafted tar entries with `..` components. Since the archive is downloaded from an external URL over HTTPS, the risk is moderate (requires compromise of the blob storage), but Python 3.12+ emits a `DeprecationWarning` and future versions will raise an error.

```python
with tarfile.open(download_path, "r:gz") as tar:
    tar.extractall(triton_dir.parent)
```

**Required action:** Use the `filter` parameter (Python 3.12+):
```python
tar.extractall(triton_dir.parent, filter="data")
```
Or if supporting older Python versions, use `tar.extractall(triton_dir.parent, filter="data")` with a try/except fallback. The `"data"` filter blocks path traversal, absolute paths, and unsafe permissions.

#### ⚠️ IMPORTANT: Windows build path skips version suffix handling

The Linux `do_build_triton` path processes `TRITON_WHEEL_VERSION_SUFFIX` and `args.version_suffix`, then installs the built wheel and returns the installed version string. The Windows path skips all of this:

- No `version_suffix` env var propagation
- No `pip install` of the built wheel
- Returns the version parsed from the wheel filename instead of the installed version

This means:
1. `--version-suffix` has no effect on Windows triton builds
2. The built wheel isn't installed, so downstream PyTorch builds that `import triton` during configuration may fail

**Recommendation:** Either replicate the version suffix and install logic, or document in a comment why it's intentionally different for triton-windows (e.g., triton-windows handles versioning differently).

#### ⚠️ IMPORTANT: Windows env constructed from `os.environ` not passed `env`

```python
windows_env = dict(os.environ)
```

The `env` parameter passed to `do_build_triton` contains build environment settings (like `TRITON_WHEEL_NAME`). The Windows path ignores this and builds from `os.environ`, potentially missing env vars set by the caller. The Linux path uses the `env` parameter via `run_command(..., env=env)`, where `run_command` merges it with `os.environ`.

**Recommendation:** Start from the passed `env` dict rather than raw `os.environ`:
```python
windows_env = dict(os.environ)
windows_env.update(env)  # Include caller's env settings
windows_env.update({...})  # Then add Windows-specific overrides
```

#### 💡 SUGGESTION: `urllib.request.urlretrieve` lacks progress indication

For a ~500MB download, `urlretrieve` provides no progress feedback. The print message says "this may take a few minutes" but the user gets no indication it's working. Consider using `urllib.request.urlopen` with chunked reading and periodic progress output, or just note this as acceptable for CI environments.

### 2. `pytorch_triton_repo.py` — Platform-aware checkout

#### ❌ BLOCKING: `--patch` flag added but never consumed

The PR adds a `--patch` argument:
```python
checkout_p.add_argument(
    "--patch",
    action=argparse.BooleanOptionalAction,
    default=default_patch,
    help="Apply patches for the repo-hashtag",
)
```

And sets `args.patch = False` on Windows. But `args.patch` is never read by `repo_management.do_checkout()` or any other code. This is dead code.

**Required action:** Either:
1. Remove the `--patch` flag entirely if patching isn't implemented yet
2. Wire it into the checkout flow if it's intended to control behavior

#### ⚠️ IMPORTANT: `torch_dir` validation moved inside `else` but Windows path may still need it

The PR moves the `torch_dir.exists()` check inside the Linux-only branch. However, `torch_dir` is still a required argument — if a Windows user forgets to pass `--torch-dir` but passes a non-existent default path, there's no error until something later tries to use it. Currently the Windows path doesn't use `torch_dir`, so this is technically correct but fragile.

**Recommendation:** Add a comment noting that Windows doesn't use `torch_dir`, or make `--torch-dir` optional when on Windows.

#### 💡 SUGGESTION: `get_triton_windows_pin()` returns `None` silently

```python
def get_triton_windows_pin() -> str | None:
    pin_file = COMMIT_PINS_DIR / "triton-windows.txt"
    if pin_file.exists():
        return pin_file.read_text().strip()
    return None
```

The caller falls back to `"main-windows"` branch if the pin file is missing. Since the pin file is committed in this PR, a missing file would indicate a packaging/checkout problem. Consider raising an error instead of silently falling back, consistent with the fail-fast principle in the style guide.

### 3. `ci_commit_pins/triton-windows.txt`

No issues. Pin file contains a full SHA hash: `6fe895f6b494b2ffc688e1e552dc2d4a8b5ae3b3`.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Use `filter="data"` with `tarfile.extractall()` to prevent path traversal
2. Remove or wire up the dead `--patch` argument

### ✅ Recommended:

1. Include the caller's `env` dict in the Windows build environment
2. Handle version suffix for Windows triton builds (or document why it's skipped)
3. Consider making `--torch-dir` optional on Windows or adding a guard comment

### 💡 Consider:

1. Fail-fast if `triton-windows.txt` pin file is missing rather than falling back to `main-windows`
2. Progress indication for the LLVM download

### 📋 Future Follow-up:

1. Unit tests for `download_llvm_for_triton_windows` and `get_triton_windows_pin` — the PR author noted no existing triton tests for Linux; this could be a good starting point for both platforms
2. CI workflow integration for Windows triton builds (not part of this PR)

---

## Testing Recommendations

- Verify the Windows build with `--version-suffix` to confirm the suffix appears (or doesn't) in the wheel filename
- Test that the built triton wheel can be imported by PyTorch during its configure step
- Test the LLVM caching: run twice and verify the second run skips the download

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The tarfile security issue and dead `--patch` flag are straightforward fixes. The env/version-suffix gaps are more impactful — if the Windows triton build is meant to integrate with the full PyTorch build pipeline (not just standalone wheel generation), those need attention. Otherwise, document the intentional differences.
