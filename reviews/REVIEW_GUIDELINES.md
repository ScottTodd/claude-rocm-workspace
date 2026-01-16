# Code Review Guidelines

This document provides guidance on how to structure and categorize code reviews to ensure clarity about what must be fixed versus what's optional.

> **See also:**
> - [README.md](README.md) - Quick start guide for requesting reviews
> - [REVIEW_TYPES.md](REVIEW_TYPES.md) - Different review types and focus areas (style, tests, documentation, architecture, security, performance)

---

## Review Status Levels

Use these status levels in the "Overall Assessment" section:

### ✅ APPROVED

- No blocking issues
- Code is ready for human review
- May have optional recommendations for future improvements

### ⚠️ CHANGES REQUESTED

- Has blocking issues that MUST be fixed before human review
- May also have non-blocking recommendations
- Requires another review after changes

### 🚫 REJECTED

- Fundamental problems with approach
- Code should not proceed to human review even with fixes
- Requires complete rework or abandonment

---

## Issue Severity Categories

### ❌ BLOCKING (Must Fix Before Human Review)

**When to use:**

- Correctness issues (bugs, logic errors)
- Incomplete cleanup (dead code, unused parameters left behind)
- Security vulnerabilities
- Breaking changes without migration path
- Style violations that break established patterns
- Missing critical tests for new functionality
- Performance regressions
- Incomplete feature implementation

**Examples:**

- ❌ BLOCKING: Incomplete cleanup - unused function parameters
- ❌ BLOCKING: Security issue - SQL injection vulnerability
- ❌ BLOCKING: Breaking change - removes public API without deprecation
- ❌ BLOCKING: Logic error - off-by-one error in loop bounds

**How to write:**

```markdown
### ❌ BLOCKING: [Brief description]
- Clear explanation of the issue
- Why it's blocking (impact)
- **Required action:** Specific fix needed
```

### ⚠️ IMPORTANT (Should Fix Before Human Review)

**When to use:**

- Missing error handling for likely edge cases
- Poor variable/function naming that hurts readability
- Missing documentation for non-obvious code
- Test coverage gaps for edge cases
- Minor performance concerns
- Code duplication that should be refactored

**Examples:**

- ⚠️ IMPORTANT: Missing error handling for file not found
- ⚠️ IMPORTANT: Function name doesn't match what it does
- ⚠️ IMPORTANT: No test for empty input case

**How to write:**

```markdown
### ⚠️ IMPORTANT: [Brief description]
- Explanation of the issue
- Why it matters
- **Recommendation:** Suggested fix
```

### 💡 SUGGESTION (Nice to Have)

**When to use:**

- Minor style preferences not covered by project standards
- Alternative approaches that might be clearer
- Optimization opportunities with minimal impact
- Additional test cases for comprehensive coverage
- Documentation improvements beyond requirements

**Examples:**

- 💡 SUGGESTION: Consider using list comprehension for clarity
- 💡 SUGGESTION: Could add type hints to this function
- 💡 SUGGESTION: Might extract this into a helper function

**How to write:**

```markdown
### 💡 SUGGESTION: [Brief description]
- Brief explanation
- Why it might be better (but optional)
```

### 📋 FUTURE WORK (Separate Scope)

**When to use:**
- Improvements that are out of scope for current PR
- Refactoring opportunities in existing code
- Features that build on this work
- Technical debt to address later
- Large-scale changes that affect other areas

**Examples:**
- 📋 FUTURE WORK: Migrate entire codebase to use this pattern
- 📋 FUTURE WORK: Add telemetry for this feature
- 📋 FUTURE WORK: Refactor related legacy code

**How to write:**
```markdown
### 📋 FUTURE WORK: [Brief description]
- Explanation of the opportunity
- Why it's out of scope now
- (Optionally) Link to tracking issue
```

---

## Decision Framework

Use this flowchart to categorize issues:

```
Is this a correctness/security issue?
├─ YES → ❌ BLOCKING
└─ NO
   └─ Is this incomplete cleanup of code being modified?
      ├─ YES → ❌ BLOCKING
      └─ NO
         └─ Will this cause problems for users/developers soon?
            ├─ YES → ⚠️ IMPORTANT
            └─ NO
               └─ Is this an improvement to code being modified?
                  ├─ YES → 💡 SUGGESTION
                  └─ NO → 📋 FUTURE WORK
```

### Key Principle: Cleanup Scope

**BLOCKING if:**

- You're removing a feature → remove ALL related code including dead parameters, unused constants, helper functions
- You're refactoring code → update ALL call sites and related functions
- You're changing an API → update ALL usages and documentation

**NOT BLOCKING if:**

- Improvement affects code you're NOT currently modifying
- Opportunity to refactor unrelated code
- Enhancement that's genuinely independent

### Key Principle: API Renames

- **Internal-only code** (single repo): Update all callsites, no backwards compat alias needed
- **Public/cross-repo APIs**: May need backwards compat alias or coordinated migration

---

## Review Structure Template

```markdown
# Branch Review: [branch-name]

* **Branch:** `branch-name`
* **Base:** `main` or `upstream/main`
* **Reviewed:** YYYY-MM-DD
* **Commits:** [count] commits

---

## Summary

[2-3 sentence overview of what the PR does]

**Net changes:** [+X lines, -Y lines across Z files]

---

## Overall Assessment

**[Status Symbol] [STATUS]** - [Brief justification]

**Strengths:**

- [Positive aspects]

**[Blocking/Important] Issues:**

- [List of issues by severity]

---

## Detailed Review

### 1. [Component/File Name]

**[Severity]: [Issue Title]**

- Explanation
- Impact
- **Required action:** or **Recommendation:**

[Repeat for each major component]

---

## Recommendations

### ❌ REQUIRED Before Human Review (Blocking):

1. [Blocking items only]

### ✅ Recommended Before Human Review:

1. [Important items and good practices]

### 💡 Consider:

1. [Suggestions]

### 📋 Future Follow-up:

1. [Out of scope items]

---

## Testing Recommendations

[Specific tests to run]

---

## Conclusion

**Approval Status: [Status Symbol] [STATUS]**

[Summary of what needs to happen next]
```

---

## Common Pitfalls to Avoid

### ❌ DON'T: Be too lenient with incomplete cleanup

```markdown
### 💡 SUGGESTION: Consider removing unused parameter
```

### ✅ DO: Mark incomplete cleanup as blocking

```markdown
### ❌ BLOCKING: Incomplete cleanup - unused parameter
This PR removes the feature, so all related code must be removed.
**Required action:** Remove `old_param` from function signature
```

---

### ❌ DON'T: Make unrelated improvements blocking

```markdown
### ❌ BLOCKING: Should refactor the entire authentication system
```

### ✅ DO: Separate scope appropriately

```markdown
### 📋 FUTURE WORK: Refactor authentication system
This PR touches auth, which revealed opportunities to improve
the overall auth architecture. Consider as separate effort.
```

---

### ❌ DON'T: Use vague severity

```markdown
### Note: This could be better
```

### ✅ DO: Use clear severity markers

```markdown
### 💡 SUGGESTION: Consider more descriptive variable names
Variable `x` could be `user_count` for clarity.
```

---

## Review Checklist

Before finalizing a review, verify:

- [ ] Overall assessment has clear status (APPROVED/CHANGES REQUESTED/REJECTED)
- [ ] Every blocking issue is marked with ❌ BLOCKING
- [ ] Blocking issues are listed in "REQUIRED Before Human Review" section
- [ ] Each issue has clear severity marker (❌/⚠️/💡/📋)
- [ ] Required actions are specific and actionable
- [ ] Future work items are clearly marked as out of scope
- [ ] No incomplete cleanup is marked as "optional" or "future work"
- [ ] Testing recommendations are specific to the changes
- [ ] Conclusion matches overall assessment status
