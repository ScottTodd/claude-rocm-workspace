# ROCm Directory Map

This document maps out where all ROCm-related directories live on this system.

**Update the paths below to match your actual setup.**

## Environment Setup

**Python Environment:** Claude Code is launched with the project venv already active (symlinked as `venv/` in this workspace). This venv contains required build tools including:
- meson (for building simde, libdrm, and other meson-based dependencies)
- Other Python dependencies from requirements.txt

## Repository Aliases

These aliases are used by `/stage-review` and other commands to resolve short names to paths.

| Alias | Path | Notes |
|-------|------|-------|
| therock | /develop/therock | Main ROCm build repo |
| rocm-kpack | /develop/rocm-kpack | Kernel packaging tools |
| jax | /develop/jax | JAX framework |
| xla | /develop/xla | XLA compiler |
| workspace | /home/stella/claude-rocm-workspace | This meta-workspace |

## Build Trees

### Active Builds
- **Main build:** `/develop/therock-build`
  - Configuration: Release
  - Target architecture: [gfx1201]
  - CMake flags:
  - Built ROCm installation is under `dist/rocm`
