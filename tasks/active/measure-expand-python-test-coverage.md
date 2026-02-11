# Measure and Expand Test Coverage for Python Scripts

**Status**: On hold — measurement infrastructure merged, coverage expansion available for others
**Priority**: Medium
**Created**: 2026-01-09
**Related**: `reports/python_audit_build_tools_2026-01-09.md`

---

## Overview

TheRock's `build_tools/` directory contains ~18,000 LOC across 105 Python files with only 16% test coverage. We need to:
1. Set up local coverage measurement tools
2. Establish baseline coverage metrics
3. Systematically add tests to critical untested code
4. Integrate coverage reporting into CI/CD

---

## Phase 0: Team Coordination (FIRST)

Before diving deep into implementation, get team buy-in and involvement:

- [x] **File GitHub issue** proposing coverage measurement for `build_tools/`
  - https://github.com/ROCm/TheRock/issues/3356
  - Reference the audit: `reports/python_audit_build_tools_2026-01-09.md`
  - Propose target metrics (e.g., 60% coverage for critical files)
  - Ask for input on CI integration approach (Codecov vs self-hosted)
  - Tag relevant team members for feedback
- [ ] Get consensus on approach before implementing CI integration

This avoids building infrastructure the team doesn't want or that conflicts with existing plans.

---

## Phase 1: Local Coverage Measurement ✅

**Merged**: PR #3359

### Running Coverage Locally

```bash
cd TheRock/build_tools
python -m pytest --cov --cov-report=term-missing --cov-report=html
# HTML report: ../build/coverage-html/index.html
# Data file: ../build/.coverage
```

Config lives in `build_tools/pyproject.toml`.

---

## Phase 2: Establish Baseline Metrics ✅

### Measured Baseline (2026-02-10)

- **Total statements**: 5,281
- **Covered**: 1,919 (36.34%)
- **Missed**: 3,362
- **Files with some coverage**: 27
- **Files at 0%**: 24 (1,968 statements)

### Files Currently WITH Tests

| File | LOC | Test File |
|------|-----|-----------|
| `_therock_utils/artifact_backend.py` | 233 | `artifact_backend_test.py` |
| `_therock_utils/artifacts.py` | 221 | `artifacts_test.py` |
| `_therock_utils/build_topology.py` | 510 | `build_topology_test.py` |
| `artifact_manager.py` | 689 | `artifact_manager_tool_test.py` |
| `compute_rocm_package_version.py` | 181 | `compute_rocm_package_version_test.py` |
| `fetch_artifacts.py` | 364 | `fetch_artifacts_test.py` |
| `fileset_tool.py` | 237 | `fileset_tool_test.py` |
| `setup_venv.py` | 230 | `setup_venv_test.py` |
| `github_actions/configure_ci.py` | 541 | `configure_ci_test.py` |
| `github_actions/configure_target_run.py` | 66 | `configure_target_run_test.py` |
| `github_actions/determine_version.py` | 59 | `determine_version_test.py` |
| `github_actions/fetch_package_targets.py` | 101 | `fetch_package_targets_test.py` |
| `github_actions/github_actions_utils.py` | 251 | `github_actions_utils_test.py` |
| `github_actions/python_to_cp_version.py` | 43 | `python_to_cp_version_test.py` |
| `packaging/promote_from_rc_to_final.py` | 275 | `promote_from_rc_to_final_test.py` |

### Target Metrics

**6-month goals**:
- Statement coverage: 25% → 60%
- File coverage: 16% → 60% (63/105 files)
- Critical file coverage: 0% → 100% (all Tier 1 files)

---

## Phase 3: Add Tests to Critical Files

### Tier 1: Critical Path (HIGHEST PRIORITY)

Files required for CI/CD and releases:

1. **`packaging/linux/build_package.py`** (768 LOC) - **MOST CRITICAL**
   - Package generation for DEB and RPM
   - Tests needed:
     - DEB package structure validation
     - RPM package structure validation
     - Metadata generation
     - File inclusion/exclusion rules
     - Version string handling

2. **`buildctl.py`** (328 LOC)
   - Core build control CLI
   - Tests needed:
     - Command parsing
     - Build orchestration
     - Error handling
     - Configuration validation

3. **`configure_stage.py`** (182 LOC)
   - Build stage configuration
   - Tests needed:
     - Stage parsing
     - Dependency resolution
     - Configuration validation

4. **`topology_to_cmake.py`** (277 LOC)
   - CMake generation from topology
   - Tests needed:
     - CMakeLists.txt generation
     - Dependency ordering
     - Variable substitution

5. **`install_rocm_from_artifacts.py`** (403 LOC)
   - ROCm installation from artifacts
   - Tests needed:
     - Installation workflow
     - File placement
     - Permission handling
     - Error recovery

6. **`packaging/upload_release_packages.py`** (353 LOC)
   - Release package uploads
   - Tests needed:
     - S3 upload workflow
     - Metadata generation
     - Error handling

### Tier 2: Core Infrastructure

7. **`_therock_utils/pattern_match.py`** (174 LOC)
   - Pattern matching core utility
   - Tests needed:
     - Glob pattern matching
     - Regex pattern matching
     - Edge cases

8. **`_therock_utils/py_packaging.py`** (448 LOC)
   - Python packaging utilities
   - Tests needed:
     - Package creation
     - Metadata generation
     - Dependency resolution

9. **`fetch_sources.py`** (452 LOC)
   - Source repository fetching
   - Tests needed:
     - Git operations
     - Submodule handling
     - Error recovery

10. **`github_actions/post_build_upload.py`** (280 LOC)
    - Post-build artifact uploads
    - Tests needed:
      - Artifact collection
      - Upload workflow
      - Failure handling

### Testing Strategy

For each file:
1. **Read the code** to understand functionality
2. **Identify critical paths** (main workflows)
3. **Identify edge cases** (error conditions, boundary cases)
4. **Write unit tests** for individual functions
5. **Write integration tests** for workflows
6. **Use mocks** for external dependencies (S3, subprocess, filesystem)
7. **Measure coverage** after each test addition

### Example Test Structure

```python
# build_tools/tests/test_buildctl.py
import pytest
from unittest.mock import Mock, patch
from build_tools.buildctl import BuildController, parse_args

class TestBuildctl:
    def test_parse_args_basic(self):
        """Test basic argument parsing."""
        args = parse_args(['--config', 'test.toml'])
        assert args.config == 'test.toml'

    def test_build_controller_init(self):
        """Test BuildController initialization."""
        controller = BuildController(config_path='test.toml')
        assert controller.config_path == 'test.toml'

    @patch('build_tools.buildctl.subprocess.run')
    def test_build_execution(self, mock_run):
        """Test build execution workflow."""
        mock_run.return_value = Mock(returncode=0)
        controller = BuildController(config_path='test.toml')
        result = controller.run_build()
        assert result == 0
        mock_run.assert_called_once()
```

---

## Phase 4: CI/CD Integration ✅

**Merged**: PR #3359

- `unit_tests.yml` runs `--cov --cov-report=term-missing --cov-report=html`
- HTML coverage report uploaded as GitHub artifact
- Also enforces `*_test.py` naming via pre-commit hook

### Future: Codecov or diff-cover

Evaluated `diff-cover` for PR-level diffs — markdown output wasn't useful enough (reverted).
Codecov would be the right tool for tracking trends and PR comments if the team wants it later.

---

## Useful Coverage Commands

### Run tests with coverage for specific module
```bash
python -m pytest \
  --cov=build_tools.artifact_manager \
  --cov-report=term-missing \
  build_tools/tests/artifact_manager_tool_test.py
```

### Show only files with <50% coverage
```bash
python -m pytest \
  --cov=build_tools \
  --cov-report=term-missing:skip-covered \
  build_tools/tests
```

### Generate coverage diff between runs
```bash
# First run
coverage run -m pytest build_tools/tests
coverage report > coverage_before.txt

# Add new tests
# ...

# Second run
coverage run -m pytest build_tools/tests
coverage report > coverage_after.txt

# Compare
diff coverage_before.txt coverage_after.txt
```

### Check coverage thresholds (fail if below threshold)
```bash
python -m pytest \
  --cov=build_tools \
  --cov-fail-under=60 \
  build_tools/tests
```

---

## Coverage Configuration File

Create `.coveragerc` in TheRock root for consistent coverage settings:

```ini
[run]
source = build_tools
omit =
    */tests/*
    */test_*.py
    */__pycache__/*
    */third_party/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
    @abstractmethod
precision = 2
skip_covered = False
sort = Cover

[html]
directory = build/coverage-html
```

---

## Files Requiring Refactoring BEFORE Testing

These files are too large (>500 LOC) and should be split before adding comprehensive tests:

1. **`hack/env_check/check_tools.py`** (1002 LOC)
   - Split into: compiler_checks.py, runtime_checks.py, cmake_checks.py

2. **`packaging/linux/build_package.py`** (768 LOC)
   - Split into: deb_builder.py, rpm_builder.py, package_validator.py

3. **`packaging/download_prerelease_packages.py`** (740 LOC)
   - Split into: package_downloader.py, url_resolver.py, package_validator.py

See `reports/python_audit_build_tools_2026-01-09.md` for full refactoring recommendations.

---

## Success Criteria

- [ ] pytest-cov installed and configured
- [ ] Baseline coverage measurement completed
- [ ] Coverage report generation working locally
- [ ] .coveragerc configuration file created
- [ ] Tier 1 files have >80% coverage (6 files)
- [ ] Tier 2 files have >70% coverage (4 files)
- [ ] Overall statement coverage >60%
- [ ] Coverage reports integrated into CI/CD
- [ ] Coverage trends tracked over time

---

## Notes

- Start with **local measurement** to understand current state
- Focus on **critical files first** (Tier 1)
- Use **HTML reports** for detailed analysis - they're invaluable for finding untested code paths
- **Mock external dependencies** (S3, subprocess, filesystem) for fast, reliable tests
- **Don't aim for 100%** - focus on critical paths and edge cases
- Some files (third_party/) may not need tests
- See the full audit report for detailed file-by-file analysis

---

## References

- Full audit: `reports/python_audit_build_tools_2026-01-09.md`
- pytest-cov docs: https://pytest-cov.readthedocs.io/
- coverage.py docs: https://coverage.readthedocs.io/
- Python Style Guide: `../TheRock/PYTHON-STYLE-GUIDE.md`
