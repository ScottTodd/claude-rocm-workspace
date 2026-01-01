---
repositories:
  - therock
  - rocm-kpack
---

# Kpack Runtime Integration

**Status:** In progress - Multi-TU POC complete, ELF surgery refinements needed

## Overview

This is the penultimate integration for kpack, focusing on working it into the runtime (clr) such that we can run key rocm examples with kpack splitting enabled in the build system. Since this may uncover work that we still have yet to do, we will be building out this runtime integration on a branch so that we can test locally/iterate, possibly over multiple tasks and review cycles. As such, we need to keep this task updated with all findings so that we can pick back up over extended interactions. Once we have landed runtime support, we will flip the `THEROCK_KPACK_SPLIT_ARTIFACTS` CMake flag and add rocm-kpack properly to the repos.

There are multiple branches involved in making this work, and I will be managing that as it is likely to change day by day. Ask if clarification is needed and work to keep patches to the submodules organized for easy cherry-picking. Instead of sending out a PR, we will be manually squashing and keeping some WIP branches in sync.

I can also help you in flipping components to debug builds, etc. Just ask as this is not well documented.

## Goals

- [x] Choose integration strategy (comgr, clr, etc).
- [x] Code initial implementation (kpack loader API complete in rocm-kpack)
- [x] Build the project with only RAND enabled (simplest of all ROCm libraries) and test.
  - Fixed two ELF surgery bugs in elf_modify_load.py:
    1. NOBITS segment offset collision (duplicate file offsets in LOAD segments)
    2. Off-by-one in min_content_offset check (program header overwrote .dynsym)
  - Library loads correctly, 28+ tests pass before needing device code
  - Device code tests fail as expected - CLR integration not yet implemented
- [x] CLR integration (HIPK detection + kpack loading)
  - HIPK detection in hip_code_object.cpp reads wrapper magic
  - Kpack loading via kpack_load_code_object() API
  - All 44 rocRAND tests pass with split artifacts
- [x] Multi-TU (RDC) bundle support - POC complete
  - rocRAND has 15 concatenated bundles in .hip_fatbin (one per TU)
  - Each wrapper now stores bundle index in reserved1 field
  - TOC uses indexed keys: `lib.so#0`, `lib.so#1`, etc.
  - Library size: 109MB (split) vs 201MB (unsplit)
- [ ] ELF surgery refinements (GDB warnings, stripping issues)
- [ ] Stage all necessary PRs in component repositories

## Current State Summary (2025-12-31)

**POC Complete**: Multi-TU kpack split works end-to-end with rocRAND.

**Branches**: Current state pushed to `users/stella/multi_arch_spike20251231` in:
- TheRock
- rocm-systems
- rocm-kpack

| Metric | Unsplit | Split | Notes |
|--------|---------|-------|-------|
| librocrand.so size | 201 MB | 109 MB | 46% reduction |
| Individual code object | 48 MB | 2.5 MB | Correct single-bundle size |
| Tests passing | 44/44 | 44/44 | All tests pass |

**Key architecture**:
- 15 `__hip_fatbin_wrapper` symbols, each with `reserved1 = bundle_index`
- TOC keys are indexed: `math-libs/.../librocrand.so.1.1#0` through `#14`
- Loader extracts `#N` from `binary_path` and appends to `kernel_name` for lookup

**Files modified across repositories**:

| Repository | File | Purpose |
|------------|------|---------|
| rocm-kpack | `python/rocm_kpack/elf_offload_kpacker.py` | Multi-TU detection, wrapper→bundle mapping, write bundle index to reserved1 |
| rocm-kpack | `python/rocm_kpack/artifact_splitter.py` | Always use indexed TOC keys (`#0`, `#1`, ...) |
| rocm-kpack | `runtime/src/loader.cpp` | Extract `#N` from binary_path, append to kernel_name for lookup |
| clr | `hipamd/src/hip_code_object.cpp` | Read bundle_index from wrapper->dummy1 |
| clr | `hipamd/src/hip_fatbin.hpp` | Add bundle_index constructor param and member |
| clr | `hipamd/src/hip_fatbin.cpp` | Store bundle_index, pass indexed path to kpack_load_code_object |

**Known issues** (ELF surgery refinements, not blocking):
1. GDB warnings about `.dynstr` section strings
2. `strip` corrupts the binary completely
3. Both indicate we're writing something slightly wrong during ELF modification

**Planned: ELF/COFF Surgery Rewrite**

Current `elf_modify_load.py` and `elf_offload_kpacker.py` have grown organically with many fixes. Before Windows port, do a clean rewrite:

1. **ElfSurgery class** - Dedicated abstraction that:
   - Maintains ELF invariants automatically (segment alignment, header space, section ordering)
   - Provides high-level operations: `add_mapped_section()`, `zero_region()`, `update_symbol()`
   - Handles program header table relocation cleanly
   - Tracks modifications and applies them atomically

2. **ElfVerifier** - Post-surgery validation that checks:
   - No overlapping segments with same file offset (caused our NOBITS bug)
   - Section/segment alignment constraints satisfied
   - String tables are valid (null-terminated, within bounds)
   - Symbol table entries point to valid sections
   - Relocations reference valid symbols
   - `readelf -a` and `objdump -x` produce no warnings
   - `strip` doesn't corrupt the binary
   - Debug data is sound: `gdb -batch -ex "info files" <binary>` produces no warnings
   - DWARF validation: `llvm-dwarfdump --verify` or `dwarfdump -V` if debug sections present

3. **COFFSurgery class** - Same pattern for Windows PE/COFF
   - Share interface where possible
   - Different invariants (PE sections, import tables, etc.)

4. **Test with real binaries** - Use rocRAND as torture test (15 wrappers, 200MB+)

LIEF is fine for parsing, but we shouldn't rely on it for modification - it tries to be everything and handles none of our edge cases well. Write our own byte-level surgery with proper abstractions.

---

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

### Known Limitations / Workarounds

**Split artifact flattening not wired up for local dev builds**

When `THEROCK_KPACK_SPLIT_ARTIFACTS=ON`, the build produces split artifacts under `build/artifacts/` with both generic (`*_generic/`) and arch-specific (`*_gfx*/`) directories. However, the CMake flatten step runs on the unsplit artifacts BEFORE splitting occurs, so the split artifacts (containing `.kpm` and `.kpack` files) don't make it to `build/dist/rocm/`.

**Workaround**: Manually flatten split artifacts after build:
```bash
# Flatten all split artifacts (generic + arch-specific) to dist
for i in build/artifacts/*_generic build/artifacts/*_gfx*; do
  [ -d "$i" ] && python ./build_tools/fileset_tool.py artifact-flatten -o build/dist/rocm "$i"
done
```

**Root cause**: The original design assumed split artifacts would be handled by CI shards uploading/downloading, not local multi-arch builds. The flatten command in `therock_artifacts.cmake` uses `_component_dirs` which points to unsplit artifacts, and the split happens in a separate custom command afterward.

**Future fix**: Either have split_artifacts.py do the flatten (it knows what dirs it creates), or add a post-split flatten step that globs for all `${artifact_prefix}_*` directories.

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

### Completed
9. [x] **CLR integration** - HIPK detection + kpack_load_code_object call
10. [x] **Multi-TU bundle support** - Bundle index in wrapper reserved1, indexed TOC keys
11. [x] **End-to-end test with RAND** - All 44 rocRAND tests pass with split binary

### Next
12. [ ] **ELF surgery refinements**:
    - Fix `.dynstr` section warnings (GDB complains about strings)
    - Fix strip corruption (stripped binary becomes completely invalid)
    - Investigate if we're overwriting wrong sections during ELF modification
13. [ ] **Move rocm-kpack into rocm-systems** - Integrate as submodule or merge
14. [ ] **Stage PRs** - Clean up commits, organize for review
15. [ ] Windows support (documented approach, implement when needed)

---

## Debugging Log

### 2024-12-31 - Initial Runtime Test Segfault (FIXED)

**Issue**: First test with kpack-enabled CLR resulted in segfault during library initialization.

**Debug build configuration**:
```bash
cmake . -Dhip-clr_BUILD_TYPE=RelWithDebInfo \
        -DrocRAND_BUILD_TYPE=RelWithDebInfo \
        -Drocm-kpack_BUILD_TYPE=RelWithDebInfo
```

**Symptoms**:
- GDB showed corrupt `.dynstr` section warnings
- Crash in `_init` during library loading (static initializer)
- Crash address was in zeroed `.hip_fatbin` region

**Investigation**:
1. Compared program headers between unsplit (9 segments) and split (13 segments) libraries
2. Found that unsplit library worked fine (44 tests passed)
3. Identified the bug: Two LOAD segments in split binary shared the same file offset (0x1db1000):
   - NOBITS segment for zeroed .hip_fatbin: `offset=0x1db1000, FileSiz=0`
   - Suffix segment (unaligned end): `offset=0x1db1000, FileSiz=0x9e0`

**Root Cause**: In `elf_modify_load.py`'s `conservative_zero_page()` function, when splitting the PT_LOAD segment, both the NOBITS segment ("Piece 3") and the suffix segment ("Piece 4") were given the same `aligned_offset` value. The dynamic linker got confused by two segments sharing the same file offset.

**Fix Applied**: Modified `conservative_zero_page()` to extend the NOBITS region to cover the full section including any unaligned suffix, rather than creating a separate suffix segment. This is safe because the suffix is part of the section being zeroed anyway.

Code change in `/develop/therock/base/rocm-kpack/python/rocm_kpack/elf_modify_load.py`:
```python
# Before: Created separate NOBITS and suffix segments with same offset (BUG)
# After: Extend NOBITS to cover suffix
zero_page_vsize = section_end_vaddr - aligned_vaddr  # Was: aligned_size
```

**Commit**: 126e12b - Fix NOBITS segment offset collision in conservative_zero_page

### 2024-12-31 - Symbol Table Corruption (FIXED)

**Issue**: After first fix, still getting segfault with corrupt symbol table warnings.

**Symptoms**:
- readelf showed `Section '.dynstr' is corrupt` warning
- .dynsym entries showed garbage values
- Crash still in `_init` but different address

**Investigation**:
1. Disabled zero-page optimization to isolate bug - still crashed
2. Tested Phase 1 (`map_section_to_new_load`) separately - symbols CORRUPTED
3. Tested marker addition (`add_kpack_ref_marker`) separately - symbols OK
4. Compared .dynsym offset (0x238) with program header end: `0x40 + 9*56 = 0x238`
5. Found 10th program header was being written at exactly 0x238

**Root Cause**: Off-by-one error in `map_section_to_new_load()` min_content_offset check.
```python
# Bug: used > instead of >=
if shdr.sh_offset > ehdr.e_phoff + old_phdr_size:  # 0x238 > 0x238 = False
    min_content_offset = min(min_content_offset, shdr.sh_offset)
```
When .dynsym starts at exactly `e_phoff + e_phnum * 56`, the `>` check returns false, so .dynsym isn't counted as content. Adding the 10th program header overwrites its first 56 bytes.

**Fix Applied**: Changed `>` to `>=` in both section and program header offset checks in `elf_modify_load.py:914,920`.

**Commit**: 27c1538 - Fix off-by-one error in program header relocation

**Result**: Library loads correctly. 28+ tests pass. Device code tests fail as expected (CLR integration not yet implemented).

### 2024-12-31 - Kpack Runtime Integration Testing

**Context**: Testing end-to-end flow with CLR integration complete. HIPK detection and kpack loading work.

**Hardlink Corruption Bug (FIXED)**:
- **Issue**: `artifact_splitter.py` modified binaries in-place, but artifact dirs hardlink to stage, corrupting originals
- **Fix**: Write to temp file, then unlink+rename to break hardlinks (artifact_splitter.py:574-587)
- **Verification**: After fix, stage=HIPF, unsplit=HIPF, split=HIPK ✓

**Current Investigation - Symbol Not Found**:

Tests fail with split binary but pass with unsplit (210MB original from stage):
```
Cannot find Symbol: _ZN12rocrand_impl...init_engines_mrg...target_archE1201
```

kpack loading works correctly:
```
kpack: found kernel: 2491232 bytes
kpack: loaded code object: 2491232 bytes
```

But the loaded code object doesn't contain the required symbol.

**Key observations**:
1. Original stage binary (210MB, HIPF magic) → 44/44 tests pass
2. Split binary (113MB, HIPK magic) → 30/44 pass, 4 fail with symbol not found
3. kpack archives contain code objects but missing some symbols
4. `.hip_fatbin` section at offset 0x01db1000 contains ALL ZEROS in stage binary
5. `clang-offload-bundler --list` returns EMPTY for stage binary

**Hypothesis**: The fat binary content may be stored in a different location/format than expected. The extraction during split may not be finding all the device code, or rocRAND uses a different bundling mechanism.

**Files changed in this session**:
- `artifact_splitter.py`: Hardlink fix + kernel_name fix
- `loader.cpp`: Target triple prefix stripping (`amdgcn-amd-amdhsa--gfx1100` → `gfx1100`)

**Next steps** (completed in next session):
1. ~~Investigate where rocRAND's device code actually lives (not in .hip_fatbin?)~~ - It IS in .hip_fatbin, but as 15 concatenated bundles
2. ~~Check if rocRAND uses RDC (relocatable device code) which has different bundling~~ - Yes, confirmed RDC with 15 bundles
3. ~~Verify the packing phase extracts all device code correctly~~ - Fixed, now extracts all 46MB per arch

### 2024-12-31 - RDC Wrapper→Bundle Mapping Discovery

**Critical Architecture Finding**: The 15 bundles are NOT arbitrarily concatenated. Each has a DEDICATED wrapper that points to it.

**Evidence**:
```
# 15 __hip_fatbin_wrapper symbols, each at offset 0x18 apart
nm librocrand.so | grep __hip_fatbin_wrapper
0881c460 d __hip_fatbin_wrapper
0881c478 d __hip_fatbin_wrapper
...
0881c5b0 d __hip_fatbin_wrapper

# 15 __hip_module_ctor functions, each referencing a DIFFERENT wrapper
ctor  0 at 0x7ae34a0 → wrapper at 0x881c460
ctor  1 at 0x7b38850 → wrapper at 0x881c478
...
ctor 14 at 0x874c9d0 → wrapper at 0x881c5b0

# Each wrapper's binary_ptr is RELOCATED at load time to different bundle offsets
Wrapper  0: reloc target 0x1db1000 → fatbin+0x0        (Bundle 0)
Wrapper  1: reloc target 0x2274000 → fatbin+0x4c3000   (Bundle 1)
Wrapper  2: reloc target 0x274b000 → fatbin+0x99a000   (Bundle 2)
...
Wrapper 14: reloc target 0x70bd000 → fatbin+0x530c000  (Bundle 14)
```

**How it works at runtime (normal non-split path)**:
1. 15 `__hip_module_ctor` functions run during library load (one per RDC compilation unit)
2. Each ctor calls `__hipRegisterFatBinary(&its_specific_wrapper)`
3. Each wrapper's `binary_ptr` points to ONE specific bundle in `.hip_fatbin`
4. CLR/COMGR parses that ONE bundle and extracts ONE code object per arch
5. Total: 15 registrations × ~400 kernels each = 5324 kernels registered

**Why this matters for kpack split**:
- Current split creates SHARED `.rocm_kpack_ref` metadata for ALL 15 wrappers
- When `__hipRegisterFatBinary()` is called for wrapper N, it can't distinguish which bundle N is
- We call `kpack_load_code_object()` with same `kernel_name` 15 times, getting ALL 15 concatenated each time
- This is wrong - wrapper N should get exactly bundle N's code object

**Architectural options**:
1. **Per-wrapper metadata**: ELF surgery creates 15 separate `.rocm_kpack_ref` sections, each with indexed kernel_name (`lib.so#0`, `lib.so#1`, etc.). Each wrapper's `binary` pointer is updated to its specific section.

2. **Wrapper address lookup**: Single metadata contains table mapping wrapper virtual addresses → bundle indices. At runtime, `kpack_load_code_object()` receives wrapper address and looks up correct bundle.

3. **Pre-link at pack time**: Combine all 15 code objects into single relocatable ELF at pack time using device linker. Returns one mega-ELF containing all 5324 kernels. This changes program structure but may be cleanest.

**Files involved**:
- `elf_modify_load.py` - Would need to track wrapper→bundle correspondence during ELF surgery
- `artifact_splitter.py` - Would need to generate per-wrapper metadata (option 1) or address table (option 2)
- `kpack.cpp` / `loader.cpp` - Would need to accept wrapper context (address or index)

---

### 2024-12-31 - RDC Discovery and Fix Attempt

**Key Discovery**: rocRAND uses RDC (Relocatable Device Code), resulting in **15 concatenated** `__CLANG_OFFLOAD_BUNDLE__` blocks in the `.hip_fatbin` section.

**Evidence**:
```
$ grep -boa '__CLANG_OFFLOAD_BUNDLE__' librocrand.so.1.1 | wc -l
15
```

Each bundle contains 3 entries (host + gfx1100 + gfx1201). Total device code:
- gfx1100: 48,480,720 bytes (46.2 MB)
- gfx1201: 48,228,696 bytes (46.0 MB)

We were only extracting 2.4 MB (first bundle only).

**Bug**: `clang-offload-bundler --list` only returns targets from the FIRST bundle. This is a known upstream bug.

**Fixes applied**:
1. `ccob_parser.py`: Added `find_bundle_offsets()`, `parse_concatenated_bundles()`, `extract_all_code_objects()`
2. `binutils.py`: Added detection and extraction for concatenated bundles
3. `artifact_splitter.py`: Track code object index per (binary, arch), use indexed keys (`lib.so#0`, etc.)
4. `kpack.cpp`: Added `find_kernel_entries()` helper that searches for indexed keys when exact match fails

**Test results after fix**:
- Kpack archives: 47MB + 46MB (was 2.4MB + 2.4MB) ✓
- TOC contains 15 indexed keys per arch ✓
- Loader finds and returns 48MB code object ✓
- **CLR segfaults** ✗

**Segfault root cause**: CLR calls `kpack_load_code_object()` 15 times (once per HIPK wrapper), but all 15 wrappers point to the SAME metadata. Each call looks up the same `kernel_name` and we return ALL 15 concatenated. CLR tries to load this as a single ELF → crash.

**Next steps** (for future session):
1. Design proper RDC support - options documented in "Follow-up Items" section
2. Consider simpler approach: Option 3 (pre-link at pack time) may be easiest

### 2025-12-31 - Multi-TU Bundle Support Implementation (POC Complete)

**Goal**: Make kpack split work with RDC binaries like rocRAND that have 15 wrappers/bundles.

**Architecture**:
```
Before (single-TU):
  1 wrapper → 1 bundle in .hip_fatbin → 1 code object per arch
  CLR: lookUpCodeObject() parses bundle → returns 1 code object

After (multi-TU with kpack):
  15 wrappers → shared .rocm_kpack_ref metadata
  Each wrapper: reserved1 = bundle_index (0-14)
  CLR: kpack_load_code_object(..., "lib.so#N") → returns that bundle's code object
```

**Step-by-step implementation**:

#### 1. ELF Surgery - Multi-TU Detection and Bundle Index Writing

**File: `/develop/therock/base/rocm-kpack/python/rocm_kpack/elf_offload_kpacker.py`**

Added functions to detect multi-TU binaries and write bundle indices:

```python
def _find_bundle_offsets(data: bytes, fatbin_offset: int) -> list[int]:
    """Scan .hip_fatbin for all __CLANG_OFFLOAD_BUNDLE__ magic headers.
    Returns list of section-relative offsets where bundles start."""
    # Searches for 24-byte magic string, returns offsets

def _read_wrapper_relocation_addends(
    elf: lief.ELF.Binary, wrappers: list[lief.ELF.Symbol]
) -> dict[int, int]:
    """Read relocation addends for each wrapper's binary_ptr field.
    Returns {wrapper_vaddr: relocation_addend}"""
    # Each wrapper at offset +8 has R_X86_64_RELATIVE pointing to its bundle

def _map_wrapper_bundle_indices(
    reloc_addends: dict[int, int], bundle_offsets: list[int], fatbin_vaddr: int
) -> dict[int, int]:
    """Map wrapper vaddrs to bundle indices based on relocation targets.
    Returns {wrapper_vaddr: bundle_index}"""
    # reloc_addend == fatbin_vaddr + bundle_offset[i] → index = i

def _rewrite_hipfatbin_magic(..., wrapper_bundle_indices: dict[int, int] | None = None):
    # Now also writes bundle index to reserved1 (offset +16):
    bundle_index = wrapper_bundle_indices.get(wrapper_vaddr, 0)
    struct.pack_into("<Q", data, wrapper_offset + 16, bundle_index)
```

#### 2. Artifact Splitter - Always Use Indexed TOC Keys

**File: `/develop/therock/base/rocm-kpack/python/rocm_kpack/artifact_splitter.py`**

Changed to always emit indexed keys even for single-TU binaries (simpler, consistent):

```python
# Track code object index per (binary, arch)
code_object_counts: dict[str, int] = {}  # {arch: count}

for arch in sorted(code_objects_by_arch.keys()):
    base_relpath = str(binary_path.relative_to(prefix_path))
    index = code_object_counts.get(arch, 0)
    code_object_counts[arch] = index + 1
    source_relpath = f"{base_relpath}#{index}"  # e.g., "lib/librocrand.so.1.1#0"
```

#### 3. CLR - Read Bundle Index from Wrapper

**File: `/develop/therock/rocm-systems/projects/clr/hipamd/src/hip_code_object.cpp`**

In `addKpackBinary()`, read bundle index from wrapper->dummy1 (which is reserved1):

```cpp
// Get bundle index from wrapper->dummy1 (reserved1 field)
uint64_t bundle_index = reinterpret_cast<uintptr_t>(wrapper->dummy1);

FatBinaryInfo* fatBinaryInfo =
    new FatBinaryInfo(std::string(binary_path), wrapper->binary, bundle_index);
```

#### 4. CLR - Pass Bundle Index Through to Kpack

**File: `/develop/therock/rocm-systems/projects/clr/hipamd/src/hip_fatbin.hpp`**

```cpp
#if ROCM_KPACK_ENABLED
  FatBinaryInfo(const std::string& binary_path, const void* hipk_metadata,
                uint64_t bundle_index = 0);
#endif
// ...
#if ROCM_KPACK_ENABLED
  const void* hipk_metadata_ = nullptr;
  bool is_kpack_ = false;
  uint64_t bundle_index_ = 0;  // Bundle index for multi-TU binaries
#endif
```

**File: `/develop/therock/rocm-systems/projects/clr/hipamd/src/hip_fatbin.cpp`**

```cpp
FatBinaryInfo::FatBinaryInfo(const std::string& binary_path, const void* hipk_metadata,
                             uint64_t bundle_index)
    : fname_(binary_path), /* ... */ bundle_index_(bundle_index) { }

// In ExtractKpackBinary():
std::string indexed_name = fname_ + "#" + std::to_string(bundle_index_);
kpack_error_t err =
    kpack_load_code_object(PlatformState::kpackGetCache(), hipk_metadata_, indexed_name.c_str(),
                           arch_ptrs.data(), arch_ptrs.size(), &code_object, &code_object_size);
```

#### 5. Kpack Loader - Use Indexed Lookup Key

**File: `/develop/therock/base/rocm-kpack/runtime/src/loader.cpp`**

The key insight: CLR passes `binary_path` like `/path/lib.so#1`, but metadata has `kernel_name` like `math-libs/.../librocrand.so.1.1`. We need to extract `#N` from path and append to kernel_name:

```cpp
// For multi-TU binaries, the caller passes an indexed path (e.g., "/path/lib.so#1").
// Extract the index and append it to the embedded kernel_name for TOC lookup.
std::string lookup_key = kernel_name;
const char* hash_pos = std::strchr(binary_path, '#');
if (hash_pos != nullptr) {
  lookup_key += hash_pos;  // Append "#N" suffix
}
KPACK_DEBUG(cache, "kernel lookup key: '%s'", lookup_key.c_str());
```

**Bug fixed**: Initially used `binary_path` directly as lookup key, but TOC keys use relative paths from metadata, not absolute runtime paths. The fix extracts just the `#N` suffix and appends to the embedded kernel_name.

**Debugging session**:
```
# With bug (wrong lookup):
kernel_name='math-libs/rocRAND/stage/lib/librocrand.so.1.1'  (from metadata)
lookup_key='/develop/therock/build/dist/rocm/lib/librocrand.so.1.1#1'  (wrong!)
# TOC has: 'math-libs/rocRAND/stage/lib/librocrand.so.1.1#0', '#1', etc.
# Result: Not found, fallback returns 48MB concatenated blob, segfault

# After fix:
kernel_name='math-libs/rocRAND/stage/lib/librocrand.so.1.1'
lookup_key='math-libs/rocRAND/stage/lib/librocrand.so.1.1#1'  (correct!)
# Result: Returns 2.5MB code object for bundle #1
```

**Test results**:
```bash
# Flatten split artifacts
python ./build_tools/fileset_tool.py artifact-flatten -o build/dist/rocm \
  build/artifacts/rand_lib_generic build/artifacts/rand_lib_gfx1201

# Verify sizes
ls -la build/dist/rocm/lib/librocrand.so.1.1
# 109MB (split) vs 201MB (unsplit)

# Run tests
LD_LIBRARY_PATH=build/dist/rocm/lib timeout 60 build/dist/rocm/bin/test_rocrand_basic
# All 44 tests pass
```

**Known issues discovered** (for future refinement):
1. **GDB warnings**: `Section '.dynstr' is corrupt` - strings not where GDB expects
2. **Strip corruption**: `strip librocrand.so.1.1` produces completely corrupted binary
3. These indicate ELF surgery needs refinement but don't affect runtime functionality

---

## Follow-up Items (WIP)

Items discovered during integration that need follow-up before landing:

### Critical - Must Fix

1. **Hardlink corruption in artifact_splitter.py** ✅ FIXED
   - **Issue**: Splitter modifies binary files in-place. But the artifact directory uses hardlinks from the stage directory, so modifying the split artifact also corrupts the original stage files.
   - **Fix applied**: Write to temp_stripped file, then unlink+rename to break hardlinks
   - **Location**: `/develop/therock/base/rocm-kpack/python/rocm_kpack/artifact_splitter.py:574-587`

2. **kernel_name mismatch between metadata and TOC** ✅ FIXED
   - **Issue**: Metadata embedded `kernel_name=artifact_prefix` (e.g., "rand_lib") but TOC used full relative path (e.g., "math-libs/rocRAND/stage/lib/librocrand.so.1.1")
   - **Fix**: Changed artifact_splitter.py:565 to use the full relative path for kernel_name

3. **Target triple prefix stripping** ✅ FIXED
   - **Issue**: CLR passes full ISA name like `amdgcn-amd-amdhsa--gfx1100` but manifest/archive keys are just `gfx1100`
   - **Fix**: Added `strip_target_prefix()` helper in loader.cpp to strip `amdgcn-amd-amdhsa--` prefix

4. **RDC (Relocatable Device Code) / Multi-TU support** ✅ FIXED (POC)

   **Discovery**: rocRAND uses RDC, resulting in 15 concatenated `__CLANG_OFFLOAD_BUNDLE__` blocks in `.hip_fatbin`. Each has a dedicated `__hip_fatbin_wrapper` with a R_X86_64_RELATIVE relocation pointing to its specific bundle offset.

   **Solution implemented**:
   - Store bundle index (0-14) in wrapper's `reserved1` field during ELF surgery
   - At runtime, each wrapper reads its index and requests the correct code object
   - TOC keys are indexed: `math-libs/rocRAND/stage/lib/librocrand.so.1.1#0` through `#14`
   - Loader extracts `#N` suffix from binary_path and appends to kernel_name for TOC lookup

   **Files changed (see detailed debugging log below for specifics)**:
   - `rocm_kpack/elf_offload_kpacker.py` - Multi-TU detection, wrapper→bundle mapping, bundle index writing
   - `rocm_kpack/artifact_splitter.py` - Always use indexed TOC keys
   - `rocm_kpack/runtime/src/loader.cpp` - Extract index from path, append to lookup key
   - `clr/hipamd/src/hip_fatbin.hpp` - Added bundle_index constructor param and member
   - `clr/hipamd/src/hip_fatbin.cpp` - Pass bundle_index to kpack loader
   - `clr/hipamd/src/hip_code_object.cpp` - Read bundle_index from wrapper->dummy1

   **Test results**:
   - All 44 rocRAND tests pass with split binary
   - Library size: 109MB (split) vs 201MB (unsplit)
   - Individual bundle size: ~2.5MB (correct) vs 48MB (all concatenated)

   **Known remaining issues** (ELF surgery refinements, not blocking):
   - GDB warnings about `.dynstr` strings not where expected
   - Stripping the binary causes complete corruption
   - These are mechanical fixes for a future session

### Nice to Have

4. **Add debug output for kernel_name lookup**
   - Currently only shows arch matching debug. Would be helpful to also show what kernel_name is being looked up.

5. **Test with multiple binaries in same artifact**
   - rand_lib has both librocrand.so and libhiprand.so. Verify both work correctly.

---

## Completion Notes

<!-- Fill this in when task is done -->

### Summary
(Not yet complete)

### Lessons Learned
(Not yet complete)

### Follow-up Tasks
(Not yet complete)
