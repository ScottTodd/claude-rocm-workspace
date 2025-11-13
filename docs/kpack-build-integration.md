# kpack Build Integration Plan

## Overview

This document describes the integration of rocm-kpack into TheRock's build pipeline, focusing on a map/reduce architecture for splitting and recombining device code artifacts.

## Problem Statement

TheRock builds produce artifact directories containing mixed host and device code. These need to be:
1. Split into generic (host-only) and architecture-specific (device code) components
2. Recombined according to packaging topology for distribution
3. Organized so runtime can efficiently locate device code

## Architecture

### Key Design Decision: Manifest-Based Indirection

Instead of embedding full kpack search paths in host binaries, we use a two-level indirection:
1. Host binaries contain a relative path to a manifest file
2. The manifest lists available kpack files and their locations
3. The reduce phase updates the manifest without modifying host binaries

This provides flexibility in final assembly while keeping host code architecture-agnostic.

## Map Phase: Per-Build Artifact Splitting

Each architecture build produces artifacts that need splitting. The map phase processes these deterministically.

### Input
- Artifact directory from build (e.g., `/develop/therock-build/artifacts/miopen_lib_gfx110X/`)
- Contains mixed host and device code

### Process
1. Scan artifact directory for bundled binaries
2. Extract device code from each binary
3. Auto-detect ISAs present in the binary
4. Generate one kpack file per ISA
5. Modify host binaries to reference relative manifest path
6. Preserve directory structure from artifact

### Output Structure
```
map-output/
├── miopen_lib_generic/
│   ├── artifact_manifest.txt
│   ├── {preserved-structure}/
│   │   └── bin/
│   │       └── binary1  # Modified with .rocm_kpack_manifest marker
│   └── kpack.manifest   # JSON manifest listing available kpacks
├── miopen_lib_gfx1100.kpack
├── miopen_lib_gfx1101.kpack
└── miopen_lib_gfx1102.kpack
```

### Manifest Format
```json
{
  "version": "1.0",
  "group": "miopen",
  "kpack_files": [
    {
      "architecture": "gfx1100",
      "path": "../miopen_lib_gfx1100.kpack",
      "checksum": "sha256:..."
    },
    {
      "architecture": "gfx1101",
      "path": "../miopen_lib_gfx1101.kpack",
      "checksum": "sha256:..."
    }
  ]
}
```

## Reduce Phase: Package Assembly

The reduce phase combines artifacts from all map phases according to packaging topology.

### Input
- Artifact directories from all map phase outputs
- Configuration file defining packaging topology

### Configuration Schema
```yaml
version: 1.0

# Which build provides primary generic artifacts
primary_generic_source: gfx110X

# Architecture grouping for packages
architecture_groups:
  gfx11-desktop:
    display_name: "Desktop Graphics (gfx11)"
    architectures:
      - gfx1100
      - gfx1101
      - gfx1102

  gfx11-datacenter:
    display_name: "Data Center (gfx11)"
    architectures:
      - gfx1150
      - gfx1151

# Component-specific overrides
component_overrides:
  rocblas:
    architecture_groups:
      gfx11-unified:
        architectures: [gfx1100, gfx1101, gfx1102, gfx1150, gfx1151]

# Validation rules
validation:
  error_on_duplicate_device_code: true
  verify_generic_artifacts_match: false
```

### Process
1. Copy generic artifacts from primary source
2. Collect kpack files according to architecture groups
3. Update manifest files to reflect final kpack locations
4. Organize into package-ready directory structure

### Output Structure
```
package-staging/
├── gfx11-desktop/
│   ├── {generic-artifact-structure}/
│   ├── .kpack/
│   │   ├── miopen_lib_gfx1100.kpack
│   │   ├── miopen_lib_gfx1101.kpack
│   │   └── miopen_lib_gfx1102.kpack
│   └── kpack.manifest  # Updated with final paths
└── gfx11-datacenter/
    ├── {generic-artifact-structure}/
    ├── .kpack/
    │   ├── miopen_lib_gfx1150.kpack
    │   └── miopen_lib_gfx1151.kpack
    └── kpack.manifest
```

## Implementation Components

### New Tools

1. **`split_artifacts.py`** - Map phase tool
   - Input: Artifact directory
   - Output: Split generic + per-ISA kpacks
   - Deterministic, no configuration needed

2. **`recombine_artifacts.py`** - Reduce phase tool
   - Input: Multiple artifact directories + config
   - Output: Package-ready directory structure
   - Configuration-driven grouping

### Modified Components

1. **`ElfOffloadKpacker`** - Add manifest reference injection
   - Instead of `.rocm_kpack_ref` with direct kpack paths
   - Inject `.rocm_kpack_manifest` with relative manifest path

2. **Runtime (future)** - Manifest-aware kpack loading
   - Read manifest path from binary
   - Load manifest JSON
   - Locate and load appropriate kpack files

## Integration with TheRock

### Build Flow
1. Standard TheRock builds produce artifacts (unchanged)
2. Map phase runs per build, splits artifacts
3. CI uploads split artifacts to S3
4. Package jobs download all artifacts
5. Reduce phase combines according to package type
6. Standard packaging tools create DEB/RPM/wheels

### Artifact Naming Convention
Following TheRock's pattern:
- Generic: `{name}_{component}_generic/`
- Device: `{name}_{component}_gfx{arch}.kpack`

## Advantages of This Approach

1. **Host Code Stability**: Host binaries don't need modification during reduce phase
2. **Flexible Packaging**: Can reorganize kpacks without touching binaries
3. **Deterministic Map**: No configuration needed for splitting
4. **Configurable Reduce**: Packaging topology defined in version-controlled config
5. **Incremental Updates**: Can update manifest without full rebuild

## Open Questions

1. **Manifest Location**: Where should the manifest file be placed relative to binaries?
   - Option A: Fixed location like `../kpack.manifest`
   - Option B: Configurable per component
   - Option C: Search path with fallbacks

2. **Kpack Directory Structure**: Where do kpack files live in final layout?
   - Option A: Single `.kpack/` directory at distribution root
   - Option B: Per-component `.kpack/` directories
   - Option C: Configurable via manifest

3. **Validation Strategy**: What checks should reduce phase perform?
   - Required: No duplicate device code per architecture
   - Optional: Verify generic artifacts match across builds
   - Optional: Check kernel compatibility versions

## Next Steps

1. Prototype manifest injection mechanism
2. Test ISA auto-detection with real binaries
3. Design manifest lookup logic for runtime
4. Create example configuration for current build topology
5. Integration test with sample artifacts