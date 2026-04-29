# Branch Review: multi-arch-release-docs

* **Branch:** `multi-arch-release-docs`
* **Base:** `main`
* **Reviewed:** 2026-04-27
* **Commits:** 2 commits

---

## Summary

Restructures `RELEASES.md` to introduce multi-arch releases as a first-class
section alongside the existing per-family release documentation. Adds a new
top-level "Multi-arch releases" section covering Python packages and tarballs,
demotes existing content under "Per-family releases", and updates the TOC, intro,
and verification sections.

**Net changes:** +207 lines, -64 lines across 1 file (RELEASES.md)

---

## Overall Assessment

**✅ APPROVED** - Well-structured documentation reorganization. The multi-arch
section is clear and self-contained. A few items to tighten up before human
review.

**Strengths:**

- Clean top-level split between multi-arch and per-family, with comparison table
- Multi-arch Python install instructions are concise — one command, one table
- Tarball section explains the `.kpack/` concept and per-family vs multiarch variants
- Good use of HTML comments for TODOs (URL changes, `--extra-index-url` transition)
- Status table with issue links gives readers a clear picture of what's available

---

## Detailed Review

### 1. Multi-arch tarballs section

#### ⚠️ IMPORTANT: Tarball section ends abruptly after the NOTE callout

The multi-arch tarballs section describes the two variants and has a `> [!NOTE]`
saying index pages aren't yet generated, but doesn't include any download/extract
example or verification step (unlike the per-family tarball section which has
manual extraction, automated extraction, and usage subsections). Even with "coming
soon" status, showing the expected tarball layout and a `tar -xf` example would
help readers understand what to expect.

The earlier version of this section (before user edits) had download/extract
examples and verification commands — consider restoring a trimmed version of
those, perhaps gated behind a note that URLs are not yet final.

**Recommendation:** Add at minimum a `tar -xf` example and `ls install/` output
showing the `.kpack/` directory, even if the download URL is a placeholder.

### 2. Broken anchor links in per-family section

#### ⚠️ IMPORTANT: Internal anchor links may be broken after heading level changes

The per-family section's headings were all bumped one level (e.g.
`## Installing releases using pip` → `### Installing per-family releases using pip`,
`### Installing ROCm Python packages` → `#### Installing ROCm Python packages`).
Several places within the per-family section have cross-references to anchors:

- Line ~397: "listed above" links to `#installing-rocm-python-packages` — this
  anchor still works since the heading text didn't change, just the level.
- The "Index page listing" table has links like `#rocm-for-gfx94X-dcgpu` — these
  also still work since heading text is preserved.

These should be fine since GitHub generates anchors from heading text regardless
of level. No action needed, but worth verifying on a rendered preview.

### 3. Comparison table

#### 💡 SUGGESTION: "Package extras/variants" in comparison table is vague

The "GPU selection" row says "Package extras/variants" for multi-arch. This is
accurate but abstract. The Python section uses `device-gfx1100` extras and the
tarball section uses tarball name variants — the table could give a concrete
example like `pip extras (device-gfx1100)` to be more immediately useful to a
skimming reader. However, this was already reviewed and approved by the user in
the current form, so this is just a thought for future iteration.

### 4. Per-family tarball section overlap

#### 💡 SUGGESTION: Per-family tarball section now has redundant context

The per-family "Installing from tarballs" section (line ~662) still has the full
directory layout listing and general explanation of what tarballs are. With the
multi-arch tarball section now covering the same ground first, a reader going
top-to-bottom sees the directory layout twice. Consider adding a brief note at
the start of the per-family tarball section pointing back to the multi-arch
tarball section for the general overview, and focusing the per-family section on
what's specific to per-family tarballs (the per-family index URLs, no `.kpack/`
directory).

### 5. TOC HTML comment

#### 💡 SUGGESTION: HTML comment in TOC may render oddly

Line 27 has `<!-- - [Installing multi-arch PyTorch Python packages](...) -->` in
the TOC. This is fine for hiding the entry until PyTorch packages are ready, but
some markdown renderers may insert blank space for the comment. Worth checking
on GitHub's rendered preview.

---

## Recommendations

### ✅ Recommended:

1. Add a download/extract example to the multi-arch tarballs section (even with
   placeholder URLs) so it's self-contained like the Python packages section.

### 💡 Consider:

1. Add a forward reference from the per-family tarball section to the multi-arch
   tarball section to reduce duplication of the general "what is a tarball" content.
2. Verify TOC HTML comment renders cleanly on GitHub.

### 📋 Future Follow-up:

1. Uncomment PyTorch section once #3332 lands multi-arch torch in nightly releases.
2. Replace `--extra-index-url` with `--index-url` once the index is self-contained.
3. Update tarball and Python package URLs once CloudFront paths are finalized.
4. Add multi-arch native packages section once #3333 is implemented.

---

## Testing Recommendations

- Render RELEASES.md on GitHub (push branch, check rendered preview) and verify:
  - All TOC links resolve correctly
  - HTML comments don't produce visible artifacts
  - Comparison table renders cleanly
  - Status badges load

---

## Conclusion

**Approval Status: ✅ APPROVED**

The restructuring is clean and the multi-arch documentation provides a clear
entry point for users. The main gap is the tarballs section stopping short of
a concrete download/extract example, which should be straightforward to add.
