# Artifact Splitter Implementation Status

## ✅ Completed

### 1. Core Architecture
- Implemented visitor pattern for file classification and processing
- Created exclude-first approach (scan → classify → exclude → copy)
- Plugin architecture for database handlers

### 2. Database Handlers
- **RocBLASHandler**: Detects rocBLAS Tensile kernel files (*.co, *.hsaco, *.dat with gfx patterns)
- **HipBLASLtHandler**: Detects hipBLASLt kernel files (similar patterns)
- **AotritonHandler**: Detects AOTriton kernel directories (aotriton/kernels/gfx*)
- Opt-in via `--split-databases` CLI flag

### 3. File Classification Visitor
```python
class FileClassificationVisitor:
    - Scans prefix directories
    - Identifies fat binaries (ELF with .hip_fatbin sections)
    - Detects architecture-specific database files
    - Builds exclude list for generic artifact
```

### 4. Generic Copy Visitor
```python
class GenericCopyVisitor:
    - Copies files to generic artifact
    - Respects exclude list from classification
    - Preserves directory structure
```

### 5. CLI Tool
- `/develop/rocm-kpack/python/rocm_kpack/tools/split_artifacts.py`
- Arguments: input-dir, output-dir, component-name, split-databases
- Uses `/develop/tmp` for temporary files

### 6. Bug Fixes
- Fixed BundledBinary cleanup error (initialized _temp_dir before operations)
- Fixed database file exclusion from generic artifact

## 📊 Test Results

Testing with `/develop/artifacts/build/artifacts/blas_lib_gfx110X-dgpu`:

### Generic Artifact (`blas_lib_generic`)
- **rocBLAS**: 55 files (all fallback.dat files - generic implementations)
- **hipBLASLt**: 3 files (hipblasltTransform.hsaco, TensileLiteLibrary_lazy_Mapping.dat, hipblasltExtOpLibrary.dat)
- These are correctly identified as generic files without architecture markers

### Architecture-Specific Artifacts
- **blas_lib_gfx1100**:
  - rocBLAS kernels (when enabled)
  - 95 hipBLASLt kernels
- **blas_lib_gfx1101**:
  - rocBLAS kernels (when enabled)
  - 111 hipBLASLt kernels
- **blas_lib_gfx1102**:
  - rocBLAS kernels (when enabled)

## ✅ Fat Binary Processing Working!

Successfully extracting kernels from fat binaries using clang-offload-bundler from ROCm SDK:
- rocBLAS libraries: Extracted kernels for gfx1100, gfx1101, gfx1102
- rocSOLVER libraries: Extracted kernels for gfx1100, gfx1101, gfx1102
- rocSPARSE libraries: Extracted kernels for gfx1100, gfx1101, gfx1102
- hipSPARSELt libraries: Extracted kernels for gfx906

Architecture extraction from target names is working correctly:
- Pattern: `hipv4-amdgcn-amd-amdhsa--gfx1100.hsaco`
- Regex: `gfx([0-9a-z]+)` extracts the architecture

## 🚧 TODO

### 1. Generate Kpack Files from Extracted Kernels
- Use PackedKernelArchive class to create .kp files per architecture
- Group extracted kernels by architecture
- Generate manifest files (.kpm) with kernel metadata
- Store in `_kpack` directory under prefix

### 2. Update ElfOffloadKpacker for Manifest Injection
- Modify fat binaries to reference kpack manifests
- Implement proper relative path computation from binary to manifest
- Inject manifest references using pre-computed relative paths
- Strip device code from fat binaries after extraction

### 3. Integration Points
- Build system integration (CMake)
- Python wheel splitting for PyTorch
- Runtime lookup mechanism (CLR vs comgr TBD)

## Usage Example

```bash
source /develop/therock-venv/bin/activate
cd /develop/rocm-kpack

# Full splitting with fat binary extraction and database handling
python -m rocm_kpack.tools.split_artifacts \
  --input-dir /path/to/artifact \
  --output-dir /path/to/output \
  --component-name my_component \
  --split-databases rocblas hipblaslt aotriton \
  --clang-offload-bundler /path/to/rocm/lib/llvm/bin/clang-offload-bundler \
  --verbose

# Database splitting only (no fat binary extraction)
python -m rocm_kpack.tools.split_artifacts \
  --input-dir /path/to/artifact \
  --output-dir /path/to/output \
  --component-name my_component \
  --split-databases rocblas hipblaslt

# Fat binary extraction only (no database handling)
python -m rocm_kpack.tools.split_artifacts \
  --input-dir /path/to/artifact \
  --output-dir /path/to/output \
  --component-name my_component \
  --clang-offload-bundler /path/to/rocm/lib/llvm/bin/clang-offload-bundler
```

## Next Steps

1. ✅ Located clang-offload-bundler in ROCm SDK
2. ✅ Implemented kernel architecture extraction from target names
3. 🚧 Generate kpack archives from extracted kernels
4. 🚧 Implement manifest injection in fat binaries
5. 🚧 Test end-to-end artifact splitting with kpack generation