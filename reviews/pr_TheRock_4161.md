# PR Review: #4161 — Enhance ccache setup - Bazelremote Caching

* **PR:** https://github.com/ROCm/TheRock/pull/4161
* **Author:** subodh-dubey-amd
* **Base:** `main`
* **Branch:** `users/subodh-dubey-amd/bazelremote-ccache`
* **Reviewed:** 2026-03-25
* **Status:** Draft

---

## Summary

Replaces GitHub Actions `actions/cache` with bazel-remote secondary storage for
ccache across all three Windows build workflows: `build_windows_artifacts.yml`
(CI), `multi_arch_build_windows_artifacts.yml` (multi-arch CI), and
`release_windows_packages.yml` (releases). Makes `setup_ccache.py` cross-platform
by guarding POSIX-only compiler fingerprinting (`ldd`/`sha256sum`) on Windows.

**Net changes:** +53 lines, -54 lines across 4 files

---

## Overall Assessment

**✅ APPROVED** — Well-scoped change, CI evidence supports the claims.

**Strengths:**
- Unifies cache infrastructure: all platforms now use `setup_ccache.py` + bazel-remote
- Removes unreliable GitHub Actions cache (was 0.4% hit rate on cold nightly)
- Multi-arch Windows CI gets ccache for the first time (previously zero caching)
- Clean, minimal cross-platform changes to `setup_ccache.py`
- CI evidence: 50% remote cache hit rate vs. 0.4% baseline

**Issues:**
- One cosmetic issue (output format mismatch with shell)
- One question about uncacheable call proportion

---

## CI Evidence

### Comparison: PR vs Baseline (gfx1151, `release_windows_packages.yml`)

| Metric | Baseline (nightly, main) | PR Cold | PR Warm |
|--------|--------------------------|---------|---------|
| **Build therock-dist** | **3h37m** | **2h45m** (-24%) | **2h12m** (-39%) |
| Cacheable calls | 17,635 / 27,233 (64.8%) | 17,734 / 27,259 (65.1%) | 17,734 / 27,259 (65.1%) |
| Hits (overall) | 72 (0.4%) | 8,997 (50.7%) | 9,002 (50.8%) |
| Local cache hits | 72 (0.4%) | 74 (0.4%) | 73 (0.4%) |
| Remote cache hits | N/A (no remote) | 8,923 / 17,660 (50.5%) | 8,929 / 17,661 (50.6%) |
| Uncacheable (unsupported option) | 9,378 (98.5% of uncacheable) | 9,378 (98.5%) | 9,378 (98.5%) |
| Cache size | 1.9 / 4.0 GB (47%) | 1.9 / 5.0 GB (38%) | 1.9 / 5.0 GB (38%) |
| Local cache evictions | N/A | 0 | 0 |

**Observations:**
- Remote cache provides a consistent ~50% hit rate on both cold and warm runs,
  confirming the server is pre-populated and stable
- Local cache hits are negligible on both old and new (~0.4%) — ephemeral runners
  start fresh every time, so local hits come only from within-build recompilation
- Build time reduction: 24% (cold) to 39% (warm) — significant for gfx1151
- The 50% ceiling appears to be fundamental: 9,378/9,521 (98.5%) of uncacheable
  calls are "unsupported compiler option", likely MSVC-specific flags ccache can't
  handle. This puts a floor on miss rate. Compare to Linux which gets 98% overall
  (GCC/Clang are more ccache-friendly)

---

## Detailed Review

### 1. `build_tools/setup_ccache.py`

#### 💡 SUGGESTION: `set` vs `export` output in bash shells

Lines 163-166: The Windows branch outputs `set CCACHE_CONFIGPATH=...` (cmd.exe
syntax) but all the GitHub Actions workflows use bash shells. The output isn't
consumed by anything (CCACHE_CONFIGPATH is set as a job-level env var), so this
is purely cosmetic — but it would print cmd.exe syntax into a bash log, which
could confuse someone debugging.

Consider either: always using `export` (bash is the shell), or suppressing the
output on Windows since it isn't consumed.

#### Platform guards are correct

- `IS_WINDOWS = platform.system() == "Windows"` — correct detection
- `POSIX_COMPILER_CHECK_SCRIPT` guarded at module level — prevents reading the
  file on Windows (file exists in repo but content is irrelevant on Windows)
- Compiler check skipped on Windows — ccache default `mtime` check works with MSVC
- `compiler_check_file.write_text()` guarded in both `init` and `update` paths
- All guards use the same `IS_WINDOWS` constant — consistent

### 2. `.github/workflows/multi_arch_build_windows_artifacts.yml`

Clean addition. The new steps follow the pattern from `build_portable_linux_artifacts.yml`:
- Install ccache via choco
- Run `setup_ccache.py` with preset
- Add `-DCMAKE_C_COMPILER_LAUNCHER=ccache` and `-DCMAKE_CXX_COMPILER_LAUNCHER=ccache`
- Report `ccache -s -v` in the existing Report step

No issues found.

### 3. `.github/workflows/build_windows_artifacts.yml`

Clean replacement of the old `actions/cache/restore` + `actions/cache/save` pattern
with `setup_ccache.py`. The `ccache --zero-stats` and `ccache -z` calls are removed
because `setup_ccache.py --reset-stats` (default True) handles stats reset. The
report upgraded from `ccache -s` to `ccache -s -v` for more detail.

No issues found.

### 4. `.github/workflows/release_windows_packages.yml`

Same pattern as build_windows_artifacts. The preset selection logic is worth noting:

```yaml
CI_TYPE: ${{ env.RELEASE_TYPE == 'dev' && 'presubmit' || 'postsubmit' }}
```

This maps dev releases to `CACHE_SRV_DEV` and nightly/stable to `CACHE_SRV_REL`.
This is consistent with the cache server separation — dev builds share presubmit
cache, releases use a separate cache server.

No issues found.

---

## Recommendations

### ✅ Recommended:
1. No required changes — this is ready for merge

### 💡 Consider:
1. Fix the `set` vs `export` output on Windows (cosmetic, low priority)
2. Add a brief comment in setup_ccache.py explaining why mtime check is sufficient for MSVC (helps future maintainers understand the platform split)

### 📋 Future Follow-up:
1. The 50% remote hit rate ceiling is driven by MSVC's unsupported compiler options (98.5% of uncacheable calls). Investigate which MSVC flags ccache rejects — if some can be added to `sloppiness` or mapped, hit rates could improve further. This is a ccache upstream issue, not something to solve in this PR.
2. Multi-arch Windows multi-stage builds will benefit more as the cache warms — the compiler-runtime stage (LLVM, shared across all families) should see very high hit rates after a few runs.

---

## Impact on Multi-Arch Migration (#3337)

This PR directly addresses Gap 1 from our multi-arch-migration task — it adds
ccache with remote storage to multi-arch Windows CI, which previously had zero
caching. With 50% remote hit rates, build times should drop enough to mitigate
the runner timeout issues (#3622), especially for the compiler-runtime stage.

This is even better than our recommended "compiler-runtime ccache only" approach
since it covers all stages uniformly.

---

## Conclusion

**Approval Status: ✅ APPROVED**

Solid PR that closes the Windows ccache gap between CI and multi-arch CI using
the same bazel-remote infrastructure already proven on Linux. CI evidence confirms
~50% remote hit rate and 24-39% build time reduction on gfx1151. No blocking issues.
