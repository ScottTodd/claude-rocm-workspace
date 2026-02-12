# Branch Review: multi-arch-windows-ci-1

* **Branch:** `multi-arch-windows-ci-1`
* **Base:** `main`
* **Reviewed:** 2026-02-12
* **Commits:** 1 commit

---

## Summary

Adds `multi_arch_build_portable_windows.yml`, a 3-stage (foundation → compiler-runtime → math-libs) build pipeline for Windows, mirroring the Linux multi-arch pipeline structure. This is the first deliverable of workstream 1 for the multi-arch Windows CI task.

**Net changes:** +464 lines across 1 new file

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** - The workflow is well-structured and closely follows the Linux multi-arch pipeline. Two issues need attention before this can work correctly in CI: the cmake command differs from `build_configure.py` in ways that may cause build failures (missing linker path, compiler path difference), and `GITHUB_PATH` appends are malformed. Neither is hard to fix.

**Strengths:**
- Clean 3-stage pipeline structure matching the Linux pattern
- Correct stage dependencies (foundation → compiler-runtime → math-libs)
- Proper per-arch matrix fan-out in math-libs
- Consistent use of `configure_stage.py` and `artifact_manager.py`
- All actions pinned to SHAs

---

## Detailed Review

### 1. CMake configure vs `build_configure.py` divergence

#### ⚠️ IMPORTANT: Missing `CMAKE_LINKER` for Windows

The existing `build_windows_artifacts.yml` calls `build_configure.py`, which sets three Windows-specific compiler/linker paths (`build_configure.py:78-84`):

```python
"windows": [
    f"-DCMAKE_C_COMPILER={vctools_install_dir}/bin/Hostx64/x64/cl.exe",
    f"-DCMAKE_CXX_COMPILER={vctools_install_dir}/bin/Hostx64/x64/cl.exe",
    f"-DCMAKE_LINKER={vctools_install_dir}/bin/Hostx64/x64/link.exe",
    "-DTHEROCK_BACKGROUND_BUILD_JOBS=4",
]
```

The new workflow relies on the `windows-release` preset for compiler paths (which sets `cl.exe` without full path via `windows-base`) and doesn't set `CMAKE_LINKER` at all. The preset also doesn't set it.

With `ilammy/msvc-dev-cmd` in the PATH, CMake *should* find `link.exe` automatically. But the full-path approach in `build_configure.py` exists for a reason — PATH-based discovery can be fragile on these runners if multiple MSVC versions are installed or if PATH ordering is wrong.

**Recommendation:** Either replicate the `build_configure.py` Windows platform options, or verify on the CI runner that the preset-based approach resolves the correct `link.exe`. At minimum, add `-DCMAKE_LINKER` to match the existing behavior:

```yaml
cmake -B "$BUILD_DIR" -S . -GNinja \
  --preset ${{ inputs.build_variant_cmake_preset }} \
  ...
  -DCMAKE_LINKER="$VCToolsInstallDir/bin/Hostx64/x64/link.exe" \
```

Or directly use `build_configure.py`'s platform options as `-D` flags.

#### 💡 SUGGESTION: Missing `BUILD_TESTING=ON`

`build_configure.py` passes `-DBUILD_TESTING=ON` but the new workflow doesn't. For staged builds this may be intentional (tests run in a separate workflow), but if any test binaries need to be included in artifacts, they won't be built.

### 2. GITHUB_PATH appends

#### ⚠️ IMPORTANT: Malformed GITHUB_PATH append

Lines like this appear in all three stages:

```bash
echo "$PATH;C:\Strawberry\c\bin" >> $GITHUB_PATH
```

`GITHUB_PATH` expects one directory per line. This writes the entire current `$PATH` contents plus `;C:\Strawberry\c\bin` as a single line. The correct form is:

```bash
echo "C:\Strawberry\c\bin" >> $GITHUB_PATH
```

Same issue with the awscli path append. This is copied from the existing `build_windows_artifacts.yml` (line 98-101), so the existing workflow has the same bug. It probably "works" because GitHub Actions is lenient about PATH parsing, but it's still wrong and could cause path-length issues.

**Recommendation:** Fix in this workflow. Optionally, fix the existing workflow in a separate PR.

### 3. Input declarations

#### 💡 SUGGESTION: Unused inputs

`use_prebuilt_artifacts`, `expect_failure`, `build_variant_label`, `build_variant_suffix`, and `test_type` are declared as inputs but not referenced by any step. The Linux build workflow also declares some unused inputs for pass-through consistency. This is harmless but worth being aware of — `use_prebuilt_artifacts` in particular is consumed by the CI orchestration layer (to decide whether to call this workflow at all), not by this workflow itself.

#### 💡 SUGGESTION: Input set differs from Linux

The Linux build workflow declares `test_labels` and `artifact_run_id` inputs (also unused by the build steps). The Windows workflow omits them. This doesn't affect functionality since GitHub Actions silently drops undeclared inputs, but maintaining parity would make the interface more predictable when writing the orchestration layer.

### 4. Consistency with Linux pipeline

#### 💡 SUGGESTION: `ccache -s` vs `ccache -s -v`

The Linux pipeline uses `ccache -s -v` (verbose stats) in the Report step, while the Windows workflow uses `ccache -s`. Minor inconsistency.

#### 💡 SUGGESTION: `THEROCK_BACKGROUND_BUILD_JOBS` context

The `-DTHEROCK_BACKGROUND_BUILD_JOBS=4` flag is Windows-specific (not in the Linux pipeline). This is correct — it comes from `build_configure.py`'s Windows platform options. A brief comment in the cmake configure step noting why would help future readers:

```yaml
-DTHEROCK_BACKGROUND_BUILD_JOBS=4 `# Windows memory pressure` \
```

### 5. AWS credentials pattern

The AWS credential setup follows the Linux pattern correctly:

| Stage | Fetch credentials | Push credentials (refresh) |
|-------|------------------|---------------------------|
| foundation | `always()` (for push) | — |
| compiler-runtime | Before fetch | Before push (refresh) |
| math-libs | Before fetch | Before push (refresh) |

One note: in `foundation`, the AWS config uses `if: ${{ always() && ... }}`. Since there's no fetch step in foundation, `always()` means credentials are configured even on build failure. This matches Linux and is correct (allows the push step to decide independently).

### 6. Security

No concerns. All actions pinned to SHAs. Inputs used in `run:` blocks are from trusted workflow call inputs (not user-controllable PR data). AWS role assumption uses OIDC. The `special-characters-workaround: true` is required for Windows runners.

---

## Recommendations

### ⚠️ IMPORTANT (should address):

1. **Verify `CMAKE_LINKER` discovery** on the CI runner, or explicitly set it to match `build_configure.py` behavior
2. **Fix `GITHUB_PATH` appends** — remove the `$PATH;` prefix (use just the directory)

### 💡 SUGGESTIONS (nice to have):

3. Use `ccache -s -v` for consistency with Linux
4. Consider adding `test_labels` / `artifact_run_id` inputs for parity with Linux
5. Add comment explaining `THEROCK_BACKGROUND_BUILD_JOBS=4`
6. Consider adding `BUILD_TESTING=ON` if test binaries should be in artifacts

### 📋 FUTURE WORK (workstream 2, out of scope):

7. Switch ccache to `setup_ccache.py` + bazel-remote (replaces GitHub Actions cache)
8. Remove redundant DVC setup (already in base image)
9. Switch chocolatey to winget
10. Remove redundant `actions/setup-python` if 3.13 from base image is acceptable
11. Move repeated environment setup into scripts (both platforms together)

---

## Testing Recommendations

- `workflow_dispatch` of `multi_arch_ci.yml` on the branch with `linux_amdgpu_families: ""` and `windows_amdgpu_families: gfx1151` to test Windows-only
- Verify cmake configure succeeds (catches any preset/flag conflicts)
- Verify artifact_manager push/fetch works between stages
- Check ccache stats in Report step to confirm caching works

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The workflow structure is solid and follows the established patterns well. The two main items to address are the cmake linker configuration (verify or fix) and the GITHUB_PATH malformation. After those, this is ready for CI testing.
