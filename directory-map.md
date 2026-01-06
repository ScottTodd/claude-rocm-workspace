# ROCm Directory Map

This document maps out where all ROCm-related directories live on this system.

**Update the paths below to match your actual setup.**

## Repository Aliases

These aliases are used by `/stage-review` and other commands to resolve short names to paths.

| Alias | Path | Notes |
|-------|------|-------|
| therock | D:/projects/TheRock | Main ROCm build repo |
| rocm-kpack | D:/projects/rocm-kpack | Kernel packaging tools |
| rocm-systems | D:/projects/TheRock/rocm-systems | ROCm Systems Superrepo (submodule)|
| rocm-libraries | D:/projects/TheRock/rocm-libraries | ROCm Libraris Superrepo (submodule) |
| workspace | D:/projects/claude-rocm-workspace | This meta-workspace |

## Build Trees

### Active Builds

- **Main build:** `D:/projects/TheRock/build`
  - Configuration: Release
  - Target architecture: [gfx1100]
  - CMake flags:
  - Built ROCm installation is under `dist/rocm`
