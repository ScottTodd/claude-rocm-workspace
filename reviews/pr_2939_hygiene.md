# Hygiene Review: PR #2939

* **PR:** [ROCm/TheRock#2939](https://github.com/ROCm/TheRock/pull/2939)
* **Title:** build ocltst for OpenCL
* **Author:** lttamd (Todd tiantuo Li)
* **Branch:** `users/lttamd/addOCLtst` → `main`
* **Reviewed:** 2026-01-26
* **Review Type:** PR Hygiene

---

## Summary

This PR enables building OpenCL tests (ocltst) by passing the `BUILD_TESTS` flag to the ocl-clr subproject and including the test artifacts in the packaging.

**Net changes:** +5 lines, -1 line across 2 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** - PR has hygiene issues that should be addressed before human review.

The PR has two blocking hygiene issues: the title doesn't follow conventions, and the description doesn't explain what ocltst is or why enabling it is valuable.

---

## Hygiene Checklist

### ❌ BLOCKING: PR Title - Does not start with uppercase

**Status:** FAIL

The title "build ocltst for OpenCL" starts with a lowercase letter.

Per the PR hygiene guidelines:
> Title must be descriptive and start with an uppercase letter.

**Required action:** Update the title to start with an uppercase letter, e.g., "Build ocltst for OpenCL" or "Enable ocltst builds for OpenCL"

---

### ❌ BLOCKING: PR Description - Motivation does not explain the "why"

**Status:** FAIL

The motivation section says:
> build ocltst for OpenCL

This restates *what* the PR does, not *why* it's needed. A reviewer unfamiliar with ocltst has no idea:
- What is ocltst? (A test suite? A debugging tool? A benchmark?)
- Why do we want to build it in TheRock?
- What problem does this solve or what use case does it enable?
- Who will use these test artifacts and for what purpose?

Per the PR hygiene guidelines:
> PR description must clearly explain what problem is being solved or what feature is being added.

**Required action:** Add context explaining:
- What ocltst is (briefly)
- Why enabling it in the build is valuable
- The use case this enables

---

### ⚠️ IMPORTANT: Artifact path change not explained

The PR silently changes the artifact include path:

```diff
include = [
-  "share/ocl/**",
+  "share/opencl/**",
]
```

This looks like a correction (perhaps the old path was wrong?), but it's not mentioned in the description. If this is fixing a bug, it should be noted. If it's unrelated, it should perhaps be a separate PR.

**Recommendation:** Explain this change in the description - is this a bug fix, or related to the test enablement?

---

### ✅ PR Description - Testing Evidence

**Status:** PASS

The description includes:
- A list of expected new files (liboclperf.so, liboclruntime.so, etc.)
- Link to a dev build: https://github.com/ROCm/TheRock/actions/runs/21167094759
- Confirmation that expected files are in artifacts

This is adequate testing evidence for a build system change.

---

### ✅ PR Size

**Status:** PASS

- 6 total lines changed (5 additions, 1 deletion)
- 2 files modified

---

### ✅ Not a Revert / Roll-forward

**Status:** PASS (N/A)

---

## Recommendations

### ❌ REQUIRED Before Human Review (Blocking):

1. **Fix PR title** - Capitalize first letter: "Build ocltst for OpenCL"
2. **Expand motivation** - Explain what ocltst is and why enabling it is valuable

### ✅ Recommended Before Human Review:

1. **Explain the path change** - Note why `share/ocl/**` changed to `share/opencl/**`

### 💡 Consider:

None.

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The PR needs two fixes before human review:
1. Title should start with uppercase
2. Description should explain what ocltst is and why we want to build it

These are quick fixes that will help reviewers understand the change without needing to ask clarifying questions.
