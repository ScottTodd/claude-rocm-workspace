# PR Review: [sysdeps] Link zstd with -Bsymbolic on Linux

* **PR:** [#4212](https://github.com/ROCm/TheRock/pull/4212)
* **Author:** stellaraccident (Stella Laurenzo)
* **Reviewed:** 2026-03-30
* **Status:** MERGED
* **Base:** `main` ← `users/stella/zstd_symbolic`

---

## Summary

Adds `-Bsymbolic` to the shared linker flags for the bundled zstd library on Linux. This prevents the system-installed zstd (which lacks symbol versioning) from interposing on internal symbols within ROCm's bundled zstd, which can cause crashes or corruption depending on the system zstd version.

**Net changes:** +1 line, -1 line across 1 file

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The intent is correct but the flag doesn't reach the linker.

**Strengths:**

- Addresses a real customer-reported crash with a well-understood linker mechanism
- Minimal, surgical change — single flag addition
- Good PR description explaining the root cause and verification

**Blocking Issues:**

- `-Bsymbolic` is not reaching the linker — verified by downloading `sysdeps_lib_generic` from the [CI artifacts](https://therock-ci-artifacts.s3.amazonaws.com/23674255041-linux/index.html) and running `readelf -d librocm_sysdeps_zstd.so.1.5.7 | grep -i symbolic` (no output — the `SYMBOLIC` flag is absent from the dynamic section)

---

## Detailed Review

### 1. `-Bsymbolic` flag placement

The flag is appended to `CMAKE_SHARED_LINKER_FLAGS` as a bare `-Bsymbolic` (not `-Wl,-Bsymbolic`):

```cmake
"-DCMAKE_SHARED_LINKER_FLAGS=-Wl,--version-script=${CMAKE_CURRENT_SOURCE_DIR}/version.lds -Bsymbolic"
```

### ❌ BLOCKING: Missing `-Wl,` wrapper for `-Bsymbolic`

`CMAKE_SHARED_LINKER_FLAGS` is passed to the compiler driver (gcc/clang), not directly to `ld`. The existing `--version-script` flag correctly uses `-Wl,` to forward it to the linker. However, bare `-Bsymbolic` is interpreted by GCC/Clang as `-B symbolic` (set compiler file search prefix to "symbolic"), not as the linker's `-Bsymbolic` flag. The nonexistent directory is silently ignored, so no build error is produced, but the flag never reaches `ld`.

**Verified:** Downloaded `sysdeps_lib_generic` from the [CI run artifacts](https://therock-ci-artifacts.s3.amazonaws.com/23674255041-linux/index.html) (run 23674255041) and inspected the built library:

```
$ readelf -d librocm_sysdeps_zstd.so.1.5.7 | grep -i symbolic
(no output)
```

If `-Bsymbolic` had reached the linker, a `SYMBOLIC` entry would appear in the dynamic section. Its absence confirms the flag is being consumed by the compiler driver, not forwarded to `ld`. (For comparison, `VERDEF` entries are present, confirming the `version.lds` script — which does use `-Wl,` — took effect.)

**Required action:** Change `-Bsymbolic` to `-Wl,-Bsymbolic`:

```cmake
"-DCMAKE_SHARED_LINKER_FLAGS=-Wl,--version-script=${CMAKE_CURRENT_SOURCE_DIR}/version.lds -Wl,-Bsymbolic"
```

### 2. Scope and completeness

### 📋 FUTURE WORK: Audit other bundled libraries for the same issue

The PR description explicitly notes: "we should add more testing and do an audit of all of the libraries and adjust as needed." This is tracked in [#4211](https://github.com/ROCm/TheRock/issues/4211). Other libraries under `third-party/sysdeps/` that build shared libraries with `version.lds` may benefit from the same treatment.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Change `-Bsymbolic` to `-Wl,-Bsymbolic` so the flag actually reaches the linker. Confirmed ineffective via `readelf -d` on the CI-built artifact.

### 📋 Future Follow-up:

1. Audit all other `sysdeps` shared libraries for the same symbol interposition risk (tracked in #4211).
2. Consider adding a CI smoke test that loads both system and bundled zstd to detect interposition regressions.

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The intent is correct — `-Bsymbolic` is the right fix for internal symbol interposition. However, the flag as written (`-Bsymbolic`) does not reach the linker; it needs to be `-Wl,-Bsymbolic`. This was confirmed by inspecting the CI-built `librocm_sysdeps_zstd.so.1.5.7` — no `SYMBOLIC` entry in the dynamic section. A follow-up PR with the one-character fix (`-Wl,-Bsymbolic`) is needed.
