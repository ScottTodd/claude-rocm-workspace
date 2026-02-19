# Task: Switch third-party subprojects to amd-llvm toolchain

## Goal

Switch all third-party subprojects (except sysdeps/) to build with the
`amd-llvm` COMPILER_TOOLCHAIN. This moves them after the compiler stage
in the build order and ensures consistent compilation across the project.

Related PR: #3440 (Reapply "Move non-sysdep third-party projects after base
and compiler")

## Status: Implementation in progress

Local build running to validate remaining subprojects.

## Subproject inventory

| Subproject | Upstream | Status | Notes |
|---|---|---|---|
| spdlog | spdlog 1.15.3 | **Done** (PR #3440) | |
| boost | Boost 1.87.0 | **Done** | |
| Catch2 | Catch2 3.8.1 | **Done** | |
| eigen | Eigen 3.4.0 | **Reverted** | Can't link to standard math library with clang (Windows) |
| fftw3 | FFTW 3.3.10 | **Done** | GPL-2.0+ — licensing review pending |
| flatbuffers | FlatBuffers 25.9.23 | **Done** | |
| fmt | fmt 11.1.3 | **Done** | |
| frugally-deep | frugally-deep 0.15.31 | **Done** | |
| FunctionalPlus | FunctionalPlus 0.2.25 | **Done** | |
| googletest | GoogleTest 1.16.0 | **Done** | |
| grpc | gRPC 1.67.1 | **Done** | |
| host-blas | OpenBLAS 0.3.30 | **Reverted** | lapack-netlib complex type errors with clang (Windows) |
| libdivide | libdivide 5.2.0 | **Done** | |
| msgpack-cxx | msgpack-c 7.0.0 | **Done** | |
| nlohmann-json | nlohmann/json 3.12.0 | **Done** | |
| simde | SIMDe 0.8.2 | **Done** | Header-only |
| SuiteSparse | SuiteSparse 7.8.3 | **Done** | LGPL — licensing review pending |
| yaml-cpp | yaml-cpp 0.8.0 | **Done** | |

### Build incompatibilities found

**eigen** — reverted to system toolchain. Eigen's CMake configure probes for
the standard math library (`-lm`) and fails with amd-llvm on Windows:
```
Performing Test standard_math_library_linked_to_automatically - Failed
Performing Test standard_math_library_linked_to_as_m - Failed
CMake Error: Can't link to the standard math library.
```

**host-blas (OpenBLAS)** — reverted to system toolchain. lapack-netlib has
C code that uses complex type expressions incompatible with clang on Windows:
```
lapack-netlib/INSTALL/second_INT_ETIME.c:30:64: error: invalid operands
to binary expression ('real' (aka 'float') and '_Fcomplex'
(aka 'struct _C_float_complex'))
```

### Licensing concerns (unchanged)

### Licensing concerns

**FFTW3** (GPL-2.0+):
- Pure GPL, no runtime library exception
- Question: does the GPL restrict which compiler toolchain can build it?
- The GPL itself does not restrict compiler choice — you can build GPL code
  with any compiler. The concern is about the GCC Runtime Library Exception
  on GCC's own runtime libraries (libgcc, libstdc++), not on FFTW itself.
- Need to verify: does building FFTW with clang change the runtime linking
  in a way that affects GPL compliance for downstream consumers?
- TODO: Research this thoroughly

**SuiteSparse** (mixed licenses per component):
- TheRock only builds: suitesparse_config + CHOLMOD (see CMakeLists.txt)
- CHOLMOD is LGPL-2.1+
- suitesparse_config is BSD-3-Clause
- LGPL allows building with any compiler — the requirement is about
  relinking, not compilation toolchain
- Likely fine but should confirm

**GCC Runtime Library Exception** (general concern):
- The exception in libgcc/libstdc++ allows combining GPL'd runtime code
  with non-GPL code when built by an "Eligible Compilation Process"
- LLVM/Clang is generally considered eligible (permissive license)
- This applies to the *runtime libraries*, not to the compiled software
- TODO: Confirm this understanding

## Implementation plan (pending licensing sign-off)

### Phase 1: Add COMPILER_TOOLCHAIN to each subproject

For each CMakeLists.txt under third-party/ (except sysdeps/), add:
```cmake
COMPILER_TOOLCHAIN
  amd-llvm
```
to the `therock_cmake_subproject_declare()` call.

### Phase 2: Add artifact_deps where missing

Each artifact that now depends on amd-llvm needs it in BUILD_TOPOLOGY.toml.
Currently spdlog already has `artifact_deps = ["amd-llvm"]`. All others
in the `third-party-libs` group have `artifact_deps = []`.

### Phase 3: Update downstream topology deps

Once all third-party-libs depend on amd-llvm, revisit the group structure:
- Consider splitting `third-party-libs` into `third-party-core` (CORE feature
  group: fmt, spdlog, flatbuffers, nlohmann-json) and `third-party-host-math`
  (HOST_MATH: host-blas, host-suite-sparse, fftw3)
- Downstream groups add `third-party-core` to `artifact_group_deps`
- See notes/spdlog-topology-deps.md for the full dependency map

### Phase 4: Guard add_subdirectory calls

Add `if(THEROCK_ENABLE_*)` guards for each third-party subproject (matching
the pattern already applied to spdlog in PR #3440).

## Notes

- Header-only libraries (simde, eigen, FunctionalPlus, frugally-deep,
  libdivide, nlohmann-json, msgpack-cxx) technically don't *need* a compiler
  toolchain since they aren't compiled, but setting it for consistency means
  they can be moved after compiler in the build order uniformly.
- Some header-only libs use `EXCLUDE_FROM_ALL` and may have test targets that
  do compile — the toolchain setting affects those.

## PR #3440 review feedback: sysdeps vs third-party-libs distinction

marbre commented that spdlog is in `third-party-libs` which "covers optional
deps" and suggested moving it to `third-party-sysdeps` if we want to pull it
in strictly. Scott pushed back, saying the "optional" label doesn't make sense
in this context and spdlog isn't a sysdep.

### Investigation: what actually distinguishes the two groups

The distinction is about **packaging behavior**, not build ordering or
optionality.

**Sysdeps** (`third-party/sysdeps/`):
- C libraries normally available from the OS package manager (zlib, zstd,
  elfutils, libdrm, numactl, hwloc, ncurses, gmp, mpfr, expat, etc.)
- Built with SONAME rewriting (`rocm_sysdeps_*` prefix), symbol versioning
  (`AMDROCM_SYSDEPS_1.0`), and installed into `lib/rocm_sysdeps/`
- Consumed via `THEROCK_BUNDLED_*` variables in `RUNTIME_DEPS` — variables
  are empty when bundling is disabled, so builds can use system copies
- Purpose: **portable distribution** — ship private copies so ROCm doesn't
  depend on exact system package versions
- Platform-specific (Linux has 15+ libs, Windows has only 4: bzip2, sqlite3,
  zlib, zstd)

**Third-party libs** (`third-party/` top-level):
- C++ libraries NOT typically available as OS packages (fmt, spdlog,
  flatbuffers, googletest, etc.)
- Built as normal CMake targets, consumed via `BUILD_DEPS` (`therock-spdlog`,
  `therock-fmt`, etc.)
- No SONAME rewriting or special install prefix
- Purpose: **build dependencies** that subprojects need to compile against
- Also includes the truly-optional `HOST_MATH` libs (host-blas, suite-sparse,
  fftw3) — these are the only ones that are actually "optional"

### The misleading `BUILD_TOPOLOGY.toml` description

`third-party-libs` is described as "Optional third-party libraries (for
tests/specific features)" but most of its contents (fmt, flatbuffers,
nlohmann-json, spdlog) are `feature_group = "CORE"` — NOT optional. Only the
HOST_MATH items (host-blas, host-suite-sparse, fftw3) are truly optional.

The staging (foundation vs compiler-runtime) is a consequence: sysdeps go in
foundation because the compiler needs some of them at runtime. But the driving
distinction is packaging behavior, not build stage.

### Who actually uses the sysdeps at runtime

| Sysdep | RUNTIME_DEPS consumers |
|--------|------------------------|
| zlib, zstd | compiler (amd-llvm), dctools |
| elfutils | compiler, core (ROCR-Runtime, hip-clr), profiler |
| libdrm | compiler, core (hsa-amdgpu, ROCR-Runtime, hip-clr), profiler |
| numactl | compiler, core (ROCR-Runtime, hip-clr) |
| sqlite3 | profiler |
| libcap | dctools (Linux-only) |
| hwloc | core (hip-clr tests) |
| gmp, mpfr, expat, ncurses | debug-tools (rocgdb) |

The compiler needs several sysdeps (zlib, zstd, elfutils, libdrm, numactl) but
that's not the reason they're sysdeps — they're sysdeps because they're system C
libraries that need special packaging treatment for portable distribution.

### Follow-up: documentation

The existing docs don't explain the sysdeps-vs-libs distinction:
- `third-party/sysdeps/linux/README.md` covers the packaging behavior (SONAME
  rewriting, symbol versioning, install prefix)
- `third-party/sysdeps/common/README.md` is one line
- `docs/development/dependencies.md` covers per-library find_package patterns
- No `third-party/sysdeps/README.md` exists at the directory level

TODO: Add a `third-party/sysdeps/README.md` explaining:
1. Why sysdeps are separate from other third-party deps (packaging behavior)
2. Point to `docs/development/dependencies.md` for per-library details
3. Point to `linux/README.md` for Linux-specific packaging details

Also consider fixing the `BUILD_TOPOLOGY.toml` description for
`third-party-libs` — something like "Third-party C++ build dependencies"
instead of "Optional third-party libraries (for tests/specific features)".

Blocked on branch availability — need to set up git worktrees to work on
docs in parallel with other branches.
