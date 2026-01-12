# Test Review Guidelines

Checklist for reviewing PRs that add or modify tests.

---

## PR Description Requirements

Before diving into code review, verify the PR description includes:

| Item | Required | Notes |
|------|----------|-------|
| Test duration | Yes | Total time for new/modified tests |
| Test count | Yes | Number of tests added/modified |
| Local run instructions | Recommended | Command to run tests locally |
| CI workflow link | If applicable | Link to passing CI run |

**If missing:** Ask the author to add these metrics before proceeding with review.
This saves reviewer time and ensures authors have actually run their tests.

---

## Test Coverage

### New Functionality

**Check:** Is new code covered by tests?

**Questions to ask:**
- Does every new public function/class have test coverage?
- Are the tests testing behavior, not just that code runs?
- Do tests cover the stated use case from the PR description?

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

### Expectations

**Check:** Are test durations reasonable?

**Guidelines:**
- Unit tests: < 1 second each
- Integration tests: < 30 seconds each
- End-to-end tests: Document expected duration

**Questions to ask:**
- Does the PR description include test duration?
- If modifying existing tests, is there a before/after comparison?
- Are slow tests marked appropriately (e.g., `@pytest.mark.slow`)?

**Where to verify (if claims seem off):**
- GitHub Actions workflow logs → look for test timing output
- Run locally with timing: `time pytest path/to/tests`

**Severity:**
- Tests add > 30s to CI without justification: **IMPORTANT**
- No duration info in PR description: **IMPORTANT** (ask author to add)
- Slow tests not marked/categorized: **SUGGESTION**

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
