---
repositories:
  - therock
  - rocm-kpack
---

# Kpack Windows Port

**Status:** In progress - Phase 3 Complete, Ready for Review

## Overview

See the task `kpack-runtime-integration.md` for the overall integration effort. This task is tracking porting to Windows. The eventual goal is that all tooling in rocm-kpack works transparently:

* On Windows and Linux
* Operating transparently on ELF and COFF files containing ROCm components
* Able to process ELF and COFF trees from Linux (for better testing, etc).

While there are any number of things that may need to be adapted, the most critical piece of infrastructure is the `rocm_kpack.elf` transformation. These must be ported to `rocm_kpack.coff` and subjected to a similar level of testing.

While doing Windows dev work, we will have an exagerated testing process because I will need to manually pull branches on Linux and verify that we haven't broken anything.

There are some populated directories that will help with this task:

* `C:\src\artifacts` - Artifacts fetched and extracted from a main gfx120X-all build
* `C:\src\rocm` - The same flattened into a usable SDK
* `C:\src\rocm\lib\llvm\bin` - ROCm bundled LLVM and some associated tools

Use `C:\src\tmp` for temporary files/scripts/etc.

---

## Implementation Plan (2025-01-03)

### Key Findings from Exploration

**PE/COFF vs ELF Differences:**

| Aspect | ELF | PE/COFF |
|--------|-----|---------|
| Section names | Unlimited | **8 chars max** |
| Memory mapping | PT_LOAD segments | Section characteristics |
| Relocations | RELA with addend | Base relocations (simpler!) |
| Virtual addresses | PHDR p_vaddr | ImageBase + RVA |

**Section Name Mapping (8-char limit):**
- `.hipFatBinSegment` → `.hipFatB` (already used in Windows builds)
- `.hip_fatbin` → `.hip_fat` (already used)
- `.rocm_kpack_ref` → `.kpackrf` (new, needs 8-char name)

**Wrapper Structure is IDENTICAL to ELF:**
```
Offset 0-3:  Magic (HIPF/HIPK)
Offset 4-7:  Version
Offset 8-15: Binary pointer (8 bytes) ← update this
Offset 16-23: Filename pointer
```

Verified in `copy.hip.exe`:
```
00000000: 4650 4948 0100 0000 00f0 8640 0100 0000  FPIH.......@....
00000010: 0000 0000 0000 0000                      ........
```

**PE Relocations are Simpler:**
- ELF: Must update BOTH pointer value AND RELA addend
- PE: Just update pointer value (base relocation says "adjust this", target is in data)

### Phased Implementation

**Critical**: Zero-page is load-bearing for the design. Must prove viability early.

#### Phase 1A: Basic Scaffolding (WIP checkpoint) ✓ DONE
**Goal**: Parse PE, find sections, basic read/write

**Files to create**:
```
rocm_kpack/coff/
    __init__.py
    types.py          # DosHeader, CoffHeader, OptionalHeader64, SectionHeader
    surgery.py        # CoffSurgery class
```

**Deliverables**:
1. Parse PE headers (DOS, COFF, Optional, Section headers)
2. Find sections by name (`.hipFatB`, `.hip_fat`)
3. RVA ↔ file offset conversion
4. Basic pointer read/write at RVA
5. **WIP commit checkpoint**

#### Phase 1B: Zero-Page Viability Proof ✓ DONE
**Goal**: Prove zero-page optimization works on PE/COFF before investing further

**Key question**: Can we remove content from `.hip_fat` and have a valid, loadable PE?

**Approach**:
1. Take `copy.hip.exe` (small, 1 wrapper)
2. Calculate page-aligned region in `.hip_fat`
3. Remove bytes from file
4. Adjust `SizeOfRawData` for `.hip_fat`
5. Adjust `PointerToRawData` for all subsequent sections
6. Update `SizeOfImage` in optional header
7. Verify with llvm-objdump and actual loading

**PE-specific challenges**:
- No memsz/filesz distinction (unlike ELF PT_LOAD)
- `.reloc` section typically at end, may need adjustment
- Must maintain FileAlignment (typically 0x200)
- Must maintain SectionAlignment (typically 0x1000)

**If viability fails**: Need to reconsider design (maybe keep file size, rely on compression)

#### Phase 2: Full Semantic Transformation ✓ DONE
- Add `.kpackrf` section with MessagePack marker
- Update wrapper pointers
- Rewrite HIPF → HIPK magic
- Zero-page `.hip_fat`

#### Phase 3: Testing & Verification ← CURRENT
- CoffVerifier
- Test suite parallel to ELF tests

### Test Binaries

Primary (from `C:\src\rocm\bin\`):
- `copy.hip.exe` - Small, 1 wrapper (~1MB fatbin) - **Primary test target**
- `rocrand.dll` - Large, 15 wrappers (~57MB fatbin)
- Various `*.hip.exe` test executables

Sections in `copy.hip.exe`:
```
Idx Name          Size     VMA              Type
  0 .text         0048fac6 0000000140001000 TEXT
  ...
  4 .hipFatB      00000018 000000014086e000 DATA  # 24 bytes = 1 wrapper
  5 .hip_fat      001015aa 000000014086f000 DATA  # ~1MB fatbin
  ...
```

### Alternatives Considered

1. **Use pefile library** - Rejected: adds dependency, inconsistent with pure-Python ELF approach
2. **Share code via abstraction layer** - Rejected: PE/COFF too different (no PHDRs, different relocations)
3. **Use llvm-objcopy for section addition** - Rejected: want pure Python for control and consistency

---

## Progress Log

### 2025-01-03: Initial Planning
- Explored ELF module structure (~8 files, ~3000 lines)
- Discovered PE section name 8-char limit
- Verified wrapper structure is identical to ELF
- Confirmed test binaries available in C:\src\rocm\bin\
- Created phased implementation plan with zero-page viability as critical gate

### 2025-01-03: Phase 1A Complete
Created basic COFF module:
- `rocm_kpack/coff/types.py` - PE/COFF structures (DosHeader, CoffHeader, OptionalHeader64, SectionHeader, BaseRelocationBlock, BaseRelocationEntry)
- `rocm_kpack/coff/surgery.py` - CoffSurgery class with parsing, section finding, RVA conversion, pointer read/write, base relocation iteration
- `rocm_kpack/coff/__init__.py` - Public API

**Test results on `copy.hip.exe`:**
```
Machine: 0x8664 (AMD64)
Sections: 9
ASLR: enabled

Sections:
  .text     RVA=0x00001000  VSize=0x0048FAC6
  .rdata    RVA=0x00491000  VSize=0x0038A82C
  .data     RVA=0x0081C000  VSize=0x0001E220
  .pdata    RVA=0x0083B000  VSize=0x00032F88
  .hipFatB  RVA=0x0086E000  VSize=0x00000018  # 24 bytes = 1 wrapper
  .hip_fat  RVA=0x0086F000  VSize=0x001015AA  # ~1MB fatbin
  .tls      RVA=0x00971000  VSize=0x00000009
  .rsrc     RVA=0x00972000  VSize=0x000001A8
  .reloc    RVA=0x00973000  VSize=0x00004888

Wrapper content:
  magic=HIPF, version=1, binary_ptr=0x14086F000 (points to .hip_fat)
  DIR64 relocation exists at wrapper pointer (RVA 0x86E008)

Total base relocations: 8988 (all DIR64)
```

**Key insight:** Base relocation exists at the wrapper binary pointer location. This means when we update the pointer, the relocation will still work correctly - base relocations just adjust pointers at load time based on actual ImageBase.

### 2025-01-03: Phase 1B Complete - Zero-Page Viability CONFIRMED

**Critical gate passed:** Zero-page optimization works on PE/COFF!

Test on `copy.hip.exe`:
```
Original file: 9,897,984 bytes
After zero-page: 8,845,312 bytes
Reduction: 1,052,672 bytes (10.6%)
llvm-objdump: VALID PE
```

**Algorithm (simpler than ELF!):**
1. Calculate page-aligned region in `.hip_fat` section
2. Remove those bytes from file (`del data[offset:offset+size]`)
3. Update `.hip_fat` header: `SizeOfRawData = remaining_content_size`
4. Update subsequent sections: `PointerToRawData -= removed_bytes`
5. Keep `VirtualSize` and `SizeOfImage` unchanged (loader zero-fills)

**Why simpler than ELF:**
- No need to split PT_LOAD segments
- No need to change section type to NOBITS
- PE naturally supports `VirtualSize > SizeOfRawData` (zero-fill semantics)

**Next:** Phase 2 - Full semantic transformation (add `.kpackrf`, update pointers, rewrite magic, zero-page)

### 2025-01-03: Phase 2 Complete - Full Transformation Pipeline

Implemented complete kpack transformation pipeline for PE/COFF:

**New files:**
- `rocm_kpack/coff/zero_page.py` - Zero-page optimization module
- `rocm_kpack/coff/kpack_transform.py` - Full transformation pipeline

**New method in surgery.py:**
- `add_section()` - Add new section to PE binary

**Pipeline stages:**
1. Add `.kpackrf` section with MessagePack marker
2. Update all wrapper pointers to point to `.kpackrf`
3. Rewrite HIPF → HIPK magic for all wrappers
4. Zero-page `.hip_fat` section

**Test results on `copy.hip.exe` (1 wrapper):**
```
Original size: 9,897,984 bytes
New size: 8,845,824 bytes
Removed: 1,052,160 bytes (10.6%)
llvm-objdump: VALID PE
Wrapper pointer updated, magic=HIPK
```

**Test results on `rocrand.dll` (15 wrappers):**
```
Original size: 93,599,744 bytes (89.3 MB)
Fatbin size: 57,330,800 bytes (54.7 MB)
New size: 36,272,640 bytes (34.6 MB)
Removed: 57,327,104 bytes (61.2%)
llvm-objdump: VALID PE
All 15 wrappers transformed to HIPK
```

**Key achievements:**
- Pure Python implementation (no external tools)
- Mirrors ELF module structure
- Handles multi-wrapper binaries correctly
- Significant file size reduction (10-61% depending on fatbin proportion)

**Next:** Phase 3 - Testing infrastructure and verification module

### 2025-01-03: Phase 3 Complete - Testing Infrastructure & Cross-Platform Fixes

**Session summary:** Built complete test infrastructure, generic API, and fixed cross-platform issues.

**New modules created:**
- `rocm_kpack/__init__.py` - Package entry point with generic API exports
- `rocm_kpack/format_detect.py` - Binary format detection (ELF vs PE/COFF by magic bytes)
- `rocm_kpack/kpack_transform.py` - Generic API that auto-detects format and dispatches
- `rocm_kpack/platform_utils.py` - Windows console UTF-8 configuration

**Test files created:**
- `tests/coff/test_surgery.py` - 10 tests for CoffSurgery class
- `tests/coff/test_verify.py` - 11 tests for CoffVerifier
- `tests/coff/test_kpack_transform.py` - 11 tests for transformation pipeline
- `tests/common/conftest.py` - Cross-platform fixtures parameterized by (platform, co_version)
- `tests/common/test_kpack_transform.py` - 10 tests × 2 platforms = 20 test runs

**Windows test assets generated:**
- `test_assets/bundled_binaries/windows/cov5/` - 9 binaries (exe/dll with hip kernels + host-only)
- Built using HIPcc from Windows ROCm SDK

**Cross-platform fixes applied:**
1. `format_detect.py` - PE offset bounds validation (security fix)
2. `coff/verify.py` - Skip dumpbin on non-Windows (it's MSVC-specific)
3. `elf/verify.py` - Skip gdb/ldd on Windows (Linux-specific tools)
4. `database_handlers.py` - Use `as_posix()` for path matching (forward slashes)
5. `test_artifact_utils.py` - Use `as_posix()` in assertions
6. `tests/conftest.py` - Toolchain discovery via `KPACK_LLVM_BIN` env var
7. `binutils.py` - Helpful error message mentioning `KPACK_LLVM_BIN`
8. `build_test_bundles.py` - Fix `-fPIC` (Linux-only), UTF-8 console, bare except
9. `tests/common/conftest.py` - Fail (not skip) on missing checked-in assets

**Test results:**
```
Windows: 261 passed, 3 skipped
Linux:   261 passed, 3 skipped
```

**WIP commit:** `01c6efd` on branch `users/stella/coff-port`

**Next steps for landing:**
1. User review of changes (milestone review)
2. Squash commits for PR
3. Run `/prep-pr` workflow

**Files modified (27 total, +1407 lines):**
- New: `python/rocm_kpack/{__init__,format_detect,kpack_transform,platform_utils}.py`
- Modified: `python/rocm_kpack/{binutils,database_handlers}.py`
- Modified: `python/rocm_kpack/{coff/verify,elf/verify}.py`
- Modified: `test_generation/build_test_bundles.py`
- New: `tests/{coff,common}/*.py`
- Modified: `tests/{conftest,test_artifact_utils}.py`
- New: `test_assets/bundled_binaries/windows/cov5/*`

