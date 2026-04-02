# PR Review: Add per-ISA device wheels for kpack-split artifacts

* **PR:** [#4308](https://github.com/ROCm/TheRock/pull/4308)
* **Author:** stellaraccident (Stella Laurenzo)
* **Base:** `main` ← `users/stella/kpack-py-packaging`
* **Reviewed:** 2026-04-02
* **Net changes:** +303 / -7 across 5 files

---

## Summary

When `KPACK_SPLIT_ARTIFACTS` is enabled in the build, the Python packaging pipeline now produces arch-neutral host wheels alongside per-ISA device wheels instead of fat per-family wheels with embedded device code. This introduces a new `rocm-sdk-device-{target_family}` wheel template, a `device` `PackageEntry`, a `populate_device_files()` method (straight copy, no RPATH processing), and a branching `_run_kpack_split()` / `_run_legacy()` split in `build_python_packages.py`. The legacy path is structurally unchanged.

---

## Overall Assessment

**✅ APPROVED** — Well-structured change with clear separation between legacy and kpack-split paths. The new code is logically sound, the device template is correctly wired, and the legacy path is preserved intact.

**Strengths:**

- Clean architectural split: `_run_kpack_split()` vs `_run_legacy()` keeps the two modes readable and independent
- Device wheel correctly overlays into the libraries platform directory so the kpack runtime finds files in the right place
- `populate_device_files()` avoids unnecessary RPATH/soname processing for binary data files
- `install_requires` pins the device wheel to the exact libraries version
- `exclude_components=["test"]` in the kpack-split devel path is well-motivated

**Issues:**

- Missing documentation update for kpack-split mode in `python_packaging.md`
- Missing `device_test.py` and unit test coverage for new code paths
- A few minor style/robustness concerns below

---

## Detailed Review

### 1. `build_tools/build_python_packages.py`

#### 💡 SUGGESTION: `load_therock_manifest` hardcoded artifact layout path

The manifest path is constructed as a deeply nested literal:
```
artifact_dir / "base_lib_generic" / "base" / "aux-overlay" / "stage" / "share" / "therock" / "therock_manifest.json"
```

This is fragile if the artifact layout changes. Not blocking since this is consistent with how other parts of the codebase handle artifacts, but worth noting.

---

#### 💡 SUGGESTION: Kpack-split meta sdist doesn't handle multi-arch dist dirs

The legacy path puts per-family meta sdists into `dist/{target_family}/` when `multi_arch` is True. The kpack-split path creates a single generic meta with `target_family=None` and writes to the default dist dir. This is likely intentional (kpack-split inherently handles multi-arch via separate device wheels), but worth confirming the downstream consumer (`build_prod_wheels.py`, find-links) can discover and use these correctly.

---

#### 💡 SUGGESTION: `device_artifact_filter` could share the library name list

`device_artifact_filter` duplicates the library name list from `libraries_artifact_filter`:
```python
# libraries_artifact_filter
an.name in ["blas", "fft", "hipdnn", "miopen", "miopenprovider", "hipblasltprovider", "rand", "rccl"]

# device_artifact_filter
an.name in ["blas", "fft", "hipdnn", "miopen", "miopenprovider", "hipblasltprovider", "rand", "rccl"]
```

These are identical. If a new library is added to one but not the other, the device wheel will silently miss files (or the libraries wheel will bundle device code it shouldn't). A shared constant would prevent drift.

**Recommendation:** Extract to a module-level constant like `_LIBRARY_ARTIFACT_NAMES`.

---

### 2. `build_tools/_therock_utils/py_packaging.py`

#### 💡 SUGGESTION: Duplicate `libraries_entry` lookup in device `__init__`

The device package looks up `self.params.dist_info.ALL_PACKAGES["libraries"]` twice in `__init__` — once to write `LIBRARIES_DIST_NAME`/`LIBRARIES_PY_PACKAGE_NAME` into dist_info, and once to set `_platform_dir`. Consider caching in a local variable.

---

#### 💡 SUGGESTION: `dist_package_template` override via string exec

The kpack-split mode overrides the libraries package template by appending executable Python to `dist_info_contents`:
```python
'ALL_PACKAGES["libraries"].dist_package_template = "rocm-sdk-libraries"\n'
```

This works but is a bit opaque — it's a string that mutates a global dict entry when `exec`'d. The existing codebase already uses this pattern (appending `__version__`, `DEFAULT_TARGET_FAMILY`, etc.) so it's consistent, but this one is a side-effecting mutation rather than a simple assignment. Not blocking; just noting the pattern is getting stretched.

---

#### ⚠️ IMPORTANT: `populate_device_files` doesn't log the count of copied files

`populate_runtime_files` has detailed logging (via symlink resolution, soname processing, etc.). `populate_device_files` logs the artifact basedirs but doesn't log how many files were actually copied. A summary line at the end (e.g., `log(f"  Copied {count} device files")`) would help debugging when device wheels are unexpectedly empty or oversized.

**Recommendation:** Add a counter and summary log line.

---

### 3. `build_tools/packaging/python/templates/rocm-sdk-device/setup.py`

The template is well-structured. A few observations:

#### 💡 SUGGESTION: `rglob("*")` may include dotfile directories

The comment mentions `.kpack` archives live "in dotfile dirs." `rglob("*")` will traverse hidden directories (like `.kpack/`), which is correct here — just calling it out since dotfile traversal is often unintentional.

---

### 4. `build_tools/packaging/python/templates/rocm/src/rocm_sdk/_dist_info.py`

The new `PackageEntry("device", ...)` is correctly placed after `libraries` and before `devel` in registration order. The `required=False` is appropriate since device wheels only exist in kpack-split mode.

No issues.

---

## Recommendations

### ✅ Recommended:

1. Add a summary log line to `populate_device_files` showing the number of files copied
2. Extract the shared library artifact name list to a constant to prevent drift between `libraries_artifact_filter` and `device_artifact_filter`

### 💡 Consider:

1. Cache the `libraries_entry` lookup in device `__init__`
2. Verify downstream consumers (build_prod_wheels.py, find-links) handle the new wheel layout correctly

### 📋 Future Follow-up:

1. Per the PR description: "additional steps needed to fully comply with the new per-target wheel design"
2. Reintroduce tests via a dedicated package (as noted in the code comment about `exclude_components=["test"]`)
3. Documentation and test coverage for kpack-split mode (see below)

---

## Suggested Follow-up PR: Docs + Tests for Kpack-Split Mode

### Documentation: `docs/packaging/python_packaging.md`

The current doc describes three package types (selector, runtime, devel) and notes that "in the future, this will be re-arranged to have more of a thin structure where the host code is always emitted as target neutral and separate device code packages are loaded as needed." That future is now here. A follow-up should:

1. **Add a "Kpack-Split Mode" section** explaining the new packaging model:
   - Arch-neutral host libraries wheel (`rocm-sdk-libraries`, no `{target_family}` suffix)
   - Per-ISA device wheels (`rocm-sdk-device-{target_family}`) containing `.kpack` archives and kernel databases
   - Device wheels overlay into the libraries package's `site-packages` directory
   - Mode is auto-detected from `KPACK_SPLIT_ARTIFACTS` flag in `therock_manifest.json`

2. **Update the "General Design" section** — the paragraph about target-specific packages says this is future work; it should note that kpack-split mode implements this

3. **Update the example output listing** — the "Building from CI Artifacts" section shows expected wheel filenames (`rocm_sdk_libraries_gfx110x_all-...`). Add kpack-split equivalents:
   ```
   # Kpack-split mode:
   # rocm_sdk_libraries-7.12.0.dev0-py3-none-linux_x86_64.whl
   # rocm_sdk_device_gfx110x_all-7.12.0.dev0-py3-none-linux_x86_64.whl
   # rocm_sdk_device_gfx120x_all-7.12.0.dev0-py3-none-linux_x86_64.whl
   ```

4. **Document the install dependency chain** — device wheel `install_requires` the exact-version libraries wheel, so `pip install rocm-sdk-device-gfx120X-all` automatically pulls in `rocm-sdk-libraries`

### SDK Tests: `build_tools/packaging/python/templates/rocm/src/rocm_sdk/tests/`

The existing tests (`libraries_test.py`, `core_test.py`, etc.) run via `rocm-sdk test` against an installed distribution. A new `device_test.py` should verify the installed device wheel. Following the pattern of `libraries_test.py`:

1. **`testInstallationLayout`** — Verify the device wheel's files land in the libraries platform directory (not a separate `_rocm_sdk_device_*` dir). Import the libraries module, confirm `.kpack` files or kernel databases exist under that module's directory tree.

2. **`testDeviceFilesPresent`** — Glob for expected device file patterns (`.kpack`, `.co`, `.dat`, `.hsaco`, `.kdb`) under the libraries platform directory. Confirm at least some are present.

3. **`testDeviceDependsOnLibraries`** — Verify that `importlib.metadata.requires("rocm-sdk-device-{target}")` includes the `rocm-sdk-libraries==<version>` dependency (i.e. the install_requires is correctly baked in).

Note: the existing `libraries_test.py` hardcodes `di.determine_target_family()` for the module lookup. In kpack-split mode the libraries module name changes (no `{target_family}` suffix) — `libraries_test.py` may need a conditional or the `_dist_info.py` resolver needs to handle both. Worth checking.

### Unit Tests: `build_tools/tests/py_packaging_test.py`

The existing test suite covers `PopulatedFiles`, multi-arch packaging, `Parameters` construction, and `restrict_families`. Following the same patterns (minimal artifact dirs, text files, no ELF binaries), a follow-up should add:

1. **`KpackSplitParametersTest`** — Test that `Parameters(kpack_split=True)` overrides the libraries `dist_package_template` to `"rocm-sdk-libraries"` (no `{target_family}`). Verify `dist_info.ALL_PACKAGES["libraries"].is_target_specific` is `False`. Verify `kpack_split=False` leaves it unchanged.

2. **`KpackSplitDevicePackageTest`** — Test `PopulatedDistPackage(params, logical_name="device", target_family="gfx120X-all")`:
   - Verify `_platform_dir` uses the libraries package's `py_package_name` (overlay semantics)
   - Verify `LIBRARIES_DIST_NAME` and `LIBRARIES_PY_PACKAGE_NAME` are written into the device package's `_dist_info.py`
   - Verify the device package template directory is `rocm-sdk-device`

3. **`PopulateDeviceFilesTest`** — Create artifact dirs with text files simulating `.kpack`/`.co` data. Call `populate_device_files()`. Verify:
   - Files are copied (not symlinked)
   - Directories are created
   - `files.mark_populated` is called for each file
   - Package is appended to `params.populated_packages`

4. **`DeviceArtifactFilterTest`** — Unit test `device_artifact_filter()`:
   - Matches `blas/lib/gfx120X-all` → True
   - Rejects `blas/lib/generic` → False (no generic in device filter)
   - Rejects `blas/dev/gfx120X-all` → False (wrong component)
   - Rejects `base/lib/gfx120X-all` → False (not a library artifact)

5. **`KpackSplitDevelExcludeComponentsTest`** — Test `populate_devel_files(exclude_components=["test"])` actually filters out test-component artifacts. Create artifacts with both `lib` and `test` components, verify only `lib` appears in the devel package.

---

## Testing Recommendations

- Verify legacy path is unchanged by running packaging on non-kpack-split artifacts and comparing output wheels
- Verify kpack-split path produces the expected wheel set: 1 core, 1 libraries (arch-neutral), N device (per-ISA), 1 meta, 1 devel
- Install a device wheel and confirm files land in the libraries package's site-packages directory (not a separate directory)
- Verify `pip install rocm-sdk-device-gfx120X-all` pulls in `rocm-sdk-libraries` as a dependency

---

## Conclusion

**Approval Status: ✅ APPROVED**

This is a well-structured first step for kpack-split packaging. The architectural separation between legacy and kpack-split paths is clean, the device wheel overlay mechanism is sound, and the legacy path is preserved. The suggestions above are improvements that can be addressed in this PR or follow-ups at the author's discretion.
