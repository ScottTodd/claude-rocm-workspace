# PR Review: [Triton][Windows] CI builds

* **PR:** [#4205](https://github.com/ROCm/TheRock/pull/4205)
* **Author:** m-gallus (Michał Gallus)
* **Branch:** `michal/triton-windows-2` → `main`
* **Reviewed:** 2026-03-30
* **Status:** OPEN

---

## Summary

Enables Triton Windows wheels in the PyTorch CI/release pipeline. The PR makes three coordinated changes: (1) wires triton checkout and build flags into the Windows pytorch wheel workflow, (2) updates `build_prod_wheels.py` to pass version suffix and ccache config to the Windows triton builder (and switches from `triton` to the native `triton_windows` package name), and (3) updates `write_torch_versions.py` to expect `triton_windows` on Windows.

**Net changes:** +33 lines, -13 lines across 3 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The build script and version detection changes are clean and consistent. However, the triton-windows checkout uses a single static commit pin (`ci_commit_pins/triton-windows.txt`) regardless of which pytorch release branch is being built. Unlike Linux — where the triton commit is derived from the torch checkout itself (nightly: `get_triton_pin(torch_dir)`, stable: release branch from `get_triton_version(torch_dir)`) — Windows always checks out the same triton-windows commit. A single triton-windows commit can't be expected to work across `release/2.9`, `release/2.10`, nightly, etc.

**Strengths:**
- All touchpoints updated consistently — no dangling references to the old `TRITON_WHEEL_NAME: "triton"` override
- Version suffix handling mirrors the Linux `build_triton_linux()` pattern closely
- Selective copying of `CMAKE_*_COMPILER_LAUNCHER` from the shared env is cleaner than copying the entire env dict (which would pull in Linux-specific vars)
- The `write_torch_versions.py` change correctly tightens validation — triton is no longer optional on Windows

**Blocking Issues:**
- Stable builds will use the same triton-windows commit for every pytorch version — needs per-version pin resolution

---

## Detailed Review

### 1. `build_prod_wheels.py` — Version suffix and env plumbing

**Overall:** Correct. The new `env` parameter and version suffix logic closely follow `build_triton_linux()`.

#### 💡 SUGGESTION: `str(args.version_suffix)` is a no-op

```python
version_suffix += str(args.version_suffix)
```

By the time `build_triton_windows` is called, `do_build()` has already ensured `args.version_suffix` is a non-None string (lines 598–599 auto-compute it from the installed ROCm package). The `str()` wrapping is harmless but misleading — it suggests the value might not be a string. Linux has the same pattern, so this isn't worth changing in isolation.

#### 💡 SUGGESTION: Consider uninstalling `triton` before building `triton_windows`

`build_triton_linux()` uninstalls any existing triton package before building (line 806–810). `build_triton_windows()` does not. If a stale `triton` package is installed in the build environment, it could potentially interfere at import time (e.g., pytorch trying to import `triton` and finding the wrong one). In CI this is likely a non-issue since the environment is fresh, but worth considering for local developer builds.

### 2. `write_torch_versions.py` — Platform-aware wheel name

**Overall:** Correct. The triton skip logic for Windows is properly removed since triton is now built.

No issues found. The `os` parameter (shadowing the module) is pre-existing and scoped correctly within this function.

### 3. `build_windows_pytorch_wheels.yml` — Workflow wiring

**Overall:** Correct. Triton checkout, build flags, version output, and S3 promotion are all wired consistently.

#### ❌ BLOCKING: Triton-windows uses a single static commit pin for all torch versions

[`pytorch_triton_repo.py`](https://github.com/ROCm/TheRock/blob/main/external-builds/pytorch/pytorch_triton_repo.py) on Windows always checks out the commit in `ci_commit_pins/triton-windows.txt` (lines 64–71), regardless of which pytorch release branch is being built. This means the same triton-windows commit is used for `release/2.9`, `release/2.10`, nightly, etc.

Compare with Linux, where the triton commit is derived from the torch checkout:
- **Nightly:** `get_triton_pin(torch_dir)` reads `torch/.ci/docker/ci_commit_pins/triton.txt`
- **Stable:** `get_triton_version(torch_dir)` reads `torch/.ci/docker/triton_version.txt` and derives a release branch

A single triton-windows commit can't be expected to work across pytorch versions. The workflow also doesn't pass `--release` for stable builds, so even if version-aware logic were added, it wouldn't be invoked.

**Required action:** Either:
1. Add per-version pin resolution to `pytorch_triton_repo.py` for Windows (analogous to the Linux `--release` path), or
2. Scope the PR to nightly-only and skip the triton checkout in the stable block until per-version pins are supported.

#### 📋 FUTURE WORK: Indentation inconsistency in stable checkout block

The nightly triton checkout uses 10-space indentation:
```yaml
          python ./external-builds/pytorch/pytorch_triton_repo.py checkout \
            --checkout-dir ${{ env.CHECKOUT_ROOT }}/triton \
            --torch-dir ${{ env.CHECKOUT_ROOT }}/torch
```

While the stable triton checkout uses 14-space indentation (matching the surrounding audio/vision lines):
```yaml
          python ./external-builds/pytorch/pytorch_triton_repo.py checkout \
              --checkout-dir ${{ env.CHECKOUT_ROOT }}/triton \
              --torch-dir ${{ env.CHECKOUT_ROOT }}/torch
```

Both work but the difference between nightly (2-space continuation indent) and stable (4-space continuation indent) is cosmetic. Not worth a fixup commit.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Triton-windows commit pin must be version-aware for stable builds, or triton must be excluded from the stable checkout path until per-version pins are supported

### ✅ Recommended:

1. Verify in a CI run that `triton_windows-*.whl` is produced and the `write_torch_versions` step picks it up correctly (the PR states "awaiting" test results)

### 💡 Consider:

1. Adding triton uninstall before build for parity with Linux (low priority, mainly for local dev)

---

## Testing Recommendations

- Run the Windows pytorch wheel build workflow with `build_triton: true` and verify:
  - `triton_windows-*.whl` appears in `PACKAGE_DIST_DIR`
  - `write_torch_versions.py` outputs `triton_version` correctly
  - S3 promotion includes the triton_windows wheel
  - The wheel installs and can be imported alongside pytorch

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The build script and version detection changes are solid — the `triton` → `triton_windows` transition is consistent across all touchpoints. The blocking issue is that `pytorch_triton_repo.py` uses a single static commit pin for all pytorch versions on Windows, so stable builds will check out a triton-windows commit that may be incompatible with the target pytorch release branch. This needs per-version pin resolution (like the Linux path) or the stable checkout should skip triton until that's implemented.
