# PR Hygiene Checklist

Objective gatekeeping checks that should pass before substantive review begins.
These are automatable and will eventually be enforced by a bot.

---

## PR Title

**Rule:** Title must be descriptive and start with an uppercase letter.
Must not be auto-generated from branch name or be overly vague.

**Fail patterns:**
- `Users/someone/branch-name` - branch name as title
- `users/someone/fix-thing` - branch name, also lowercase
- `fix` - too vague
- `update` - too vague
- `WIP` - work in progress, not ready for review

**Pass patterns:**
- `Add ROCm 6.2 support for MI300X`
- `Fix CMake detection of system LLVM`
- `Remove deprecated pytorch patch support`
- `Update clr to version 6.2.0`

**Auto-comment:**
> PR title appears to be auto-generated from the branch name or is not descriptive.
> Please update to a descriptive title that:
> - Starts with an uppercase letter
> - Summarizes what the PR does (not just "fix" or "update")
> - Does not include branch path components like `Users/name/`

---

## PR Description - Motivation or Problem Statement

**Rule:** PR description must clearly explain what problem is being solved or what feature is being added.

**Fail patterns:**
- Empty description
- Description only contains checklist items with no context
- "Fixes bug" with no explanation of what bug

**Pass patterns:**
- Explains the symptom/issue that motivated the change
- Links to related GitHub issues (if applicable)
- For bug fixes: includes error logs or reproduction steps (inline or linked)
- For features: explains the use case

**Auto-comment:**
> PR description does not explain the motivation behind this work.
> Please add context about:
> - What issue or need motivated this change?
> - For bug fixes: What was the error/symptom? (include logs or link to issue)
> - For features: What use case does this enable?

---

## PR Description - Testing Evidence

**Rule:** PR description must show evidence that changes were tested.

**Fail patterns:**
- No mention of testing
- "Tested locally" with no details
- Only mentions CI will test it

**Pass patterns:**
- Specific test commands that were run
- Screenshots or logs showing successful test output
- "Added tests in `test_foo.py`, all passing"
- For CI-only tests: explicit note explaining why local testing isn't feasible

**Auto-comment:**
> PR description does not include testing evidence.
> Please add:
> - What tests were run (commands, test names)?
> - Test results (passing count, relevant output)
> - If tests can only run in CI, explain why

---

## PR Description - Metrics (When Applicable)

**Rule:** PRs that affect build time, test duration, or binary size should include before/after metrics.

**Applies to:**
- New tests or test modifications
- New dependencies or subprojects
- Build system changes

**Required metrics by PR type:**

| PR Type | Required Metrics |
|---------|------------------|
| Adds/modifies tests | Test duration (before/after if modifying) |
| Adds dependency | Build time impact, binary size impact |
| Adds subproject | Build time, packaging considerations |

**Auto-comment:**
> This PR appears to [add tests / add a dependency / modify build system] but does not include relevant metrics.
> Please add:
> - [Test duration / Build time impact / Binary size change]
> - Before/after comparison if modifying existing behavior

---

## PR Size

**Rule:** PRs should be reviewable. Very large PRs should be split unless there's a good reason.

**Guidelines:**
- < 400 lines: No concerns
- 400-1000 lines: Acceptable if cohesive
- > 1000 lines: Should justify why it can't be split

**Exceptions (large PRs acceptable):**
- Generated code or vendored dependencies
- Large-scale automated refactoring (e.g., rename across codebase)
- Initial implementation that can't be meaningfully split

**Auto-comment:**
> This PR is quite large (X lines). Large PRs are harder to review thoroughly.
> Consider:
> - Can this be split into smaller, incremental PRs?
> - If not, please explain why in the PR description.

---

## Reverts

**Rule:** Revert PRs must include justification for the revert.

**Required in description:**
- What problem did the original PR cause?
- Error logs, test failures, or user reports that motivated the revert
- Link to the original PR being reverted

**Auto-comment:**
> This appears to be a revert but does not explain why the original change is being reverted.
> Please add:
> - What problem did the original PR cause?
> - Evidence (error logs, test failures, user reports)
> - Link to the original PR

---

## Roll-forwards (Re-landing Reverted Changes)

**Rule:** When re-landing a previously reverted PR, must explain what was fixed.

**Required in description:**
- Link to the original PR and the revert PR
- What was wrong with the original approach?
- What changed to fix the issue?

**Auto-comment:**
> This appears to re-land a previously reverted change.
> Please add:
> - Links to the original PR and revert PR
> - What was fixed since the revert?

---

## Reviewers

**Rule:** PR should have appropriate reviewers assigned based on the files changed.

**How to identify appropriate reviewers:**
- Run `git blame` on modified files to find recent authors/reviewers
- Check CODEOWNERS if the project has one
- For cross-cutting changes, include reviewers from each affected area

**Note:** This is harder to automate but Claude can check during review.

---

## Summary

| Check | Automatable | Severity |
|-------|-------------|----------|
| Title format | Yes | Block merge |
| Problem statement | Partial | Block review |
| Testing evidence | Partial | Block review |
| Metrics included | Partial | Flag for review |
| PR size | Yes | Flag for review |
| Revert justification | Yes (detect revert) | Block review |
| Roll-forward explanation | Partial | Block review |
| Reviewers assigned | Yes | Flag for review |
