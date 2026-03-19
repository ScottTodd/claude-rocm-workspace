# PR Review: Add Windows packaging requirements RFC document

* **PR:** [#3973](https://github.com/ROCm/TheRock/pull/3973)
* **Author:** LiamfBerry
* **Base:** `main` ← `windows-packaging-rfc`
* **Reviewed:** 2026-03-19
* **Type:** Comprehensive

---

## Summary

Adds RFC0011 defining Windows packaging requirements for ROCm via TheRock. Covers MSI, Winget, pip, and ZIP packaging formats, directory layout, versioning, side-by-side installation, registry discovery, environment variables, driver decoupling, logging, signing, redistribution, and a VS Code plugin. This is a companion to the existing RFC0009 (Linux packaging requirements).

**Net changes:** +464 lines, -0 lines across 1 file

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** - The RFC is well-structured and covers the necessary packaging concerns comprehensively. However, there are numerous typos/spelling errors throughout the document, some internal inconsistencies in the package tables, and a few areas where requirements are ambiguous or potentially contradictory. These should be cleaned up before the RFC is published for wider feedback.

**Strengths:**
- Clear scope delineation (in-scope vs out-of-scope)
- Good alignment with the existing RFC0009 Linux packaging structure
- Concrete examples for MSI commands and directory layouts
- Thoughtful handling of symlink limitations on Windows
- Clear side-by-side versioning policy

**Issues:**

- Many spelling/typographical errors throughout
- Package table inconsistencies between sections
- Some ambiguous requirements around caches and per-user installs

---

## Detailed Review

### ❌ BLOCKING: Numerous spelling and typographical errors

The document has many typos that undermine its credibility as a published requirements document:

- Line 10: "distrobuition" → "distribution"
- Line 14: "sotware" → "software"
- Line 60: "ir power-user" → "or power-user"
- Line 94: "provleges" → "privileges"
- Line 132: "Cmake" → "CMake"
- Line 168: "libraires" → "libraries"
- Line 208: "seperable" → "separable"
- Line 210: "avaialable" → "available"
- Line 263: "footproint" → "footprint"
- Line 263: "redistribuition" → "redistribution"
- Line 300: "package-owend" → "package-owned"
- Line 309: "enrionment" → "environment"
- Line 337: "dsicovery" → "discovery"
- Line 349: "compatiblity" → "compatibility"
- Line 351: "seperate" → "separate"
- Line 376: "assiociated" → "associated"
- Line 441: "Exisiting-version" → "Existing-version"
- Line 446: "deffered" → "deferred"
- Line 459: "redistrobution" → "redistribution" (appears multiple times)
- Line 461: "distringuish" → "distinguish"
- Line 464: "redistrobution" → "redistribution"

**Required action:** Run a spell check pass over the entire document. There are ~20+ typos — these are the ones I caught but there may be more.

### ⚠️ IMPORTANT: Package table inconsistencies between sections

The document defines packages in three separate tables (lines 143-155, lines 170-180, lines 213-221) with inconsistent content:

1. **"Path Length Requirements" table (lines 143-155)** lists `amdrocm-runtimes`, `amdrocm-core`, `amdrocm-developer-tools`, `amdrocm-core-sdk`, `amdrocm-raytracing`, `amdrocm-raytracing-sdk`
2. **"Package Naming" table (lines 170-180)** lists the same six packages but with slightly different descriptions
3. **"Installer for ROCm" table (lines 213-221)** lists five packages including `amdrocm-core-dev.msi` which appears nowhere else, and omits `amdrocm-raytracing` and `amdrocm-raytracing-sdk`

Questions:
- Is `amdrocm-core-dev.msi` a separate package from `amdrocm-core-sdk.msi`? The naming table doesn't mention it.
- Why do the ray tracing packages disappear from the installer section?
- The "Path Length Requirements" section seems like an odd place to define the authoritative package list — that feels more like it belongs in "Package Naming" or "Installer for ROCm."

**Recommendation:** Consolidate to a single authoritative package table (in "Package Naming" or a dedicated section), then reference it from other sections. Clarify the relationship between `core-dev` and `core-sdk`.

### ⚠️ IMPORTANT: Cache location under Program Files is unusual

Lines 102-116 specify caches under `C:\Program Files\AMD\rocm\cache\`. On Windows, `Program Files` is typically read-only for non-admin processes. Standard Windows practice stores caches in:
- `%LOCALAPPDATA%\AMD\ROCm\cache\` (per-user)
- `%PROGRAMDATA%\AMD\ROCm\cache\` (per-machine)

The document says "Caches are stored system wide and matches Windows guidelines for application data" — but `Program Files` is specifically *not* the Windows-recommended location for application data/caches. The recommended locations are `%PROGRAMDATA%` or `%LOCALAPPDATA%` per [Microsoft's guidelines](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid).

**Recommendation:** Clarify whether admin elevation is always assumed when writing caches, or move the cache location to `%PROGRAMDATA%\AMD\ROCm\cache\` for system-wide caches (or `%LOCALAPPDATA%` for per-user).

### ⚠️ IMPORTANT: Per-user install feasibility is questionable for some packages

The MSI requirements (line 232) state "Support per-user installation where technically valid for the selected package set." However, the directory layout mandates `C:\Program Files\AMD\rocm\core-X.Y` which requires admin privileges. The document doesn't describe an alternative per-user installation path (e.g., under `%LOCALAPPDATA%`).

Additionally, the registry section mentions `HKCU\Software\AMD\ROCm\X.Y\` for per-user installs and `HKCU\Software\AMD\ROCm\CurrentVersion`, but nothing else in the document describes how a per-user install actually differs from per-machine.

**Recommendation:** Either flesh out per-user installation (alternative directory, environment scope) or explicitly state that per-user installation is a future consideration and remove the per-user registry requirements for now.

### ⚠️ IMPORTANT: VS Code plugin section seems out of scope

Lines 371-387 define requirements for a "Visual Studio Code Plugin" (the heading says "Visual Studio Code" but the body describes "Visual Studio plugin" — which is it?). This feels like it belongs in a separate RFC or feature spec rather than a packaging requirements document. The packaging RFC should define the discovery mechanisms (registry, env vars) that *any* tool can use, not specify requirements for a specific IDE plugin.

**Recommendation:** Either rename to "IDE/Tool Discovery Requirements" focusing on the general mechanism, or move the VS Code/Visual Studio plugin requirements to a separate document and reference the discovery mechanisms defined here.

### 💡 SUGGESTION: Frontmatter status field

The frontmatter says `status: draft` which is correct. Consider also adding a `replaces:` or `related:` field pointing to RFC0009, since this is the Windows companion to the Linux packaging RFC.

### 💡 SUGGESTION: "Alternatives Considered" section missing

Per the project's CLAUDE.md conventions (and good RFC practice), an "Alternatives Considered" section would strengthen the document. For example:
- Why MSI over MSIX?
- Why `C:\Program Files\AMD\rocm\` vs `C:\AMD\ROCm\` (the legacy HIP SDK path)?
- Why not require long paths universally?

### 💡 SUGGESTION: ZIP archive naming inconsistency

Line 420 shows `rocm-core-X.Y.Z.zip` using a three-part version, but the directory inside is `rocm-core-X.Y\` using two-part. This is presumably intentional (patch versions install in place) but the mismatch in the example could confuse readers. Consider adding a brief note explaining this.

### 💡 SUGGESTION: ROCM_PATH for ZIP packages contradicts ZIP requirements

Line 192 states "Downloaded ROCM zip files should point ROCM_PATH to its location," but the ZIP requirements section (lines 425-427) says ZIP packages "Must not modify environment variables" and "Must not modify PATH." These are in tension — the first asks the user to set `ROCM_PATH`, the second says ZIP shouldn't touch env vars. The distinction is presumably that the *user* sets it manually vs. the *package* setting it, but this could be clearer.

### 📋 FUTURE WORK: Relationship to TheRock build artifacts

The RFC doesn't describe how TheRock's artifact system (the `artifact-*.toml` descriptors, component split of lib/run/dev/dbg/doc/test) maps to the MSI package boundaries defined here. This mapping will be important for automated packaging but is probably out of scope for a requirements RFC.

### 📋 FUTURE WORK: WiX/installer tooling

The RFC defines what MSI packages must do but doesn't specify or constrain the tooling (WiX, InstallShield, Advanced Installer, etc.). This is appropriate for a requirements doc, but a follow-up implementation RFC or design doc would need to address this.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Fix all spelling/typographical errors throughout the document (~20+ instances)

### ✅ Recommended:

1. Consolidate package tables into a single authoritative list to resolve inconsistencies
2. Reconsider cache location (`Program Files` is not standard for writable caches on Windows)
3. Clarify or defer per-user installation requirements
4. Fix "Visual Studio Code Plugin" / "Visual Studio plugin" naming mismatch and consider whether this section belongs in a packaging RFC

### 💡 Consider:

1. Add `related: RFC0009` to frontmatter
2. Add "Alternatives Considered" section
3. Clarify ZIP archive naming (three-part version filename vs two-part directory)
4. Reconcile ROCM_PATH guidance for ZIP packages

### 📋 Future Follow-up:

1. Define mapping from TheRock artifact system to MSI package boundaries
2. Implementation RFC for installer tooling selection

---

## Testing Recommendations

Documentation-only RFC — no functional tests needed. Recommend:
- Spell check pass (e.g., `aspell`, `cspell`, or VS Code spell checker)
- Internal review by someone with Windows MSI/WiX packaging experience to validate the MSI requirements are implementable as written
- Cross-reference with RFC0009 to ensure consistent terminology and versioning semantics

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The RFC covers the right topics and is well-organized. The blocking issue is the volume of typos — for a document meant to be published for cross-team review, these need to be fixed. The package table inconsistencies and cache location question should also be addressed before the RFC is finalized, though those could arguably be resolved during the RFC review process itself.
