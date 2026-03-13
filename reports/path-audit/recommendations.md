# Path Audit: Recommended Fixes

Findings and recommended fix patterns from the path audit (2026-03-13).

## REC-1: Tensile/data file runtime discovery — silent fallback to hardcoded path

**Affected projects:** rocblas, hipblaslt, hipsparselt

**Pattern:** Libraries use `dladdr` or similar to locate themselves at runtime, then
resolve data files (Tensile libraries, .hsaco code objects, .dat files) relative to
the shared library path. If that relative discovery fails, they silently fall back to
a `#define`'d hardcoded path like `/opt/rocm/lib`.

**Instances:**

| Project | File | Hardcoded path | Data file |
|---------|------|----------------|-----------|
| rocblas | library/src/tensile_host.cpp:76 | `/opt/rocm/lib` (Linux), `C:/hipSDK/rocblas/bin` (Windows) | Tensile library |
| hipblaslt | library/src/amd_detail/rocblaslt/src/tensile_host.cpp:71 | `/opt/rocm/lib` | Tensile library |
| hipblaslt | library/src/amd_detail/rocblaslt/src/rocblaslt_transform.cpp:49-53 | `/opt/rocm/lib/hipblaslt/library/hipblasltTransform.hsaco` (Linux), `C:\opt\rocm\bin\hipblaslt\library\hipblasltTransform.hsaco` (Windows) | Transform code object |
| hipblaslt | library/src/amd_detail/hipblaslt-ext-op.cpp:116-117 | `/opt/rocm/lib/hipblaslt/library/hipblasltExtOpLibrary.dat` | ExtOp library |
| hipblaslt | library/src/amd_detail/rocblaslt/src/rocroller/custom_kernels.cpp:47-48 | `/opt/rocm/lib` | Custom kernels (static lib only) |
| hipsparselt | library/src/hcc_detail/rocsparselt/src/tensile_host.cpp:66 | `/opt/rocm/hipsparselt/lib` | Tensile library |
| hipsparselt | library/src/hcc_detail/rocsparselt/src/spmm/hip/kernel_launcher.cpp:52 | `/opt/rocm/hipsparselt/lib` | SpMM kernels |

**Why this is bad:**

- Silent fallback masks discovery failures. If relative path resolution breaks (e.g.
  due to static linking, unusual install layout, or packaging bugs), the library silently
  loads data from a system ROCm install — possibly a different version. This is both a
  correctness bug and a potential security issue.
- The Windows fallback paths (`C:\opt\rocm\...`, `C:/hipSDK/...`) are clearly untested
  — nothing installs to `C:\opt\rocm\` on Windows.
- Violates the side-by-side install requirement: if two ROCm versions are installed,
  a non-default install silently picks up data files from the default location.

**Recommended fix:**

- If relative path discovery (`rocblaslt_find_library_relative_path` / `dladdr`-based
  resolution) returns nullopt/fails, **log an error and fail** rather than falling back
  to a hardcoded path. The data files are required for correctness — loading the wrong
  version is worse than failing loudly.
- For the static library case (where `dladdr` can't locate the .so), the hardcoded
  default is the only option. Consider stamping the path at build time via a CMake
  `configure_file` instead of a source-level `#define`.
- The `rocblaslt_find_library_relative_path` utility in hipblaslt is the most robust
  version of this pattern. rocblas and hipsparselt use older, more manual approaches.
  Consider converging on a shared utility.

**Impact:** High — affects installed packages at runtime, not mitigated by TheRock
build-time defenses.

---

## REC-2: CMAKE_INSTALL_PREFIX FORCE

**Affected projects:** hipblas-common, hipblaslt, hipsparse, hipsparselt, rocwmma,
rocblas (next-cmake), plus Windows-only FORCE in hipblas, hipfft, hipsolver,
rocsolver, rocsparse, rocblas, rocfft

**Pattern:** `set(CMAKE_INSTALL_PREFIX "/opt/rocm" CACHE PATH "..." FORCE)` overrides
whatever install prefix is passed via `-DCMAKE_INSTALL_PREFIX=...` on the command line.

**Two variants:**

1. **Linux FORCE to /opt/rocm** (hipblas-common, hipblaslt, hipsparse, hipsparselt,
   rocwmma, rocblas/next-cmake): Always forces install prefix to /opt/rocm.
2. **Windows FORCE to C:/hipSDK** (hipblas, hipfft, hipsolver, rocsolver, rocsparse,
   rocblas, rocfft): Conditional on WIN32, forces install prefix to C:/hipSDK.

There's also a common `deps/CMakeLists.txt` pattern that FORCEs to the build-tree
package dir — this one is intentional and scoped to dependency builds.

**Recommended fix:**

- Remove the FORCE keyword. The default `/opt/rocm` is fine as a CACHE default (users
  who don't specify get a reasonable default), but FORCE prevents TheRock (or any
  integrator) from overriding it.
- TheRock already has a post-configure validation idea in the plan. Even without that,
  the dependency provider and CLI args should be sufficient if FORCE is removed.
- The `deps/CMakeLists.txt` FORCE is a different case — it's scoped to building
  vendored dependencies into a local prefix. Leave as-is or evaluate separately.

**Impact:** High for build correctness. Need to verify whether TheRock's current
approach survives FORCE (the CLI `-D` might re-apply each configure, but this is
CMake-version-dependent behavior).

---

## REC-3: find_package / find_program with PATHS /opt/rocm

**Affected projects:** Nearly all rocm-libraries and rocm-systems projects

**Pattern:** `find_package(hip REQUIRED CONFIG PATHS /opt/rocm/lib/cmake/hip/)` and
similar. These add `/opt/rocm` as a search hint, which can cause CMake to find a
system-installed package instead of the build-tree version.

**Why TheRock mostly survives this today:**

- TheRock's dependency provider intercepts `find_package` calls for known packages.
- TheRock unsets ROCM_PATH/HIP_PATH environment variables.
- TheRock sets CMAKE_PREFIX_PATH to point at the build tree.

**Recommended fix:**

- Remove `PATHS /opt/rocm/...` from find_package calls. For standalone builds,
  users should set `CMAKE_PREFIX_PATH=/opt/rocm` — this is standard CMake practice
  and handles all packages at once.
- This is high volume (~200+ sites) but low risk per change — the fix is mechanical.
- Batch by project, prioritize projects that TheRock's dependency provider doesn't
  fully cover.

**Impact:** Medium — mostly defended by TheRock today, but still wrong and creates
fragility.

---

## REC-4: Hardcoded paths in standalone build helpers

**Affected projects:** Nearly all (install.sh, rmake.py, toolchain-*.cmake)

**Pattern:** Standalone build scripts and toolchain files that hardcode `/opt/rocm`
as a default. These are used for building projects outside TheRock (e.g. developer
workflows, CI in individual repos).

**Recommended fix:**

- Low priority for TheRock — these files aren't used in TheRock builds.
- For individual project standalone builds, these defaults are arguably reasonable
  (user has ROCm installed at the default location).
- Fix opportunistically when touching a project for other reasons.

**Impact:** Low for TheRock. Relevant for standalone build correctness.
