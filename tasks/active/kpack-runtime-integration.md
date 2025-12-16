---
repositories:
  - therock
  - rocm-kpack
---

# Kpack Runtime Integration

**Status:** In progress - Loader API complete, pending repo move and CLR integration

## Overview

This is the penultimate integration for kpack, focusing on working it into the runtime (clr) such that we can run key rocm examples with kpack splitting enabled in the build system. Since this may uncover work that we still have yet to do, we will be building out this runtime integration on a branch so that we can test locally/iterate, possibly over multiple tasks and review cycles. As such, we need to keep this task updated with all findings so that we can pick back up over extended interactions. Once we have landed runtime support, we will flip the `THEROCK_KPACK_SPLIT_ARTIFACTS` CMake flag and add rocm-kpack properly to the repos.

There are multiple branches involved in making this work, and I will be managing that as it is likely to change day by day. Ask if clarification is needed and work to keep patches to the submodules organized for easy cherry-picking. Instead of sending out a PR, we will be manually squashing and keeping some WIP branches in sync.

I can also help you in flipping components to debug builds, etc. Just ask as this is not well documented.

## Goals

- [x] Choose integration strategy (comgr, clr, etc).
- [ ] Code initial implementation
- [ ] Build the project with only RAND enabled (simplest of all ROCm libraries) and test.
- [ ] Stage all necessary PRs in component repositories.

## Context

### Background

The kpack build-time integration (completed in `integrate-kpack-split` task) produces split artifacts:
- **Host-only binaries**: `.so` files with device code sections zeroed, containing `.rocm_kpack_ref` marker
- **Kpack archives**: `.kpack` files with compressed device code organized by architecture family

At runtime, when a HIP application loads a split binary, the CLR needs to:
1. Detect that the binary uses kpack (vs embedded fat binary)
2. Locate the appropriate `.kpack` archive
3. Extract device code for the current GPU architecture
4. Load it into the HSA runtime as normal

### Related Work
- `/develop/rocm-kpack/docs/multi_arch_packaging_with_kpack.md`
- `/develop/rocm-kpack/docs/runtime_api.md`
- `tasks/completed/integrate-kpack-split.md`

---

## Design Document

### Architectural Principle: Complexity in Kpack, Not CLR

**Key Decision**: The kpack runtime library (`librocm_kpack.so`) handles all complexity. CLR remains thin.

**Rationale**:
- CLR is complex, fragile, and hard to unit test
- Kpack library can have robust, isolated tests
- Other runtimes (OpenCL, future) may need this feature
- Keeps CLR changes minimal and reviewable

### Current Code Object Loading Architecture

```
HIP Application
    │
    ▼
__hipRegisterFatBinary() / hipModuleLoad()
    │
    ▼
FatBinaryInfo::ExtractFatBinaryUsingCOMGR()   ◄── INTEGRATION POINT
    │                                              hip_fatbin.cpp:391
    ├── Detects bundle format (magic bytes)
    ├── Queries ISA list for current devices
    ├── Calls amd::Comgr::lookup_code_object()
    │
    ▼
AddDevProgram()                                    Per-device code objects
    │
    ▼
Program::setKernels()                              rocprogram.cpp:236
    │
    ├── hsa_code_object_reader_create_from_memory()
    ├── hsa_executable_load_agent_code_object()
    └── hsa_executable_freeze()
```

### HIPK Data Structure

Split binaries are identified by magic byte change in `__CudaFatBinaryWrapper`:

```c
struct __CudaFatBinaryWrapper {
    uint32_t magic;       // HIPF (0x48495046) → HIPK (0x4B504948)
    uint32_t version;     // 1
    void* binary;         // Points to MessagePack metadata (NOT fat binary data)
    void* reserved1;
};
```

**Critical insight**: When magic is `HIPK`, the `binary` pointer is **redirected** to point at the mapped `.rocm_kpack_ref` section. No ELF section parsing needed at runtime - just dereference the pointer to get MessagePack data:

```
{
  "kernel_name": "lib/librocrand.so.1",      // TOC lookup key
  "kpack_search_paths": [
    "../.kpack/rocm-gfx1100.kpack",          // Relative to binary
    "../.kpack/rocm-gfx1200.kpack"
  ]
}
```

### Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLR (hip_fatbin.cpp)                     │
│                                                                 │
│  // In ExtractFatBinaryUsingCOMGR() or similar:                 │
│  if (IsHipkMagic(wrapper->magic)) {                             │
│      // Get binary path (CLR already has this in fname_)        │
│      // Or use: kpack_discover_binary_path(wrapper->binary,...) │
│                                                                 │
│      for (auto& device : devices) {                             │
│          // Build arch list using existing CLR logic            │
│          std::string native = device->isa().isaName();          │
│          std::string generic = TargetToGeneric(native);         │
│          const char* arch_list[] = { native.c_str(),            │
│                                       generic.c_str() };        │
│                                                                 │
│          void* code_obj; size_t size;                           │
│          auto err = kpack_load_code_object(                     │
│              wrapper->binary,           // msgpack metadata     │
│              fname_.c_str(),            // binary path          │
│              arch_list, 2,              // archs + count        │
│              &code_obj, &size);                                 │
│          if (err != KPACK_OK) return hipErrorNoBinaryForGpu;    │
│          AddDevProgram(device, code_obj, size, 0);              │
│          kpack_free_code_object(code_obj);                      │
│      }                                                          │
│      return hipSuccess;                                         │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              librocm_kpack.so - High-Level API (NEW)            │
│                                                                 │
│  kpack_discover_binary_path():                                  │
│    - Linux: /proc/self/maps parsing                             │
│    - Windows: GetModuleHandleEx + GetModuleFileName             │
│                                                                 │
│  kpack_load_code_object(metadata, path, archs, count, ...):     │
│    1. Parse msgpack from hipk_metadata                          │
│    2. Check env vars (ROCM_KPACK_PATH override, etc)            │
│    3. Resolve search paths relative to binary_path              │
│    4. Iterate search paths, open first valid archive            │
│    5. Iterate arch_list[0..count), return first match           │
│    6. Return code object bytes (caller frees)                   │
│    7. KPACK_ERROR_ARCH_NOT_FOUND if no match                    │
│                                                                 │
│  kpack_enumerate_architectures(path, callback, user_data):      │
│    - Callback-based enumeration for introspection               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              librocm_kpack.so - Low-Level API (existing)        │
│                                                                 │
│  kpack_open() / kpack_get_kernel() / kpack_close()              │
└─────────────────────────────────────────────────────────────────┘
```

### High-Level API Surface (NEW)

```c
//=============================================================================
// Path Discovery
//=============================================================================

// Resolve address in a loaded binary to its file path
// Works on Linux (/proc/self/maps) and Windows (GetModuleHandleEx)
kpack_error_t kpack_discover_binary_path(
    const void* address_in_binary,   // any address mapped from the .so/.dll
    char* path_out,                  // buffer
    size_t path_out_size,
    size_t* offset_out               // optional: offset within file
);

//=============================================================================
// Archive Cache (WIP - defer to later iteration)
//=============================================================================
//
// Design TBD. Initial integration will work without caching.
//
// Notes for future design:
// - Should be an explicit object (kpack_cache_t*) not process-wide static
// - Enables unit testing with sanitizers, multiple isolated caches
// - kpack_load_code_object() would take optional cache pointer
// - May be more of a "map of seen archives" than LRU cache
//   (matches current behavior where all kernels are mmap'd)
// - Consider: kpack_cache_create() / kpack_cache_destroy()
//

//=============================================================================
// Code Object Loading
//=============================================================================

// Callback for architecture enumeration
typedef bool (*kpack_arch_callback_t)(
    const char* arch,          // architecture string (valid only during callback)
    void* user_data
);

// Main entry point for loading code objects
// Returns first matching architecture from the priority list, or KPACK_ERROR_ARCH_NOT_FOUND
kpack_error_t kpack_load_code_object(
    const void* hipk_metadata,       // wrapper->binary (msgpack data)
    const char* binary_path,         // path to .so/.dll (required)
    const char* const* arch_list,    // array of ISAs in priority order
    size_t arch_count,               // number of entries in arch_list
    void** code_object_out,          // caller must free via kpack_free_code_object
    size_t* code_object_size_out     // size of returned code object in bytes
);

// Cleanup loaded code object
void kpack_free_code_object(void* code_object);

//=============================================================================
// Introspection (debugging/diagnostics)
//=============================================================================

// Enumerate architectures available in an archive
// Callback invoked for each architecture; return false to stop enumeration
kpack_error_t kpack_enumerate_architectures(
    const char* archive_path,
    kpack_arch_callback_t callback,
    void* user_data
);
```

**Key design choices**:
1. CLR passes the architecture priority list (xnack/sramecc/generic logic stays in CLR)
2. Explicit array + count instead of NULL-terminated list (safer)
3. Returns **single** code object (first match) or `KPACK_ERROR_ARCH_NOT_FOUND`
4. Callback/enumerate pattern for variable-length results (simpler memory ownership)
5. Cache design deferred - initial integration works without it

### Environment Variables for Serviceability

| Variable | Purpose |
|----------|---------|
| `ROCM_KPACK_PATH` | Override search paths entirely (colon-separated on Linux, semicolon on Windows) |
| `ROCM_KPACK_PATH_PREFIX` | Prepend additional paths to search (for debugging/development) |
| `ROCM_KPACK_DEBUG` | Enable verbose logging of path resolution and archive loading |
| `ROCM_KPACK_ARCH_OVERRIDE` | Force loading specific architecture (debugging) |
| `ROCM_KPACK_DISABLE` | If set, fail immediately on HIPK binaries (escape hatch) |

### Files to Modify

| Repository | File | Changes |
|------------|------|---------|
| rocm-kpack | `runtime/include/rocm_kpack/kpack.h` | Add high-level API declarations |
| rocm-kpack | `runtime/src/high_level.cpp` | Implement high-level API (NEW) |
| rocm-kpack | `runtime/src/path_resolution.cpp` | Platform-specific path discovery (NEW) |
| rocm-kpack | `runtime/src/msgpack_parser.cpp` | Parse HIPK metadata (NEW) |
| rocm-kpack | `runtime/CMakeLists.txt` | Add new sources |
| clr | `hipamd/src/hip_fatbin.cpp` | Add HIPK detection, call kpack API |
| clr | `hipamd/CMakeLists.txt` | Link against librocm_kpack |

---

## Design Decisions

### Decision 1: Where Complexity Lives

**Decision**: Kpack library owns all complexity. CLR just detects HIPK and calls one function.

**Rationale**:
- CLR is complex, fragile, hard to test
- Kpack library can be unit tested in isolation
- Other runtimes may want kpack support
- Minimal CLR diff = easier review

**Alternatives Considered**:

| Alternative | Why Rejected |
|-------------|--------------|
| All logic in CLR | Hard to test, CLR already complex, other runtimes can't reuse |
| Split between CLR and kpack | Unclear ownership, harder to debug |

### Decision 2: Binary Path Discovery Mechanism

**Decision**: Use `/proc/self/maps` parsing on Linux, `GetModuleHandleEx` on Windows.

**Rationale** (investigated in detail):

| Mechanism | Works for Fat Binary Data? | Why |
|-----------|---------------------------|-----|
| `dladdr()` | **No** | Only works for symbols (functions/variables), not data sections |
| `dl_iterate_phdr()` | **No** | Only sees dynamically loaded ELFs; fat binary data is embedded in executable, not a separate .so |
| `/proc/self/maps` | **Yes** | Sees ALL memory mappings including embedded data sections |

This is **technical necessity**, not legacy copy-paste. Fat binary data is embedded in executables/libraries as data, not loaded as separate shared objects. Only `/proc/self/maps` (Linux) provides a complete view of all memory mappings.

**Evidence**: CLR already uses `/proc/self/maps` in `amd::Os::FindFileNameFromAddress()` (os_posix.cpp:764-807) for exactly this purpose.

**Windows**: `GetModuleHandleEx(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS, ...)` + `GetModuleFileName()` - already used elsewhere in CLR (os_win32.cpp:687-696).

**Windows Deep-Dive Confirmation** (2025-12-15):
- `GetModuleHandleEx` works for **ANY address in a module**, not just code/symbols
- Works for .text, .data, .rdata, and custom sections (like `.rocm_kpack_ref`)
- Handles ASLR correctly (uses runtime addresses, not hardcoded)
- `Os::FindFileNameFromAddress()` on Windows is currently a **STUB** (returns false) - needs implementation
- Implementation pattern is clear and already used in CLR for similar purposes
- **Confidence: HIGH** - proceed with this approach

### Decision 3: Path Resolution Strategy

**Decision**: Paths in metadata are relative to binary location. Environment variables can override.

**Resolution order**:
1. If `ROCM_KPACK_PATH` set → use it exclusively
2. If `ROCM_KPACK_PATH_PREFIX` set → prepend to embedded paths
3. Otherwise → resolve embedded paths relative to binary directory

**Example**:
```
Binary at: /opt/rocm/lib/librocrand.so.1
Metadata contains: "../.kpack/rocm-gfx1100.kpack"
Resolved: /opt/rocm/.kpack/rocm-gfx1100.kpack
```

### Decision 4: Architecture Matching Strategy

**Decision**: CLR passes architecture priority list to kpack. Kpack iterates the list and returns first match.

**Rationale**: Architecture matching in CLR is complex and already implemented:
- xnack+/- feature flags require **exact matching** (gfx90a:xnack+ ≠ gfx90a:xnack-)
- Code objects without xnack specification are **wildcards** (work with any device setting)
- Same rules apply for sramecc
- Priority order: Native ISA → Generic ISA → SPIRV (kpack doesn't handle SPIRV)
- Generic mappings are defined in CLR (gfx1100 → gfx11-generic, etc.)

**CLR's existing logic** (hip_fatbin.cpp:444-458, hip_comgr_helper.cpp:109-158):
1. Gets device ISA name with features: `amdgcn-amd-amdhsa--gfx1100:xnack+`
2. Maps to generic: `amdgcn-amd-amdhsa--gfx11-generic:xnack+` (preserves features)
3. Builds query list: [native, generic, spirv...]
4. For each match, validates xnack/sramecc compatibility

**Example arch_list passed to kpack**:
```c
const char* arch_list[] = {
    "amdgcn-amd-amdhsa--gfx1100:xnack+",      // Native (highest priority)
    "amdgcn-amd-amdhsa--gfx11-generic:xnack+", // Generic fallback
    NULL
};
```

**Kpack's responsibility**: Iterate list, find first architecture present in archive TOC, return that code object.

**Override**: `ROCM_KPACK_ARCH_OVERRIDE` env var forces specific arch (debugging).

**Alternatives Considered**:

| Alternative | Why Rejected |
|-------------|--------------|
| Kpack implements full matching logic | Duplicates complex CLR code, must stay in sync, error-prone |
| Single arch with kpack fallback | Loses feature flag handling, xnack mismatches would be silent |

### Decision 5: Error Handling

**Decision**: Fail-fast with detailed error messages.

**Error cases**:
- HIPK magic but invalid msgpack → `KPACK_ERROR_INVALID_METADATA`
- Binary path discovery failed → `KPACK_ERROR_PATH_DISCOVERY_FAILED`
- No archive found at any search path → `KPACK_ERROR_ARCHIVE_NOT_FOUND`
- Architecture not available (after fallbacks) → `KPACK_ERROR_ARCH_NOT_FOUND`
- Archive corrupt/decompression failed → `KPACK_ERROR_CORRUPT_ARCHIVE`

When `ROCM_KPACK_DEBUG` is set, log detailed information about:
- Which paths were searched
- Which archives were tried
- What architectures were available vs requested

### Decision 6: Linking Strategy

**Decision**: Direct linking initially. Can add dlopen later if needed.

**Rationale**:
- Simpler implementation
- Compile-time errors are easier to debug
- kpack library is small, dependency cost is low
- If HIPK binaries are deployed, kpack library will be present

### Decision 7: Windows Support

**Decision**: Design for cross-platform, implement Linux first, document Windows approach.

**Windows implementation path** (documented but not initially implemented):
- Path discovery: `GetModuleHandleEx(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS, ...)` + `GetModuleFileName()`
- Path separator: semicolon for env vars, backslash for paths
- `/proc/self/maps` equivalent: `VirtualQuery()` can provide similar info if needed

**Confidence**: High - the Windows APIs are well-documented and already used elsewhere in CLR.

---

## Open Questions

### Resolved

1. ~~**CLR's `fname_` availability**~~: **RESOLVED** - CLR passes binary_path; kpack provides `kpack_discover_binary_path()` helper if CLR needs it. No "hint" mechanism - path is required.

2. ~~**Architecture fallback logic location**~~: **RESOLVED** - CLR passes priority list of architectures. Kpack iterates and returns first match. Keeps xnack/sramecc complexity in CLR.

3. ~~**Windows path discovery confidence**~~: **RESOLVED** - High confidence. `GetModuleHandleEx` works for any address in module. `Os::FindFileNameFromAddress()` is a stub that needs implementation.

### Still Open / Deferred

4. **Multi-GPU with different arch families**: System has gfx1100 and gfx1200. CLR loops per-device, each call may hit different archives. Initial integration will re-open archives each call; caching deferred.

5. **Archive caching strategy**: **DEFERRED** - Initial integration works without caching.
   - Future design notes captured in API section
   - Should be explicit object (`kpack_cache_t*`), not process-wide static
   - Enables unit testing with sanitizers
   - May be more "map of seen archives" than LRU cache

6. **Thread safety**: Without cache, each call is independent. Once cache is added, it will need mutex protection. Initial integration is inherently thread-safe (no shared state).

### Resolved

7. ~~**Memory ownership**~~: **RESOLVED** - kpack allocates, caller frees via `kpack_free_code_object()`. Clear and matches low-level API pattern.

8. ~~**API style**~~: **RESOLVED** - Array+count (not NULL-terminated), callback/enumerate for variable results.

---

## Investigation Notes

### 2025-12-15 - Initial Investigation

**Code object loading path traced**:
- Entry: `__hipRegisterFatBinary()` or `hipModuleLoad()`
- Key file: `/develop/therock/external/clr/hipamd/src/hip_fatbin.cpp`
- Integration point: `FatBinaryInfo::ExtractFatBinaryUsingCOMGR()` at line 391
- ISA selection: Lines 444-458, uses `TargetToGeneric()` for fallbacks
- COMGR lookup: Line 370, `amd::Comgr::lookup_code_object()`

**Kpack runtime API reviewed**:
- Thread-safe C API in `librocm_kpack.so`
- Key functions: `kpack_open()`, `kpack_get_kernel()`, `kpack_close()`
- Returns decompressed kernel bytes + size
- Caller must free with `kpack_free_kernel()`

**COMGR role clarified**:
- Primarily compile-time (source→executable)
- Runtime use limited to bundle parsing via `amd_comgr_lookup_code_object()`
- Not the right layer for kpack - would conflate compilation with runtime I/O

**Note**: COMGR could potentially be taught about kpack archives in the future if there's organizational preference for centralizing binary format handling. The current design keeps kpack as a separate library for cleaner separation of concerns and easier testing, but this is a reversible decision.

### 2025-12-15 - HIPK Structure Deep Dive

**Key finding**: `wrapper->binary` pointer is redirected at build time to point at mapped `.rocm_kpack_ref` section. No ELF parsing needed at runtime - just dereference and parse msgpack.

**Build-time transformation**:
1. `.rocm_kpack_ref` section added with msgpack data
2. Section mapped to PT_LOAD segment (SHF_ALLOC set)
3. `wrapper->binary` pointer updated to point at this section's virtual address
4. Magic changed from HIPF to HIPK

### 2025-12-15 - Address Resolution Research

**Investigated three mechanisms**:

1. **dladdr()**: Fast, but only works for symbols. Fat binary data has no symbols. **Not suitable.**

2. **dl_iterate_phdr()**: Iterates loaded ELFs, but fat binary data is embedded in executable data section, not loaded as separate shared object. **Not suitable.**

3. **/proc/self/maps**: Parses all memory mappings. Only option that sees embedded data. **Correct choice.**

**Historical context from ROCR-Runtime**:
- June 2020: Added `dl_iterate_phdr` as default, `/proc/self/maps` as fallback via `HSA_LOADER_ENABLE_MMAP_URI=1`
- Reason: `dl_iterate_phdr` is faster but doesn't see all mappings
- CLR independently chose `/proc/self/maps` for fat binary case (Aug 2021)

**Conclusion**: This is technical necessity, not legacy code. Different mechanisms solve different problems.

### 2025-12-15 - Windows Address Resolution Deep-Dive

**Investigated**: Can we reliably map address → DLL path on Windows?

**Answer**: YES, with high confidence.

**Mechanism**: `GetModuleHandleEx(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS, ...)` + `GetModuleFileName()`

**Key findings**:
- Works for **ANY address** in a loaded module (not just code/symbols)
- Tested sections: .text ✓, .data ✓, .rdata ✓, custom sections ✓
- Handles ASLR correctly (uses runtime addresses)
- Already used in CLR for similar purposes (os_win32.cpp:687-696)
- `Os::FindFileNameFromAddress()` on Windows is currently a STUB - needs implementation

**Implementation pattern**:
```cpp
HMODULE hm = NULL;
if (GetModuleHandleExA(
    GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
    (LPCSTR)address, &hm)) {
    char path[MAX_PATH];
    GetModuleFileNameA(hm, path, sizeof(path));
    // path now contains DLL/EXE path
}
```

**Edge cases handled**: Delay-loaded DLLs (fails gracefully if not loaded), heap addresses (returns false), NULL (returns false).

### 2025-12-15 - CLR Architecture Matching Deep-Dive

**Investigated**: How does CLR handle ISA matching, especially xnack+/- and generic architectures?

**Key findings**:

1. **TargetToGeneric()** (hip_fatbin.cpp:153-177):
   - Strips ISA name, maps to generic (e.g., gfx1100 → gfx11-generic)
   - **Preserves feature flags** (xnack, sramecc)

2. **xnack/sramecc matching rules** (hip_comgr_helper.cpp:109-158):
   - If code object specifies `xnack+` or `xnack-`: **MUST match device exactly**
   - If code object has no xnack: compatible with ANY device setting (wildcard)
   - Same rules for sramecc

3. **Query list construction** (hip_fatbin.cpp:444-458):
   - Device ISA: `amdgcn-amd-amdhsa--gfx1100:xnack+`
   - Generic: `amdgcn-amd-amdhsa--gfx11-generic:xnack+`
   - SPIRV fallback (not relevant for kpack)

4. **Priority order**: Native ISA > Generic ISA > SPIRV

**Implication**: CLR owns this complexity. Kpack receives a priority-ordered arch list and returns first match.

**Note**: Kpack will handle SPIRV in the future (JIT compilation path). For initial integration, SPIRV falls through to CLR's existing COMGR-based JIT.

---

## Test Hardening Plan

### Current Coverage (2025-12-15)

| File | Line Coverage | Notes |
|------|--------------|-------|
| toc_parser.cpp | 91.86% | Excellent |
| loader.cpp | 87.21% | Good, some error paths untested |
| compression.cpp | 77.42% | Missing error path tests |
| archive.cpp | 75.00% | I/O error handling untested |
| kpack.cpp | 75.00% | **`kpack_get_binary()` is 0% tested** |
| path_resolution.cpp | 70.31% | Parsing edge cases untested |

### Priority 1: Critical Gaps

#### 1.1 Untested API Functions
- `kpack_get_binary()` - 0% coverage, completely untested

#### 1.2 Thread Safety Tests
API claims thread safety but has zero concurrent tests:
- `kpack_get_kernel()` - "Thread-safe when called concurrently on SAME archive"
- `kpack_load_code_object()` - "Thread-safe with same cache from multiple threads"

Tests needed:
- [ ] ConcurrentGetKernel - Multiple threads calling kpack_get_kernel()
- [ ] ConcurrentLoadCodeObject - Multiple threads loading code objects
- [ ] ConcurrentArchiveCaching - Race to cache same archive

#### 1.3 Invalid Archive Format Tests
- [ ] InvalidMagic - Wrong magic bytes ("XXXX" instead of "KPAK")
- [ ] UnsupportedVersion - Valid magic but version=999
- [ ] TruncatedHeader - File with only partial header
- [ ] TruncatedTOC - Valid header but file shorter than TOC offset
- [ ] EmptyFile - 0-byte file

#### 1.4 Msgpack Parsing Edge Cases
- [ ] HIPKMetadataMissingKernelName - Missing required field
- [ ] HIPKMetadataMissingSearchPaths - Missing required field
- [ ] HIPKMetadataEmptySearchPaths - Empty array
- [ ] HIPKMetadataWrongTypes - Wrong types for fields

### Priority 2: Important Gaps

#### 2.1 Boundary Conditions
- [ ] GetArchitectureBoundary - Index at N-1 (valid) and N (invalid)
- [ ] GetBinaryBoundary - Same for binaries
- [ ] EmptyArchive - Archive with zero kernels
- [ ] ManyArchitectures - 20+ architectures in priority list

#### 2.2 Environment Variable Edge Cases
- [ ] EnvPathWithEmptyComponents - "path1::path2"
- [ ] EnvPathWithTrailingColon - "path1:path2:"
- [ ] DisableEnvWithZero - ROCM_KPACK_DISABLE="0"
- [ ] PathOverrideSupersededPrefix - Both PATH and PATH_PREFIX set

#### 2.3 Path Discovery Edge Cases
- [ ] DiscoverBinaryPath_AnonymousMmap - Address in mmap'd region
- [ ] DiscoverBinaryPath_PathWithSpaces - "/path with spaces/lib.so"

### Implementation Status

- [x] ASAN build passes (67/67 tests, no memory errors)
- [x] Thread safety tests (3 tests: concurrent load, caching, get_kernel)
- [x] Invalid format tests (5 tests: empty, wrong magic, bad version, truncated, bad offset)
- [x] Msgpack edge case tests (6 tests: missing/wrong type fields)
- [x] Boundary condition tests (kpack_get_binary/architecture index boundary)
- [x] Environment variable edge case tests (5 tests: empty components, trailing colon, disable with 0/empty, prefix with override)

---

## Code Changes

### Commit
`ae4f1c2` Add kpack loader API with comprehensive test coverage

### Files Modified (14 files, +2461/-35)
- `runtime/src/loader.cpp` - NEW: Loader implementation (474 lines)
- `runtime/src/path_resolution.cpp` - NEW: /proc/self/maps parsing (193 lines)
- `runtime/tests/test_loader_api.cpp` - NEW: Comprehensive loader tests (1158 lines)
- `runtime/include/rocm_kpack/kpack.h` - Added loader API declarations
- `runtime/include/rocm_kpack/kpack_types.h` - Added new error codes
- `runtime/src/kpack_internal.h` - Added kpack_cache struct
- `runtime/src/toc_parser.cpp` - Added bounds check for toc_offset
- `runtime/src/archive.cpp` - Minor refactoring
- `runtime/src/compression.cpp` - Minor refactoring
- `runtime/src/kpack.cpp` - Minor refactoring
- `runtime/tests/test_archive_integration.cpp` - Added GetBinaryNames, thread safety tests
- `runtime/tests/test_kpack_api.cpp` - Added invalid format tests, boundary tests
- `runtime/tests/CMakeLists.txt` - Added test_loader_api.cpp
- `runtime/CMakeLists.txt` - Added new source files

### Testing Done
- All 67 tests pass with ASAN enabled
- Coverage analysis completed
- Thread safety verified with 8 threads × 50 iterations

---

## Blockers & Issues

### Active Blockers
None - loader API complete, ready for repo move and CLR integration.

### Resolved Issues
- Fixed C API exception propagation (toc_parser.cpp bounds check)
- Fixed TempFile race condition (mkstemp on POSIX, GetTempPath2W on Windows)

---

## Next Steps

### Completed
1. [x] Investigate binary path discovery mechanism in CLR
2. [x] Research dladdr vs dl_iterate_phdr vs /proc/self/maps
3. [x] Document high-level architecture (complexity in kpack, not CLR)
4. [x] Implement high-level API in rocm-kpack runtime library
5. [x] Add unit tests for path resolution and msgpack parsing
6. [x] Thread safety tests
7. [x] Invalid archive format tests
8. [x] HIPK metadata edge case tests

### Next (manual steps)
9. [ ] **Move rocm-kpack into rocm-systems** - Integrate as submodule or merge
10. [ ] **CLR integration** - Add HIPK detection + kpack_load_code_object call in hip_fatbin.cpp
11. [ ] Build with RAND enabled and test end-to-end
12. [ ] Windows support (documented approach, implement when needed)

---

## Completion Notes

<!-- Fill this in when task is done -->

### Summary
(Not yet complete)

### Lessons Learned
(Not yet complete)

### Follow-up Tasks
(Not yet complete)
