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

**✅ APPROVED** — Clean, well-scoped change. The package name switch from `triton` to `triton_windows` is consistently applied across all three files (build script, version detection, workflow). The version suffix and ccache support mirror the existing Linux patterns appropriately.

**Strengths:**
- All touchpoints updated consistently — no dangling references to the old `TRITON_WHEEL_NAME: "triton"` override
- Version suffix handling mirrors the Linux `build_triton_linux()` pattern closely
- Selective copying of `CMAKE_*_COMPILER_LAUNCHER` from the shared env is cleaner than copying the entire env dict (which would pull in Linux-specific vars)
- The `write_torch_versions.py` change correctly tightens validation — triton is no longer optional on Windows

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

#### 💡 SUGGESTION: Stable triton checkout lacks `--require-related-commit`

The stable checkout block for audio and vision both pass `--require-related-commit`:
```yaml
python ./external-builds/pytorch/pytorch_audio_repo.py checkout \
    --checkout-dir ${{ env.CHECKOUT_ROOT }}/audio \
    --torch-dir ${{ env.CHECKOUT_ROOT }}/torch \
    --require-related-commit
```

The triton stable checkout does not:
```yaml
python ./external-builds/pytorch/pytorch_triton_repo.py checkout \
    --checkout-dir ${{ env.CHECKOUT_ROOT }}/triton \
    --torch-dir ${{ env.CHECKOUT_ROOT }}/torch
```

This appears to be because [`pytorch_triton_repo.py` doesn't implement `--require-related-commit`](https://github.com/ROCm/TheRock/blob/main/external-builds/pytorch/pytorch_triton_repo.py). For stable releases, this means triton could be built from a commit that doesn't correspond to the pytorch release branch. Consider adding this support to `pytorch_triton_repo.py` as a follow-up if triton-windows has release branches.

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

### ✅ Recommended:

1. Verify in a CI run that `triton_windows-*.whl` is produced and the `write_torch_versions` step picks it up correctly (the PR states "awaiting" test results)

### 💡 Consider:

1. Adding triton uninstall before build for parity with Linux (low priority, mainly for local dev)
2. Future `--require-related-commit` support in `pytorch_triton_repo.py` for stable release builds

### 📋 Future Follow-up:

1. Add `--require-related-commit` to `pytorch_triton_repo.py` once triton-windows has release branches that align with pytorch stable

---

## Testing Recommendations

- Run the Windows pytorch wheel build workflow with `build_triton: true` and verify:
  - `triton_windows-*.whl` appears in `PACKAGE_DIST_DIR`
  - `write_torch_versions.py` outputs `triton_version` correctly
  - S3 promotion includes the triton_windows wheel
  - The wheel installs and can be imported alongside pytorch

---

## Conclusion

**Approval Status: ✅ APPROVED**

Well-scoped change that consistently wires triton Windows builds through the CI pipeline. The package name transition from `triton` to `triton_windows` is complete across all touchpoints. No blocking issues. Recommend waiting for CI validation before merging since the triton build + version detection flow hasn't been exercised on Windows yet.
