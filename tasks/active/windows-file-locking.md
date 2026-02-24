---
repositories:
  - therock
  - rocm-libraries
---

# Windows File Locking (WinError 32) in CI

- **Status:** Investigation
- **Priority:** P2 (Medium)
- **Started:** 2026-02-24
- **Issue:** https://github.com/ROCm/TheRock/issues/2784

## Overview

Windows CI machines fail with `PermissionError: [WinError 32] The process
cannot access the file because it is being used by another process` during
artifact setup and test execution. The error prevents test binaries (hipdnn,
miopen primarily) from being overwritten when a new job starts.

Before proposing a fix (e.g. retry logic in artifact extraction), we need to
understand how widespread and generic this is — whether it's a narrow problem
with specific subprojects or a systemic issue across the Windows CI fleet.

## Goals

- [ ] Determine which subprojects and test binaries are affected
- [ ] Understand what is different about the failing tests vs passing ones
- [ ] Determine whether the root cause is leftover processes, Windows OS
      locking (Defender, indexer), extraction races, or a combination
- [ ] Decide on a fix strategy (code change vs infra change vs both)

## Context

### Background

Issue #2784 has 23 comments spanning several months. Key observations:

1. **Core error:** `WinError 32` on `.exe` files during artifact setup —
   the next CI job can't overwrite/unlink test executables from the prior job.

2. **Cleanup script mismatch (comment #3):** `cleanup_processes.ps1` uses
   `GITHUB_WORKSPACE` path regex, which doesn't match cross-repo test binary
   paths (rocm-libraries invokes TheRock tests).

3. **Fresh pod reproduction (comment #23):** amd-justchen hit WinError 32 on
   a brand-new Azure K8s pod during artifact *download* (no prior tests). The
   traceback is in `artifacts.py:239` (`os.unlink`). This suggests a second
   root cause beyond leftover processes.

4. **Timeout correlation (comment #18):** MIOpen tests hit the 60-minute
   timeout, which kills the runner but may leave child/GPU processes alive.

5. **BSOD interference (comment #15):** Strix Halo machines also BSOD during
   tests (issue #2986), making interactive debugging difficult.

### Related Work

- **dlls-copied-fix task:** Fixed a different Windows CI problem — duplicate
  `POST_BUILD` DLL copy commands racing during parallel builds. PRs:
  [rocm-libraries#4784](https://github.com/ROCm/rocm-libraries/pull/4784)
  (minimal, merged),
  [rocm-libraries#4783](https://github.com/ROCm/rocm-libraries/pull/4783)
  (full rework, open). That fix was to *subproject CMakeLists.txt*. The
  question is whether this issue also has a subproject-level fix.

- **PR #2819:** Open PR to broaden `cleanup_processes.ps1` path matching.

- **Issue #2986:** Windows Strix Halo BSOD — complicating factor.

### Directories/Files Involved

```
TheRock/build_tools/_therock_utils/artifacts.py       # os.unlink at line 239
TheRock/build_tools/_therock_utils/pattern_match.py   # os.unlink at lines 254, 287
TheRock/build_tools/fetch_artifacts.py                # concurrent download+extract
```

## Hypotheses

### H1: Bare `os.unlink()` in artifact extraction has no Windows retry

`artifacts.py:239` does a bare `os.unlink(dest_path)` with no retry.
`pattern_match.py:254,287` has the same. On Windows, files can be transiently
locked by Defender, Search Indexer, or the PE loader. The fresh-pod
reproduction (comment #23) supports this — no leftover processes, just
extraction racing against Windows file scanning.

By contrast, `pattern_match.py` already has `_rmtree_with_retry()` for
`shutil.rmtree`, so there's precedent for retry in this codebase.

**Strength:** Explains fresh-pod reproduction. Targeted code fix.
**Weakness:** Might only explain a subset of failures. Adding retries to
packaging code is a band-aid if the real problem is elsewhere.

### H2: Concurrent extraction races on shared files

`fetch_artifacts.py` uses two thread pools for download and extraction. If two
archives write overlapping paths (especially in "flatten" mode where everything
goes to one `dist/` dir), their extractions race: one writes an `.exe`, the
other tries to `os.unlink` it while still open.

**Strength:** Explains non-deterministic failures.
**Weakness:** Need to verify whether affected artifacts actually overlap.

### H3: Leftover test processes from timeout kills

MIOpen tests hit the 60-minute timeout. The killed process may leave GPU worker
threads or child processes holding locks on `.exe` files. The cleanup script's
path regex doesn't cover cross-repo paths.

**Strength:** Matches the most common failure pattern (hipdnn, miopen).
**Weakness:** Doesn't explain the fresh-pod case (comment #23).

### H4: Something specific to hipdnn/miopen tests

The issue is disproportionately hipdnn and miopen. These tests might:
- Spawn persistent child processes or GPU contexts
- Memory-map their own executable
- Take long enough to be killed by timeouts more often

**Strength:** Would explain the narrow blast radius.
**Weakness:** Needs investigation of those tests' runtime behavior.

## Investigation Plan

### Phase 1: Scope the problem

- [ ] Catalog all CI failures in the issue — which executables, which machines,
      which workflow paths (TheRock direct vs rocm-libraries cross-repo)
- [ ] Search for similar WinError 32 failures in other TheRock issues and
      recent CI runs that may not have issues filed
- [ ] Check whether non-hipdnn/miopen projects also fail this way

### Phase 2: Understand what's different about failing tests

- [ ] Look at hipdnn and miopen test CMakeLists.txt and test runner code —
      do they spawn subprocesses, use GPU contexts that outlive the test?
- [ ] Check whether the affected tests have POST_BUILD DLL copy patterns
      (they don't seem to based on initial search, but verify)
- [ ] Compare test execution patterns: do passing tests run shorter? Use
      different process models?

### Phase 3: Characterize the extraction path

- [ ] Trace the exact code path for the fresh-pod failure (comment #23) —
      is it the flatten path or extract path?
- [ ] Check whether multiple archives in a typical CI run contain overlapping
      file paths
- [ ] Determine if `_rmtree_with_retry` already covers the exploded-dir
      path and only the archive path is unprotected

### Phase 4: Decide on fix strategy

Based on findings, options include:
1. **Subproject code change** (like dlls-copied-fix): if the tests themselves
   are doing something that causes locking
2. **Build tools code change**: retry logic in `artifacts.py` / `pattern_match.py`
3. **CI infra change**: broaden cleanup script (PR #2819), increase timeouts
4. **Combination**: likely needed given multiple root causes

## Investigation Notes

### 2026-02-24 — Initial research

Reviewed issue #2784 (23 comments), the dlls-copied-fix PRs (#4783, #4784),
and the relevant source code. Key code paths identified:

- `artifacts.py:236-239`: bare `os.unlink` in archive extraction (flatten path)
- `pattern_match.py:254,287`: bare `os.unlink` in exploded-dir copy
- `pattern_match.py:221-237`: existing `_rmtree_with_retry` with backoff

Initial grep of rocm-libraries found that hipdnn and miopen do NOT use the
`DLLS_COPIED` / `POST_BUILD` DLL copy pattern that was fixed before. The
POST_BUILD pattern remains in hipblas, rocblas, hipsparse, rocsparse, rocfft,
hipfft, hipsolver — but those copy library DLLs (1 copy per lib target), not
the N-copies-per-test-target bug.

## Next Steps

1. [ ] Phase 1: scope — catalog failures, search for unreported instances
2. [ ] Phase 2: compare failing vs passing tests
3. [ ] Phase 3: trace the extraction code path for the fresh-pod case
