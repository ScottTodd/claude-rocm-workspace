# Code Review System

This directory contains code review documentation and completed reviews.

---

## Quick Start

### Request a Review

**Comprehensive review (everything):**

```
"Review my current branch"
"Review PR #1234"
```

**Focused review (single aspect):**

```
"Do a style review of my changes"
"Run a test coverage review"
"Check documentation for this PR"
```

**Parallel reviews (multiple aspects):**

```
"Run style, tests, and documentation reviews in parallel"
"Review for architecture and security in parallel"
```

---

## Review Types Available

| Type | Focus | Use When |
|------|-------|----------|
| **Comprehensive** | Everything | Final automated review |
| **Style** | Code formatting & conventions | After refactoring |
| **Tests** | Test coverage & quality | New features, bug fixes |
| **Documentation** | Docs, comments, help text | API changes, complex code |
| **Architecture** | Design & structure | Major features, refactoring |
| **Security** | Vulnerabilities & risks | Auth changes, input handling |
| **Performance** | Efficiency & scaling | Hot paths, optimization work |

See [REVIEW_TYPES.md](REVIEW_TYPES.md) for detailed descriptions.

---

## How It Works

1. **You request a review** with specific focus areas
2. **Claude analyzes** your code with that focus in mind
3. **Review is written** to `reviews/pr_{REPO}_{NUMBER}.md` or `reviews/local_{COUNTER}_{branch-name}.md` (with `_{TYPE}` suffix for focused reviews)
4. **You address issues** based on severity (❌ BLOCKING, ⚠️ IMPORTANT, 💡 SUGGESTION)
5. **Claude can re-review** after you fix blocking issues

---

## Review Severity Levels

### ❌ BLOCKING (Must Fix)

Critical issues that prevent approval:

- Bugs and correctness issues
- Security vulnerabilities
- Incomplete cleanup (dead code)
- Missing critical tests
- Breaking changes without migration

### ⚠️ IMPORTANT (Should Fix)

Issues that significantly impact quality:

- Missing error handling
- Poor naming that hurts readability
- Test coverage gaps
- Missing documentation for complex code

### 💡 SUGGESTION (Nice to Have)

Optional improvements:

- Style preferences
- Additional test cases
- Alternative approaches
- Optimization opportunities

### 📋 FUTURE WORK (Out of Scope)

Improvements for later:

- Unrelated refactoring
- Features beyond current scope
- Large-scale changes

---

## File Naming Convention

### PR Reviews
```
reviews/pr_{REPO}_{NUMBER}.md              # Comprehensive review (no type suffix)
reviews/pr_{REPO}_{NUMBER}_{TYPE}.md       # Focused review (with type suffix)
```

The repository name is extracted from the PR URL (e.g., `TheRock` from `https://github.com/ROCm/TheRock/pull/2761`).

Examples:
- `reviews/pr_TheRock_2761.md` - comprehensive review of TheRock PR #2761
- `reviews/pr_TheRock_2761_style.md` - style-focused review of TheRock PR #2761
- `reviews/pr_rocm-systems_3066.md` - comprehensive review of rocm-systems PR #3066

### Local Branch Reviews

For reviewing local branches before they become PRs:

```
reviews/local_{COUNTER}_{branch-name}.md        # Comprehensive review
reviews/local_{COUNTER}_{branch-name}_{TYPE}.md # Focused review
```

Examples:
- `reviews/local_001_users-myname-fix-bug.md` - comprehensive review
- `reviews/local_001_users-myname-fix-bug_style.md` - style-focused review
- `reviews/local_002_add-new-feature.md` - next local review

**Counter:** Use incrementing numbers (001, 002, etc.) for chronological ordering. Claude will scan existing files to determine the next number.

**Branch name sanitization:** Slashes are converted to dashes (e.g., `users/myname/fix-bug` → `users-myname-fix-bug`). Other characters in branch names (including dashes) are preserved.

**No type suffix = comprehensive:** When no type suffix is present, the review is comprehensive (covers all aspects).

---

## Directory Structure

```
reviews/
├── README.md                          # This file (includes naming conventions)
├── REVIEW_GUIDELINES.md              # How to write reviews
├── REVIEW_TYPES.md                   # Review type definitions
├── pr_{REPO}_{NUMBER}.md             # PR reviews
├── pr_{REPO}_{NUMBER}_{TYPE}.md      # Focused PR reviews
├── local_{COUNTER}_{branch-name}.md  # Local branch reviews
└── remove-pytorch-patch-support.md   # Example (predates convention)
```

---

## Documentation Files

- **[README.md](README.md)** - This quick start guide
- **[REVIEW_GUIDELINES.md](REVIEW_GUIDELINES.md)** - Detailed guidelines for writing reviews
- **[REVIEW_TYPES.md](REVIEW_TYPES.md)** - Complete review type definitions and examples

---

## Examples

### Example 1: Comprehensive Review (Default)

```
User: "Review my current branch"

Claude:
- Analyzes all aspects (style, tests, docs, architecture, security, performance)
- Creates reviews/local_001_my-branch-name.md
- Provides comprehensive assessment with all severity levels
```

### Example 2: Focused Style Review

```
User: "Do a style review of my refactoring"

Claude:
- Focuses only on code style, formatting, naming
- Creates reviews/local_001_my-branch-name_style.md
- Ignores other aspects (tests, architecture, etc.)
```

### Example 3: Parallel Reviews

```
User: "Run tests and documentation reviews in parallel"

Claude:
- Launches two review agents simultaneously
- One analyzes test coverage
- One analyzes documentation
- Combines results into reviews/local_001_my-branch-name.md with separate sections
```

### Example 4: Sequential Reviews

```
User: "Review my branch"
Claude: [Creates comprehensive review with blocking issues]

User: [Fixes blocking issues]

User: "Re-review the changes"
Claude: [Creates updated review, verifies fixes]
```

---

## Best Practices

### When to Use Each Review Type

**Use Comprehensive when:**
- Final automated check before submitting PR
- Reviewing an open PR
- Unsure what aspects to focus on

**Use Focused Reviews when:**
- You've changed a specific aspect (e.g., just added tests)
- You want deep analysis of one area
- Running reviews in parallel for efficiency
- Iterating on specific issues

**Use Parallel Reviews when:**
- New feature (architecture + tests + docs)
- Performance work (performance + tests)
- Security changes (security + tests)
- Refactoring (style + architecture)

### Review Workflow

1. **Early check:** Run focused reviews during development
   - Style review after refactoring
   - Test review after adding tests
   - Architecture review for design validation

2. **Pre-submission:** Run comprehensive review
   - Catches all issues before human review
   - Ensures complete coverage

3. **Fix and iterate:** Address blocking issues
   - Fix ❌ BLOCKING items first
   - Re-run focused review on changed areas
   - Address ⚠️ IMPORTANT items

4. **Submit for human review:** When approved
   - All blocking issues resolved
   - Important issues addressed or documented
   - Review file included for human reviewer context

---

## Tips

### For Getting Good Reviews

1. **Be specific:** "Review tests" is more focused than "Review everything"
2. **Use parallel reviews:** Save time by running multiple types at once
3. **Iterate:** Fix blocking issues, then re-review
4. **Ask questions:** If a review finding is unclear, ask for clarification
5. **Include context:** Mention relevant background when requesting reviews

### For Understanding Review Results

1. **Severity matters:** ❌ blocks approval, 💡 is optional
2. **Context matters:** BLOCKING in one review type isn't blocking in another
3. **Reviews complement:** A comprehensive review might miss deep issues a focused review catches
4. **Not all suggestions apply:** Use judgment on 💡 SUGGESTIONS
5. **Future work is OK:** 📋 items can be deferred to later PRs

---

## Customization

You can request custom review criteria:

```
"Review this focusing on error handling and edge cases"
"Check if this follows our project's CMake patterns"
"Review for Windows compatibility issues"
```

Claude will adapt the review to your specific needs.

---

## Questions?

Ask Claude:

- "What review type should I use for [scenario]?"
- "Explain this review finding in more detail"
- "How do I address this blocking issue?"
- "Can you re-review just the test coverage after my fixes?"
