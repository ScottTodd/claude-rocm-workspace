# Audit: HIP_VERSION automation design

**Date:** 2026-03-24
**Context:** While debugging a Windows CI failure caused by a HIP version bump ([rocm-systems#4010](https://github.com/ROCm/rocm-systems/pull/4010)), we discovered that the HIP_VERSION automation has significant design issues. This report documents the system, its problems, and open questions.

**Related reports:**
- [HIP_VERSION threshold audit](audit_hip_version_thresholds.md)
- [Build-time HIP runtime usage audit](audit_buildtime_hip_runtime.md)
- [Debugging notes](https://gist.github.com/ScottTodd/8505d2b3704c4458e15db9339317cc24)

## How the system works

The HIP version is derived from a chain spanning two repositories:

### 1. Default state

[`rocm-systems/projects/hip/VERSION`](https://github.com/ROCm/rocm-systems/blob/main/projects/hip/VERSION) is checked into git with:
```
#HIP_VERSION_MAJOR
7
#HIP_VERSION_MINOR
2
#HIP_VERSION_PATCH
0
```

This file is the fallback. It has not been kept in sync with actual releases.

### 2. Tagging automation (TheRock side)

[TheRock PR #3401](https://github.com/ROCm/TheRock/pull/3401) (merged 2026-02-17) added [`.github/workflows/hip_tagging_automation.yml`](https://github.com/ROCm/TheRock/blob/main/.github/workflows/hip_tagging_automation.yml) and [`build_tools/github_actions/hip_tagging_helper.py`](https://github.com/ROCm/TheRock/blob/main/build_tools/github_actions/hip_tagging_helper.py).

When a push to `main` changes the `rocm-systems` submodule pointer:
1. The workflow reads [`version.json`](https://github.com/ROCm/TheRock/blob/main/version.json) from the TheRock repo root (e.g. `{"rocm-version": "7.12.0"}`)
2. `calculate_patch_tag()` generates a patch number from the current date: `{last_digit_of_year}{day_of_year:03}0`
3. A tag like `hip-version_7.12.60610` is pushed to the rocm-systems commit via the GitHub API

This runs **after merge** — the tag does not exist when CI starts on the merge commit itself.

### 3. Version consumption (rocm-systems side)

[rocm-systems PR #1135](https://github.com/ROCm/rocm-systems/pull/1135) (merged 2025-11-06) modified [`projects/clr/hipamd/CMakeLists.txt`](https://github.com/ROCm/rocm-systems/blob/main/projects/clr/hipamd/CMakeLists.txt).

During CMake configure of hip-clr:
1. Read [`projects/hip/VERSION`](https://github.com/ROCm/rocm-systems/blob/main/projects/hip/VERSION) → get `HIP_VERSION_MAJOR`, `HIP_VERSION_MINOR`, `HIP_VERSION_PATCH`
2. If `HIP_VERSION_PATCH == 0` AND `GIT_FOUND` AND `UNIX`:
   - Run `git fetch --tags origin` (with `ERROR_QUIET`)
   - Run `git describe --tags --match "hip-version_*" --abbrev=0 HEAD`
   - If a tag is found, parse the version and **overwrite the VERSION file in the source tree**
3. Otherwise, use the VERSION file as-is

### 4. Release branch overrides

The tagging automation only runs on `main`. For release branches (e.g. `release/therock-7.12`), the VERSION file must be manually edited. This is what [rocm-systems#4010](https://github.com/ROCm/rocm-systems/pull/4010) did, directly triggering the Windows CI failure.

## Problems

### P1: Windows never gets the real version

The git-tag lookup is gated on `UNIX`:
```cmake
if(HIP_VERSION_PATCH EQUAL 0 AND GIT_FOUND AND UNIX)
```

Windows always builds with the VERSION file contents (currently `7.2.0`). This means Windows and Linux have been building with **different HIP_VERSION values** — different `#if` guards active, different code paths compiled. The CMake file itself has a comment acknowledging this: `# FIXME: Two different version strings used. Below we use UNIX commands, not compatible with Windows.`

### P2: No pre-merge testing of the new version

The tag is pushed after merge by a separate workflow. CI on the merge commit itself cannot see the tag (it doesn't exist yet). The first build that picks up the new version is some later commit — but that build isn't testing the version change, it's testing whatever other changes happened to land.

This means **no CI run ever tests the version transition itself**. The activation of new `#if HIP_VERSION` code paths is never validated.

### P3: Version depends on network access at configure time

`git fetch --tags origin` requires network access to the git remote. Builds without this — air-gapped machines, tarball/zip archives of the source, shallow clones without tags, or any environment where the fetch fails — silently fall back to the VERSION file (`7.2.0`).

Since the fetch failure is swallowed by `ERROR_QUIET`, there is **no indication** that the version is wrong. The build proceeds with a stale version, different code paths compiled, and the resulting binaries report a different version than the same source built with network access.

### P4: CMake configure mutates the source tree

```cmake
file(WRITE ${HIP_COMMON_DIR}/VERSION ...)
```

This overwrites the checked-in VERSION file during configure. This is a side effect that:
- Contaminates subsequent builds (the file is now different from what's in git)
- Shows up in `git status` / `git diff`
- Breaks reproducibility (the source tree is different after configure than before)
- Could cause issues with build systems that detect source changes

### P5: The VERSION file is stale and misleading

The checked-in VERSION file says `7.2.0` but the actual version used on Linux is tag-derived (e.g. `7.12.60610`). Anyone reading the file directly — or building on Windows, or building without git, or building without network access — gets a value that doesn't reflect what Linux CI builds.

### P6: The patch number is a date encoding, not a version

`calculate_patch_tag` generates patch numbers like `60610` from `{last_digit_of_year=6}{day_of_year=061}{0}`. This is an opaque date encoding, not a meaningful version progression. Two submodule bumps on the same day would attempt the same patch number (mitigated by the `tag_exists_for_commit` check, which just skips tagging).

### P7: Release branches bypass the automation entirely

The tagging workflow only triggers on `push` to `main`. Release branches require manual VERSION file edits (as in #4010). This creates a different version derivation path for releases vs. development, with no shared testing.

### P8: No end-to-end ownership

PR #1135 (consumption side) was merged by one developer in Nov 2025. PR #3401 (production side) was merged by a different developer in Feb 2026, four months later. Neither PR references a design document. Neither has cross-team review connecting the two halves. The system spans two repositories with no single owner.

## Release stream context

ROCm ran two parallel release streams:
- **Stream 1:** 7.0, 7.1, 7.2 (and possibly 7.3)
- **Stream 2:** 7.9, 7.10, 7.11, 7.12

The VERSION file's `7.2.0` value corresponds to stream 1. The git tags encode stream 2 versions (7.12.xxxxx). The version bump in #4010 was the first time a release branch jumped across the gap from stream 1 (7.2) to stream 2 (7.12), activating `#if HIP_VERSION` guards that targeted the 7.3-7.12 range.

The [tag list on rocm-systems](https://github.com/ROCm/rocm-systems/tags) shows this gap clearly:
```
hip-version_7.2.52960
hip-version_7.2.53090
hip-version_7.2.53150
hip-version_7.2.53210
hip-version_7.3.53290   <-- stream jump
hip-version_7.3.53390
hip-version_7.12.60370  <-- stream jump
hip-version_7.12.60430
...
hip-version_7.13.60800
```

## Open questions

### On the technical motivation

1. **Why is HIP_VERSION coupled to the ROCm product version?** HIP_VERSION gates code paths in libraries (e.g. the `HasSchedMode` guard). Is this intentional — are library teams expected to use HIP_VERSION to feature-gate against specific SDK releases? Or is it supposed to be a metadata/ABI version that just happens to track the product version?

2. **Who consumes HIP_VERSION at runtime?** The `hipRuntimeGetVersion()` API returns this value. Do downstream users (PyTorch, TensorFlow, etc.) check it to decide behavior? If so, the Windows-always-returns-7.2.0 problem is much bigger than a build issue.

3. **Is there documentation for library developers on what HIP_VERSION means?** The 92 existing `#if HIP_VERSION` guards imply developers treat it as a feature-availability signal. Is there guidance on when to use it vs. other mechanisms?

### On the automation design

4. **Why was the git-tag approach chosen over simpler alternatives?** The two-repo boundary between TheRock and rocm-systems prevents an atomic update, but there are simpler bridges:
   - **CMake variable injection:** TheRock passes `-DHIP_VERSION_OVERRIDE=7.12.60610` from `version.json` at configure time. No git tags, no network, no source mutation, cross-platform.
   - **Two-step PR flow:** Update VERSION in rocm-systems first (with CI), then bump the submodule in TheRock. Not atomic, but the version change gets tested.

5. **Was the UNIX-only gate intentional or an oversight?** The `FIXME` comment suggests it was known to be incomplete.

6. **Does anyone own this system end-to-end?** Who is responsible when it breaks?

### On the path forward

7. **Should HIP_VERSION stop gating code paths entirely?** If the version is meant to be product metadata, it shouldn't control `#if` branches. Library teams could use separate feature-detection mechanisms.

8. **Should there be a CI check that audits `#if HIP_VERSION` guards when the version changes?** Even if we fix the automation, the 92 existing guards are a permanent risk surface for future bumps.

9. **What is the minimum viable fix?** If the full redesign takes time, is there a short-term fix to ensure Windows and Linux build with the same version and version changes get CI coverage?
