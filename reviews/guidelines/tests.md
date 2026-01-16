# Test Review Guidelines

Checklist for reviewing PRs that add or modify tests.

## Summary

| Check | Automatable | Severity | Notes |
|-------|-------------|----------|-------|
| [Test duration in PR description](#pr-description-requirements) | Partial | Flag for review | Can detect missing, not validate |
| [Test coverage for new code](#new-functionality) | Partial | BLOCKING if none | Coverage tools can assist |
| [Regression test for bug fix](#bug-fixes) | No | IMPORTANT | Requires understanding intent |
| [Duration is reasonable](#test-duration) | Partial | IMPORTANT if outlier | Compare to subproject peers |
| [Tests are deterministic](#determinism) | No | BLOCKING if flaky | Requires analysis |
| [Tests run locally](#local-execution) | No | IMPORTANT | Requires trying or docs |
| [Tests integrated with CI](#ci-integration) | Yes | BLOCKING if missing | Check workflow files |

**What reviewers look for:**
- Evidence that tests were actually run (duration, pass/fail)
- Coverage of new functionality and edge cases
- No flaky or order-dependent tests
- Reasonable CI impact

**What automation can help with:**
- Detecting missing duration/metrics in PR description
- Measuring actual test duration from CI logs
- Checking if new test files are picked up by CI workflows
- Coverage reports (if configured)

---

## Scope and Exemptions

### When This Guide Applies

This guide applies to PRs that:
- Add new tests for new functionality
- Add regression tests for bug fixes
- Modify existing test behavior
- Add significant test infrastructure

### Lighter Review for Trivial Test Changes

Some test changes don't need full scrutiny:
- Fixing typos in test names or comments
- Updating tests to match API changes (rename, signature change)
- Removing obsolete tests
- Minor test cleanup (formatting, imports)

For these, verify CI passes and move on.

### Test-Only PRs (Adding Coverage)

PRs that only add tests to existing code:
- "Regression test for bug fix" doesn't apply—there's no bug being fixed
- Focus on test quality, coverage value, and CI integration
- Still encourage test duration in PR description

---

## PR Description Requirements

Before diving into code review, verify the PR description includes:

| Item | Required | Notes |
|------|----------|-------|
| Test duration | Yes | Total time for new/modified tests |
| Test count | Recommended | Number of tests added/modified (often obvious from diff) |
| Local run instructions | Recommended | Command to run tests locally |
| CI workflow link | If applicable | Link to passing CI run |

**If missing test duration:** Ask the author to add before proceeding with review.
This saves reviewer time and ensures authors have actually run their tests.

**If missing other items:** Use judgment—don't block review for obvious info.

---

## Test Coverage

### New Functionality

**Check:** Is new code covered by tests?

**Questions to ask:**
- Does every new public function/class have test coverage?
- Does every **new code path in existing functions** have test coverage?
  - New parameters that change behavior
  - New branches (if/else paths)
  - New early returns or error conditions
- Are the tests testing behavior, not just that code runs?
- Do tests cover the stated use case from the PR description?

**Common miss:** A function is refactored to accept an optional parameter that skips
some work (e.g., pass pre-fetched data to avoid redundant API call). The new parameter
path needs test coverage even though the function already has tests for the old path.

**Severity:**
- No tests for new functionality: **BLOCKING**
- Partial coverage of new code: **IMPORTANT**
- Missing edge case tests: **SUGGESTION**

### Bug Fixes

**Check:** Does the fix include a regression test?

**Questions to ask:**
- Is there a test that would have caught this bug?
- Does the test fail without the fix and pass with it?

**Severity:**
- No regression test for bug fix: **IMPORTANT** (sometimes **BLOCKING** for critical bugs)

---

## Test Duration

### Context

TheRock is a superproject containing multiple subprojects, each with potentially
100,000+ tests and total runtimes of 2+ hours. Absolute duration thresholds
don't apply uniformly. What matters is whether new tests are reasonable
*relative to the rest of the project*.

### What to Look For

**Check:** Are new tests oversized relative to comparable tests? Are tests for
one subproject taking significantly longer than tests for another subproject?

**Questions to ask:**
- Does the PR description include test duration?
- How does this compare to similar tests in the same subproject?
- If significantly slower than peers, is there justification?
- Are slow tests marked appropriately (e.g., `@pytest.mark.slow`, filtered out
  of "smoketests")?

**Red flags:**
- New test takes 10x longer than similar existing tests
- Test duration not mentioned in PR description
- Slow tests mixed in with fast test suites without marking

**Where to verify:**
- GitHub Actions workflow logs → look for test timing output
- Compare to existing test durations in the same subproject

**Severity:**
- Tests significantly slower than peers without justification: **IMPORTANT**
- No duration info in PR description: **IMPORTANT** (ask author to add)
- Slow tests not marked/categorized: **SUGGESTION**

*Note: More specific guidelines per subproject may be added as patterns emerge.*

---

## Test Quality

### Clarity

**Check:** Are tests readable and maintainable?

**Questions to ask:**
- Do test names describe what they're testing?
- Is the test structure clear (arrange/act/assert)?
- Are assertions meaningful (not just `assert result`)?
- Do failing tests produce helpful error messages?

**Severity:**
- Unclear what test is validating: **IMPORTANT**
- Poor test names: **SUGGESTION**

### Independence

**Check:** Are tests independent and isolated?

**Questions to ask:**
- Can tests run in any order?
- Do tests clean up after themselves?
- Are there hidden dependencies between tests?
- Do tests rely on global state?

**Severity:**
- Tests depend on execution order: **BLOCKING**
- Tests leave artifacts/state: **IMPORTANT**

### Determinism

**Check:** Are tests deterministic?

**Questions to ask:**
- Do tests use fixed seeds for random operations?
- Are time-dependent tests properly mocked?
- Do tests depend on external services that might be flaky?
- Do tests make network calls that could timeout or fail intermittently?
- Do tests depend on filesystem ordering or timing?

**Common flakiness sources:**
- Network calls to external services
- Time-based assertions without mocking
- Random data without fixed seeds
- Race conditions in async code
- Filesystem operations assuming ordering

**Severity:**
- Flaky tests: **BLOCKING**
- Potential flakiness not addressed: **IMPORTANT**

---

## Test Runnability

### Local Execution

**Check:** Can tests be run locally?

**Questions to ask:**
- Are instructions for running tests locally included?
- Do tests require special hardware (GPUs, specific architectures)?
- If hardware-dependent, is there a way to run a subset locally?

**Severity:**
- Tests only runnable in CI with no explanation: **IMPORTANT**
- Missing local run instructions: **SUGGESTION**

### CI Integration

**Check:** Are tests properly integrated with CI?

**Questions to ask:**
- Are new tests picked up by existing CI workflows?
- If new workflow needed, is it included in the PR?
- Do tests run on appropriate triggers (PR, push, schedule)?

**Severity:**
- Tests not running in CI: **BLOCKING**
- Tests running on wrong triggers: **IMPORTANT**

---

## Test Structure

### Organization

**Check:** Are tests well-organized?

**Questions to ask:**
- Are tests in the appropriate directory?
- Do test files mirror source file structure?
- Are related tests grouped logically?

**Severity:**
- Tests in wrong location: **SUGGESTION**
- Poor test organization: **SUGGESTION**

### Fixtures and Helpers

**Check:** Is test infrastructure appropriate?

**Questions to ask:**
- Are fixtures/helpers reusable where appropriate?
- Is there unnecessary duplication across tests?
- Are complex setups extracted into fixtures?

**Severity:**
- Significant duplication: **SUGGESTION**
- Missing useful fixtures: **SUGGESTION**

---

## Code Testability

**Check:** Could the code under test be structured better for testing?

**Questions to ask:**
- Are there functions that are hard to test due to tight coupling?
- Could code be refactored to separate pure logic from I/O?
- Are there implicit dependencies that could be made explicit?

**This is often out of scope for a test-focused review**, but worth noting
if the code structure makes testing unnecessarily difficult.

**Severity:**
- Code structure prevents adequate testing: **IMPORTANT** (flag for architecture review)
- Minor testability improvements possible: **FUTURE WORK**

---

## TheRock-Specific Considerations

### GPU-Dependent Tests

- Tests requiring specific GPU architectures should be clearly marked
- Consider gating tests by `THEROCK_AMDGPU_FAMILIES` or similar
- Document which GPU families are tested in CI vs require manual testing

### Build System Tests

- For CMake changes, verify tests cover different configurations
- Test both `THEROCK_ENABLE_*` combinations where relevant
- Consider testing with and without optional dependencies

### Subproject Tests

- When adding tests to subprojects (under `external/`), verify they integrate with the superproject test infrastructure
- Check if tests need to be registered in the parent CMakeLists.txt

---

## Summary Checklist

**Before reviewing code:**
- [ ] PR description includes test duration
- [ ] PR description includes test count
- [ ] PR description includes how to run tests locally

**During code review:**
- [ ] New functionality has test coverage
- [ ] Bug fixes include regression tests
- [ ] Tests are clear, independent, and deterministic
- [ ] Test duration is reasonable
- [ ] Tests can be run locally (or explain why not)
- [ ] Tests are integrated with CI
