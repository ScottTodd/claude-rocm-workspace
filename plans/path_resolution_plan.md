# Path Discovery: Resolution Plan (Discussion Draft)

Status: **Under discussion** — not approved for implementation.

Tracking issue: https://github.com/ROCm/TheRock/issues/3976

## Problem Summary

ROCm sub-projects have ~74 `PATHS /opt/rocm` call sites across rocm-systems
and rocm-libraries. TheRock papers over most of these during integrated builds,
but they cause real problems:

- **Build issues:** Sandbox escapes when host ROCm installs exist (#670, #683)
- **Install issues:** Broken HIP_PLATFORM detection in distributed packages (#1402)
- **Regression risk:** CMAKE_INSTALL_PREFIX FORCE bug (#340) was fixed but has
  no automated enforcement

## Bucket 1: Build Issues

Projects must build correctly regardless of host state (env vars, system paths).

### Scope

- ~74 `PATHS /opt/rocm` sites in find_package/find_program calls
- Toolchain files with `$ENV{ROCM_PATH}` → `/opt/rocm` fallback
- Python scripts with hardcoded paths

### Existing defenses (TheRock-side)

- CLI override: `-DCMAKE_INSTALL_PREFIX=<stage_dir>`
- Env unsetting: `cmake -E env --unset=ROCM_PATH/HIP_PATH/...`
- Dependency provider intercepts `find_package`
- Generated toolchain files (sub-project toolchains ignored)

### Fix approach

Remove `PATHS /opt/rocm` hints from find_* calls. For standalone builds,
users set `CMAKE_PREFIX_PATH=/opt/rocm` once — standard CMake discovery
handles the rest. Upstream PRs preferred over TheRock patches.

Toolchain files are lowest priority (TheRock doesn't use them).

## Bucket 2: Install Issues

Side-by-side installs must not conflict, even with env vars set.

### Scope

- `hip-config-amd.cmake.in`: `PATHS "/opt/rocm"` in `find_dependency` calls
- `HIPCC_BIN_DIR` defaults to `/opt/rocm/bin`
- PATH fallback via `find_program(hipconfig)` (rocm-systems PR #3150)

### Fix approach

- Remove PATHS hints from hip-config-amd.cmake.in (already has PACKAGE_PREFIX_DIR)
- Change HIPCC_BIN_DIR default from `/opt/rocm/bin` to empty or relative
- Revert or replace PATH fallback with relative path computation

## Possible Work Items

### Linter script

`build_tools/lint_cmake_paths.py` — regex-based, with allowlist for
known-acceptable sites.

Rules:
- B1-PATHS: `PATHS /opt/rocm` in find_* calls (ERROR)
- B1-FORCE-UNGUARDED: FORCE on CMAKE_INSTALL_PREFIX without guard (ERROR)
- B1-ENV-READ: `$ENV{ROCM_PATH|HIP_PATH|...}` (WARNING)
- B2-CONFIG-HARDCODED: `/opt/rocm` in config templates (ERROR)

Could wire into pre-commit to prevent new violations.

### Install relocatability tests

Extend `tests/test_artifact_structure.py`:
- Scan `*-config.cmake` in artifact archives for `/opt/rocm`
- Check for leaked build-tree absolute paths
- Runs on existing artifact test infrastructure, no GPU needed

### Post-configure validation

After sub-project configure, verify CMAKE_INSTALL_PREFIX in CMakeCache.txt
matches expected stage dir. ~5 lines in `therock_subproject.cmake`.

### Upstream cleanup PRs

Batched by project, in dependency order:
- Phase 1: hip-config-amd.cmake.in, HIPCC_BIN_DIR (highest impact)
- Phase 2a: rocm-systems (~20 sites)
- Phase 2b: rocm-libraries (~54 sites, heavy hitters: miopen, hipsolver, rocfft)
- Phase 2c: toolchain files (lowest priority)

## Related Issues & PRs

Known issues and PRs related to hardcoded path resolution across ROCm.

| Ref | Repo | Summary | Status |
|-----|------|---------|--------|
| [#670](https://github.com/ROCm/TheRock/issues/670) | TheRock | Sandbox escape when host ROCm exists | Closed (env unset workaround) |
| [#683](https://github.com/ROCm/TheRock/issues/683) | TheRock | Build issues with system ROCm installed | Closed |
| [#340](https://github.com/ROCm/TheRock/issues/340) | TheRock | CMAKE_INSTALL_PREFIX FORCE bug | Closed (fixed, no enforcement) |
| [#1200](https://github.com/ROCm/TheRock/issues/1200) | TheRock | hipcc uses system HIP_PATH over own install tree | Closed |
| [#1201](https://github.com/ROCm/TheRock/pull/1201) | TheRock | Patch hipcc to deprioritize HIP_PATH env var (Windows) | Merged |
| [#1402](https://github.com/ROCm/TheRock/issues/1402) | TheRock | Broken HIP_PLATFORM detection in distributed packages | Open |
| [#3825](https://github.com/ROCm/TheRock/pull/3825) | TheRock | Redirect ROCM_PATH/HIP_PATH to build tree (rejected approach) | Changes requested |
| [#289](https://github.com/ROCm/llvm-project/pull/289) | llvm-project | Upstream: deprioritize HIP_PATH in hipcc | Open |
| [#3880](https://github.com/ROCm/rocm-systems/pull/3880) | rocm-systems | hip-tests: remove /opt/rocm fallback for ROCM_PATH | Open |

### Key takeaways

- **#3825 was rejected** — the team consensus is to fix subprojects individually rather
  than papering over the problem at the TheRock super-project level. Subproject builds
  should be self-contained; env var redirects to `dist/rocm` don't work because each
  subproject's dist only contains its own dependency cone.
- **#3880 is the canonical example** of the fix pattern: remove the hardcoded fallback,
  let CMake discovery work via `CMAKE_PREFIX_PATH` set by TheRock.
- **#1201/#289** shows the same problem class in C++ tools (hipcc), not just CMake.

## Open Questions

- Who owns the upstream PRs? Some repos have different maintainers/review cycles.
- Should we file tracking issues in rocm-systems / rocm-libraries?
- Is a linter script worth building now, or should we focus on the highest-impact
  manual fixes first?
- How aggressive should the pre-commit hook be? (block vs warn)
- Should Phase 1 (install fixes) go through TheRock patches as a fast path
  while upstream PRs are in review?
