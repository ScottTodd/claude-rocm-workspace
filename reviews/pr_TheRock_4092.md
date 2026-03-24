# PR Review: opencl ICD package as an artifact

* **PR:** [#4092](https://github.com/ROCm/TheRock/pull/4092)
* **Author:** agunashe
* **Reviewed:** 2026-03-24
* **Status:** OPEN
* **Base:** `main` ← `users/agunashe/opencl_icd_pkg_artifact`

---

## Summary

This PR creates a new `core-ocl-icd` artifact to package the OpenCL ICD
loader (e.g. `OpenCL.dll`) separately from the OpenCL runtime (`core-ocl`).
It adds a `BUILD_TOPOLOGY.toml` entry, a new artifact descriptor, and wraps
the existing `ocl-icd` subproject declaration inside the `THEROCK_ENABLE_OCL_RUNTIME`
guard (previously `ocl-icd` was activated unconditionally).

**Net changes:** +27 lines, -5 lines across 3 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** — The concept is reasonable, but there are
correctness issues with the feature flag wiring and the artifact descriptor
that need to be resolved before merge.

**Strengths:**
- Addresses a real packaging gap — the ICD loader was bundled into the
  OpenCL runtime and not independently distributable
- Small, focused change

**Blocking Issues:**
- Feature flag mismatch between topology and CMake
- Missing topology dependency from `core-ocl` to `core-ocl-icd`
- Incorrect component classification in artifact descriptor

---

## Detailed Review

### 1. BUILD_TOPOLOGY.toml — Feature flag mismatch

#### ❌ BLOCKING: `feature_name = "OCL_ICD"` is never checked in CMake

The topology entry declares `feature_name = "OCL_ICD"`, which generates
`THEROCK_ENABLE_OCL_ICD=ON` via `topology_to_cmake.py`. However, the CMake
code gates the ocl-icd subproject on `THEROCK_ENABLE_OCL_RUNTIME` (from
the `core-ocl` artifact), not `THEROCK_ENABLE_OCL_ICD`.

This means:
- If `core-ocl-icd` is requested **without** `core-ocl`, the feature flag
  `THEROCK_ENABLE_OCL_ICD` would be set but nothing would build because
  the guard is `if(THEROCK_ENABLE_OCL_RUNTIME)`.
- The generated CMake variable `THEROCK_ENABLE_OCL_ICD` is unused.

**Required action:** Either:
- **(a)** Use `feature_name = "OCL_RUNTIME"` for both topology entries (same
  feature flag controls both), OR
- **(b)** Add a separate `if(THEROCK_ENABLE_OCL_ICD)` guard for the ocl-icd
  subproject and `therock_provide_artifact(core-ocl-icd)` call, keeping
  `if(THEROCK_ENABLE_OCL_RUNTIME)` only for ocl-clr. Then have the `ocl-clr`
  section also check `THEROCK_ENABLE_OCL_ICD` or add `core-ocl-icd` as a dep.

Option (a) is simpler. Option (b) allows truly independent builds.

#### ❌ BLOCKING: Missing topology dependency — `core-ocl` → `core-ocl-icd`

In CMake, `ocl-clr` declares `ocl-icd` as a `RUNTIME_DEPS` (line 411).
But in `BUILD_TOPOLOGY.toml`, `core-ocl` does not list `core-ocl-icd` in
its `artifact_deps`. This means the topology-level dependency graph doesn't
reflect the CMake-level dependency.

If the two artifacts end up in different stages (or one is fetched as a
prebuilt), the dependency won't be resolved correctly.

**Required action:** Add `"core-ocl-icd"` to `core-ocl`'s `artifact_deps`:
```toml
[artifacts.core-ocl]
artifact_deps = ["core-runtime", "amd-llvm", "core-ocl-icd"]
```

### 2. core/artifact-core-ocl-icd.toml — Component semantics

#### ⚠️ IMPORTANT: `bin/**` should be in `run` component, not `lib`

The descriptor puts `bin/**` into the `lib` component:
```toml
[components.lib."core/ocl-icd/stage"]
include = [
  "bin/**",
]
```

Per the artifact system conventions (and consistent with `artifact-core-ocl.toml`),
`bin/**` belongs in the `run` component, not `lib`. The `lib` component is for
shared libraries (`lib/**`), config files, etc.

Compare `artifact-core-ocl.toml`:
```toml
[components.lib."core/ocl-clr/stage"]
include = ["etc/**"]
[components.run."core/ocl-clr/stage"]
include = ["bin/**"]
```

**Recommendation:** Fix component classification:
```toml
[components.run."core/ocl-icd/stage"]
include = [
  "bin/**",
]
```

And update the `therock_provide_artifact()` call to include `run` instead of
(or in addition to) `lib`:
```cmake
therock_provide_artifact(core-ocl-icd
  TARGET_NEUTRAL
  DESCRIPTOR artifact-core-ocl-icd.toml
  COMPONENTS
    run
  SUBPROJECT_DEPS
    ocl-icd
)
```

#### ⚠️ IMPORTANT: Descriptor may miss Linux shared libraries

The ICD loader installs `libOpenCL.so` (Linux) to `lib/` and `OpenCL.dll`
(Windows) to `bin/`. The current descriptor only captures `bin/**`, which
would package the Windows DLL but miss the Linux shared library.

The subproject's `INTERFACE_LINK_DIRS "lib"` confirms it installs to `lib/`.

**Recommendation:** Add a `lib` component for the shared library:
```toml
[components.lib."core/ocl-icd/stage"]
include = [
  "lib/**",
]
[components.run."core/ocl-icd/stage"]
include = [
  "bin/**",
]
```

### 3. core/CMakeLists.txt — Guard change

#### 💡 SUGGESTION: Verify the unconditional→conditional change is safe

On `main`, `ocl-icd` is activated unconditionally (outside any `if` guard).
This PR moves it inside `if(THEROCK_ENABLE_OCL_RUNTIME)`. Since `ocl-clr`
is the only consumer of `ocl-icd` and is already inside this guard, this
change is logically correct. However, if any other subproject has started
depending on `ocl-icd` without being behind `THEROCK_ENABLE_OCL_RUNTIME`,
this would break it.

This is likely fine, but worth a quick grep for `ocl-icd` in RUNTIME_DEPS
or BUILD_DEPS elsewhere.

### 4. CI Evidence

The CI run shows:
- All **build** jobs pass (Linux and Windows, all GPU families)
- All **artifact structure validation** jobs pass
- The one failure (`test_hip_printf` on gfx1151) is a pre-existing runtime
  test issue, unrelated to this PR
- Windows gfx110X tests all pass, including the sanity check

The artifact structure validation passing is a positive signal that the
new artifact is well-formed enough for the validation checks, though it
doesn't validate component semantics.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. Fix the feature flag mismatch: either use `feature_name = "OCL_RUNTIME"`
   or add proper `THEROCK_ENABLE_OCL_ICD` guards in CMake
2. Add `"core-ocl-icd"` to `core-ocl`'s `artifact_deps` in `BUILD_TOPOLOGY.toml`

### ✅ Recommended:

1. Fix component classification: `bin/**` → `run` component, add `lib/**` → `lib` component
2. Update `therock_provide_artifact()` COMPONENTS list to match descriptor

### 💡 Consider:

1. Verify no other subprojects depend on `ocl-icd` outside the `OCL_RUNTIME` guard
2. Check if `include/**` or `dev` component is needed for the ICD headers

---

## Testing Recommendations

- Verify the artifact contents on both Linux and Windows CI builds:
  list files in the `core-ocl-icd` artifact and confirm `OpenCL.dll` (Windows)
  and `libOpenCL.so` (Linux) are present
- Test building with `THEROCK_ENABLE_OCL_ICD=ON` and
  `THEROCK_ENABLE_OCL_RUNTIME=OFF` to verify the feature flag works independently

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The PR needs feature flag alignment between the topology and CMake, a
topology-level dependency addition, and artifact descriptor corrections.
The core idea is sound — splitting the ICD loader into its own artifact
is a reasonable packaging improvement.
