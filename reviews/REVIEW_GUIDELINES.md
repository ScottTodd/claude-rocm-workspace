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
- Passed automated review
- May have optional recommendations for future improvements

### ⚠️ CHANGES REQUESTED

- Has blocking issues that MUST be fixed
- May also have non-blocking recommendations
- Requires another review after changes

### 🚫 REJECTED

- Fundamental problems with approach
- Requires complete rework or abandonment

---

## Issue Severity Categories

### ❌ BLOCKING (Must Fix)

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

### ⚠️ IMPORTANT (Should Fix)

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

## Evidence-Based Review (CI Validation)

When CI run data is available, use it to validate findings from the diff.
Code-only review can produce false positives — CI logs provide ground truth.

### Process

1. **Form hypotheses from the diff.** When reading changes, note potential
   behavioral impacts:
   - Removed env var → might break a downstream step
   - Changed paths → might break caching or artifact collection
   - Added/removed CMake flags → might change build behavior
   - Reordered steps → might break dependencies

2. **Gather evidence.** If the PR links a CI run (or one is discoverable on
   the branch), fetch step-level data:
   ```bash
   # Get step timings and status for a specific job
   gh api repos/OWNER/REPO/actions/jobs/JOB_ID \
     --jq '{steps: [.steps[] | {name, conclusion, started_at, completed_at}]}'
   ```
   Also find a recent baseline run on `main` for the same workflow to compare
   against.

3. **Test hypotheses.** Compare the PR run against the baseline:
   - **Step timings** — Large increases may indicate missing caching,
     unnecessary work, or configuration regressions. Note that different VM
     sizes can affect timings, so focus on relative patterns (e.g., a step
     going from 51s to 0s) rather than absolute values.
   - **Cache behavior** — Compare save/restore step durations. A cache save
     of 0s when the baseline saves data is a strong signal that cache
     configuration is broken.
   - **Step presence/absence** — New steps, missing steps, or steps that
     changed from pass to fail.
   - **Log output** — When step timings alone aren't conclusive, check actual
     log output for specific markers (cmake flags, error messages, warnings).

4. **Calibrate findings based on evidence:**
   - Hypothesis confirmed by CI data → keep finding, cite evidence
   - Hypothesis disproven by CI data → remove finding or downgrade to
     informational note
   - Unexpected pattern in CI data → investigate as potential new finding

### What to Compare

| Signal | Where to Look | What It Indicates |
|--------|---------------|-------------------|
| Cache save duration (0s vs >0s) | Save cache step timing | Cache configuration broken |
| Build step duration (large delta) | Build step timing | Missing optimization, extra work, or VM difference |
| Step conclusion changes | Step status field | Regression or flaky behavior |
| cmake configure output | Configure step logs | Flag differences, missing options |
| Artifact sizes | Upload step logs or artifact listings | Missing or extra content |

### When CI Data Is Not Available

If no CI run is linked or discoverable, note hypotheses as conditional:
> "If ccache is not configured to write within `$OUTPUT_DIR/caches`, the
> cache save step will be ineffective. **Verify by checking Save cache
> step timing in a CI run.**"

This makes the finding actionable without asserting certainty.

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

### ❌ REQUIRED (Blocking):

1. [Blocking items only]

### ✅ Recommended:

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

## Specialized Review Guidelines

For PRs that add tests or documentation, consult the detailed guidelines:

| PR Type | Guideline File |
|---------|----------------|
| Adding/modifying tests | [guidelines/tests.md](guidelines/tests.md) |
| Adding/modifying documentation | [guidelines/documentation.md](guidelines/documentation.md) |
| Adding/modifying artifacts | [guidelines/pr_patterns.md](guidelines/pr_patterns.md#pattern-adds-or-modifies-artifacts) |
| GitHub Actions workflows | [guidelines/github_actions.md](guidelines/github_actions.md) |
| General PR hygiene | [guidelines/pr_hygiene.md](guidelines/pr_hygiene.md) |
| Common PR patterns | [guidelines/pr_patterns.md](guidelines/pr_patterns.md) |
| Security (secrets, injection) | [guidelines/security.md](guidelines/security.md) |

### Quick Reference: Test Anti-Patterns (BLOCKING)

These test issues should always be marked **BLOCKING**:

1. **Testing standard library wrappers** - Don't test code that just calls `shutil.rmtree()` or `print()`
2. **Over-mocking** - If you mock the file read in a function that reads files, the test is useless
3. **Change detector tests** - Tests that mirror implementation details break on any refactor
4. **Testing frameworks** - Don't test argparse, json, etc.
5. **Excessive patching** - 5+ patches means you're testing call sequences, not behavior

### Quick Reference: Documentation Anti-Patterns (BLOCKING)

These documentation issues should always be marked **BLOCKING**:

1. **Stale information** - Specific counts, percentages, version numbers that will change
2. **Generic instructions** - Don't duplicate how to use pytest/unittest; link to official docs
3. **Wrong location** - Testing practices belong in style guides, not nested READMEs

### Quick Reference: GitHub Actions Anti-Patterns (BLOCKING)

These workflow issues should always be marked **BLOCKING**:

1. **Missing script dependencies** - Workflow calls a Python script but no prior step installs its non-stdlib imports (e.g., `boto3`, `packaging`). Trace imports transitively — the script may import a local module that imports the missing package.
2. **Caller not updated** - Reusable workflow gains a new required input but callers don't pass it
3. **Input source mismatch** - Switching from `github.event.inputs` to `inputs` breaks `workflow_dispatch`
4. **Complex inline bash** - `run:` blocks with conditionals, loops, string manipulation, or decision trees must be Python scripts per the [style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/github_actions_style_guide.md#prefer-python-scripts-over-inline-bash). One-line commands and simple `echo`/`mkdir` are fine.
5. **Unused checkout** - Workflow checks out multiple repos but a checkout's source is never wired to build/test steps (e.g., missing `-D*_SOURCE_DIR` flag). CI passes but tests the wrong source.

See [guidelines/github_actions.md](guidelines/github_actions.md) for full details.

### Quick Reference: Python Error Handling Anti-Patterns (BLOCKING)

These error handling issues should always be marked **BLOCKING**:

1. **`sys.exit()` instead of exceptions** - Use `raise RuntimeError(...)`, not `sys.exit("error")`. `sys.exit()` bypasses the call stack and makes functions untestable.
2. **`print("ERROR: ..."); return`** - Silent degradation. Raise an exception instead.
3. **`print("WARNING: ..."); continue`** - If data is missing or corrupted, that's an error, not a warning.

See the [Python style guide fail-fast section](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/python_style_guide.md#fail-fast-behavior).

### Quick Reference: Security Red Flags (BLOCKING)

These security issues should always be marked **BLOCKING**:

1. **Committed secrets** - Private keys (`.gpg`, `.pem`, `.key`, `.p12`), API keys, passwords, tokens
2. **Unverified binary files** - Binary `.gpg` keyrings, keystores, or other opaque files that could contain private material must be inspected before merge
3. **Command injection** - `system()` or `eval` with unsanitized user input
4. **Unsanitized `source`/`eval`** - Config files sourced without validation execute arbitrary code

### Quick Reference: Artifact Anti-Patterns (BLOCKING)

These artifact issues should always be marked **BLOCKING**:

1. **Duplicate file ownership** - Same stage path + component defined in multiple `artifact-*.toml` files, causing files to be packaged into multiple artifacts
2. **Stale descriptor after split** - New artifact created for files previously bundled in an existing artifact, but old descriptor not updated to remove those files
3. **Dead TOML components** - Descriptor defines components (dbg, dev, lib, etc.) that no `therock_provide_artifact()` call activates — indicates copy-paste from another descriptor

**How to check:** For any stage path in a new/changed TOML, grep all
`artifact-*.toml` for that path. Multiple hits on the same component = duplicate.

---

## Review Checklist

Before finalizing a review, verify:

**General:**
- [ ] Overall assessment has clear status (APPROVED/CHANGES REQUESTED/REJECTED)
- [ ] Every blocking issue is marked with ❌ BLOCKING
- [ ] Blocking issues are listed in "REQUIRED (Blocking)" section
- [ ] Each issue has clear severity marker (❌/⚠️/💡/📋)
- [ ] Required actions are specific and actionable
- [ ] Future work items are clearly marked as out of scope
- [ ] No incomplete cleanup is marked as "optional" or "future work"
- [ ] Testing recommendations are specific to the changes
- [ ] Conclusion matches overall assessment status

**For PRs adding tests:** See [guidelines/tests.md](guidelines/tests.md) for full checklist
- [ ] Tests verify OUR code, not standard library wrappers
- [ ] Mocks don't defeat the test's purpose (use real files where possible)
- [ ] No change detector tests or excessive patching (5+ is a red flag)
- [ ] File naming matches project conventions (`*_test.py`)

**For PRs adding documentation:** See [guidelines/documentation.md](guidelines/documentation.md) for full checklist
- [ ] No stale information (counts, percentages, versions)
- [ ] Not duplicating standard tool documentation
- [ ] Documentation in correct location (style guide vs nested README)

**For PRs adding/modifying artifacts:** See [guidelines/pr_patterns.md](guidelines/pr_patterns.md#pattern-adds-or-modifies-artifacts) for full checklist
- [ ] No duplicate component ownership across `artifact-*.toml` files (grep stage paths)
- [ ] TOML components match what `therock_provide_artifact()` COMPONENTS activates
- [ ] Old descriptor updated when splitting files into a new artifact

**For PRs modifying Python code:** See [guidelines/pr_patterns.md](guidelines/pr_patterns.md#pattern-python-code) for full checklist
- [ ] Error handling uses exceptions, not `sys.exit()` or `print()+return` (see [fail-fast](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/python_style_guide.md#fail-fast-behavior))
- [ ] No broad `except Exception` that hides bugs

**For PRs modifying GitHub Actions workflows:** See [guidelines/github_actions.md](guidelines/github_actions.md) for full checklist
- [ ] Script runtime dependencies available (trace Python imports through call chain)
- [ ] All callers of modified reusable workflows updated
- [ ] Input propagation correct for all trigger types
- [ ] No complex inline bash (conditionals/loops/string manipulation belong in Python scripts)
- [ ] Multiple checkouts wired correctly (each checkout's source consumed by intended steps)
- [ ] `runs-on:` labels pinned (not `*-latest`)

**Security (always check):** See [guidelines/security.md](guidelines/security.md) for full checklist
- [ ] No private keys or credentials committed (check binary files too)
- [ ] Binary files inspected and justified
- [ ] No `system()`/`eval`/`source` with unsanitized input
