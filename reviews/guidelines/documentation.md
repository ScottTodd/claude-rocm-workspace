# Documentation Review Guidelines

Checklist for reviewing PRs that add or modify documentation (README files, guides, etc.).

## Summary

| Check | Severity | Notes |
|-------|----------|-------|
| [No stale information](#information-that-will-go-stale) | BLOCKING | Counts, percentages, version numbers |
| [Not duplicating standard docs](#generic-instructions) | IMPORTANT | Link instead of repeating |
| [Correct location](#documentation-location) | IMPORTANT | Style guide vs README vs docstring |
| [Adds value](#value-assessment) | IMPORTANT | Not just restating code |

---

## Information That Will Go Stale

**BLOCKING:** Don't include specific counts, percentages, or version numbers that change.

```markdown
<!-- BAD: Will go stale immediately -->
This directory contains **54 tests** with **96% code coverage**.

The test file includes:
- `test_version_to_str` - 5 tests
- `test_update_package_name` - 8 tests

<!-- GOOD: Evergreen -->
This directory contains unit tests for the packaging scripts.
Run `pytest --cov` to see current coverage.
```

**Why this matters:**
- Numbers go stale on the next commit
- Creates maintenance burden to keep docs in sync
- Misleads readers when inevitably out of date
- Adds no value over just looking at the code

**What to do instead:**
- Describe what exists conceptually
- Point to commands that show current state
- Let the code be the source of truth

---

## Generic Instructions

**IMPORTANT:** Don't document how to use Python/pytest/unittest - link to official docs.

```markdown
<!-- BAD: Generic instructions for any Python project -->
### Run All Tests
python3 -m unittest discover -v

### Run Specific Test
python3 -m unittest test_module.TestClass.test_method -v

### Run a Single Test Method
To run just one specific test case:
python3 -m unittest test_module.TestClass.test_method -v

<!-- GOOD: Project-specific instructions only -->
### Running Packaging Tests

See the [testing guide](../../docs/testing.md) for general pytest usage.

These tests require:
- The `package.json` file to be present in `linux/`
- No special hardware or CI environment
```

**Why this matters:**
- Duplicates official documentation that's better maintained
- Goes stale when tool versions change
- Adds noise without project-specific value
- New contributors already know how to use standard tools

**What to include instead:**
- Project-specific setup requirements
- Non-obvious dependencies or prerequisites
- Links to authoritative documentation
- Things that are unique to this project

---

## Documentation Location

**IMPORTANT:** Put documentation where it will be found and maintained.

| Content Type | Location | Example |
|--------------|----------|---------|
| Testing practices | Style guide | `docs/development/style_guides/python_style_guide.md` |
| Project-wide test instructions | Central docs | `docs/testing.md` |
| CI/CD instructions | Workflow README or central docs | `.github/workflows/README.md` |
| Module-specific notes | Docstrings or module header | Top of Python file |
| API documentation | Adjacent to code | Docstrings, type hints |

**Red flags for wrong location:**
- README deeply nested in subdirectory with generic content
- Testing practices in a package-specific README instead of style guide
- Duplicate instructions across multiple READMEs

**Ask:** "If someone needs this information, where would they look first?"

---

## Value Assessment

**IMPORTANT:** Documentation should add value beyond what the code already shows.

```markdown
<!-- BAD: Just restating what the code does -->
### packaging_utils.py Tests

The `test_linux_packaging_utils.py` file includes tests for:

- `print_function_name()` - Function name printing
- `read_package_json_file()` - JSON file reading
- `is_key_defined()` - Key validation

<!-- GOOD: Explains non-obvious aspects -->
### Test Architecture

Tests use the real `package.json` file rather than mocks to ensure
tests catch real-world issues. This means tests may need updating
when package definitions change.

For tests that require `dpkg-buildpackage` or `rpmbuild`, we mock
only the external tool invocation, not the file preparation logic.
```

**Questions to ask:**
- Does this explain something not obvious from reading the code?
- Would a developer benefit from reading this before diving into code?
- Is this documenting decisions/rationale rather than restating implementation?

---

## Contributing Sections

**SUGGESTION:** Contributing sections in deeply nested READMEs are often redundant.

```markdown
<!-- BAD: Generic contributing guidelines in package subfolder -->
## Contributing

When adding new functions to `packaging_utils.py`:

1. Create a corresponding test class
2. Test both success and failure cases
3. Run all tests to ensure no regressions

<!-- This belongs in the project-level CONTRIBUTING.md or style guide -->
```

**Where contributing guidelines belong:**
- Project root `CONTRIBUTING.md`
- Style guides under `docs/development/style_guides/`
- Not in every subdirectory README

---

## Summary Checklist

**Before approving documentation PRs:**

- [ ] No specific counts, percentages, or version numbers that will go stale
- [ ] Not duplicating standard tool documentation (pytest, unittest, etc.)
- [ ] Documentation is in the appropriate location (not buried in subdirectory)
- [ ] Adds value beyond restating what the code does
- [ ] Links to authoritative sources instead of duplicating
- [ ] Contributing guidelines are in project-level docs, not scattered
