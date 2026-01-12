# PR Pattern Detection

This document maps common PR patterns to additional review criteria.
When a PR matches a pattern, apply the corresponding checks.

---

## How to Use This Document

1. **Identify PR patterns** from the title, description, and changed files
2. **Apply relevant guidelines** for each pattern detected
3. **Multiple patterns can apply** - a PR adding a dependency with tests triggers both patterns

---

## Pattern: Adds or Modifies Tests

### Detection

- Files changed in `test/`, `tests/`, or `*_test.py`, `test_*.py`
- PR title/description mentions "add tests", "test coverage", "fix test"
- New pytest/unittest/gtest files

### Additional Checks

Apply full [tests.md](tests.md) checklist, especially:

- [ ] Test duration included in PR description
- [ ] Test count included in PR description
- [ ] Local run instructions provided
- [ ] Tests are deterministic and independent

### Questions for PR Author

If not addressed in description:
- "How long do these tests take to run?"
- "Can these tests be run locally? If so, what's the command?"

---

## Pattern: Adds New Dependency or Subproject

### Detection

- Changes to `external/` directory (new submodule)
- New entries in CMakeLists.txt `add_subdirectory()` or `FetchContent`
- New `find_package()` calls
- Changes to requirements.txt, pyproject.toml, package.json

### Additional Checks

**PR description must include:**

| Metric | Where to Find |
|--------|---------------|
| Build time impact | CI logs before/after |
| Binary size impact | Build artifacts comparison |
| Packaging considerations | Note any special handling needed |

**Review questions:**
- [ ] Is this dependency necessary, or could existing deps solve the problem?
- [ ] Is the dependency actively maintained?
- [ ] What's the license? Is it compatible?
- [ ] Are there security implications?
- [ ] Does it work across all supported platforms?

**TheRock-specific:**
- Check `core/CMakeLists.txt` for how dependencies are integrated
- Review `docs/development/build_system.md` for dependency patterns
- Verify `THEROCK_ENABLE_*` flags if dependency is optional

### Questions for PR Author

If not addressed in description:
- "What's the build time impact of adding this dependency?"
- "Are there packaging considerations for this dependency?"
- "Why was this dependency chosen over alternatives?"

---

## Pattern: Build System Changes

### Detection

- Changes to `CMakeLists.txt` files
- Changes to `.cmake` files
- Changes to `meson.build`, `Makefile`, or similar
- Modifications to build scripts in `scripts/` or `tools/`

### Additional Checks

- [ ] Changes follow [CMake Style Guide](../../TheRock/docs/development/style_guides/cmake_style_guide.md)
- [ ] Tested with different configurations (`-DTHEROCK_ENABLE_*` variants)
- [ ] Works on supported platforms (Linux, Windows if applicable)
- [ ] Doesn't break incremental builds
- [ ] Target names follow project conventions

**TheRock-specific:**
- Super-project vs sub-project patterns (see `docs/development/build_system.md`)
- Check `core/CMakeLists.txt` for dependency management patterns

### Questions for PR Author

- "Was this tested with a clean build and an incremental build?"
- "Which `THEROCK_ENABLE_*` configurations were tested?"

---

## Pattern: Revert

### Detection

- PR title starts with "Revert"
- Commit message contains "This reverts commit"
- PR description mentions reverting

### Additional Checks

See [pr_hygiene.md](pr_hygiene.md#reverts) - **required in description:**

- [ ] What problem did the original PR cause?
- [ ] Evidence (error logs, test failures, user reports)
- [ ] Link to the original PR being reverted

### Questions for PR Author

- "What failure or issue triggered this revert?"
- "Is there a plan to fix and re-land, or is this a permanent revert?"

---

## Pattern: Roll-forward (Re-landing Reverted Changes)

### Detection

- PR description mentions "re-land", "roll forward", "retry"
- References a previously reverted PR
- Similar changes to a recently reverted commit

### Additional Checks

See [pr_hygiene.md](pr_hygiene.md#roll-forwards-re-landing-reverted-changes) - **required:**

- [ ] Link to original PR and revert PR
- [ ] What was wrong with the original approach?
- [ ] What changed to fix the issue?

### Questions for PR Author

- "What was fixed since the revert?"
- "How was the fix verified?"

---

## Pattern: Documentation Only

### Detection

- Only `.md` files changed
- Changes to `docs/` directory
- README updates

### Additional Checks

Apply [documentation.md](documentation.md) checklist (when created), including:

- [ ] Code blocks have syntax hints
- [ ] Links are valid and not broken
- [ ] Information density is appropriate
- [ ] Instructions are clear and actionable

**Reduced scrutiny for:**
- Test coverage (not applicable)
- Performance impact (not applicable)

---

## Pattern: CI/CD Changes

### Detection

- Changes to `.github/workflows/`
- Changes to CI configuration files
- New or modified GitHub Actions

### Additional Checks

- [ ] Follows [GitHub Actions Style Guide](../../TheRock/docs/development/style_guides/github_actions_style_guide.md)
- [ ] Permissions are minimal (prefer read-only where possible)
- [ ] No secrets exposed in logs
- [ ] Workflow triggers are appropriate
- [ ] Job dependencies are correct

**Security considerations:**
- [ ] Uses pinned action versions (not `@main` or `@latest`)
- [ ] Secrets use appropriate scoping
- [ ] No command injection vulnerabilities in dynamic inputs

### Questions for PR Author

- "Were these workflow changes tested on a branch first?"
- "Do any new secrets need to be configured?"

---

## Pattern: Python Code

### Detection

- Changes to `.py` files

### Additional Checks

- [ ] Follows [Python Style Guide](../../TheRock/docs/development/style_guides/python_style_guide.md)
- [ ] Type hints on public interfaces
- [ ] Uses `pathlib` for path operations
- [ ] Proper error handling (fail-fast, no silent failures)
- [ ] Uses dataclasses/attrs for data containers where appropriate

---

## Pattern: Bash/Shell Scripts

### Detection

- Changes to `.sh` files
- New scripts in `scripts/` or `tools/`

### Additional Checks

- [ ] Follows [Bash Style Guide](../../TheRock/docs/development/style_guides/bash_style_guide.md)
- [ ] Uses `set -euo pipefail` (or equivalent)
- [ ] Proper quoting of variables
- [ ] No command injection vulnerabilities
- [ ] Works on target platforms (bash version compatibility)

---

## Pattern: Security-Sensitive Changes

### Detection

- Changes to authentication/authorization code
- Changes to permission handling
- Changes to secret management
- Input validation changes
- File path handling
- Network request handling

### Additional Checks

Apply [security.md](security.md) checklist (when created), including:

- [ ] No hardcoded secrets
- [ ] Input validation at boundaries
- [ ] Path traversal prevention
- [ ] Command injection prevention
- [ ] Appropriate permission checks

---

## Pattern: Performance-Critical Changes

### Detection

- PR mentions "performance", "optimization", "speed"
- Changes to hot paths (identified by profiling)
- Algorithm changes
- Caching additions

### Additional Checks

**PR description should include:**
- Benchmark results (before/after)
- What was measured and how
- Test environment details

**Review questions:**
- [ ] Are performance claims backed by measurements?
- [ ] Could the change regress other scenarios?
- [ ] Is the optimization worth the complexity?

---

## Pattern Matrix

Quick reference for which guidelines to apply:

| PR Contains | Apply Guidelines |
|-------------|------------------|
| Test changes | pr_hygiene + tests |
| New dependency | pr_hygiene + architecture + security |
| Build changes | pr_hygiene + (project-specific patterns) |
| Revert | pr_hygiene (revert section) |
| Docs only | pr_hygiene (reduced) + documentation |
| CI changes | pr_hygiene + security |
| Python code | pr_hygiene + style |
| Shell scripts | pr_hygiene + style + security |
| Security-sensitive | pr_hygiene + security |
| Performance work | pr_hygiene + performance |

---

## Adding New Patterns

When you notice a recurring PR type that needs specific review criteria:

1. Add a new section with Detection rules
2. List Additional Checks specific to that pattern
3. Add Questions for PR Author to surface missing info
4. Update the Pattern Matrix
