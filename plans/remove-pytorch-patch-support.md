# Plan: Remove .patch File Support from external-builds/pytorch

## Overview

Remove the unused git patch file system from the PyTorch build infrastructure. The patch system was designed to apply custom patches but is no longer needed since ROCm-specific changes are maintained in downstream git forks (ROCm/pytorch) rather than as patch files.

**Scope**: Complete removal in a single PR including code, documentation, and CI workflow updates.

## Key Findings

- **Patch code location**: `repo_management.py` contains all core patch functions
- **Four repo scripts** use the patch system: pytorch_torch_repo.py, pytorch_audio_repo.py, pytorch_vision_repo.py, pytorch_triton_repo.py
- **CI workflows** currently pass `--patchset` parameter (will be removed)
- **No actual patches exist**: The `patches/` directory doesn't exist (system is unused)
- **windows_patch_fat_wheel.py**: NOT related to git patches (patches wheel files instead) - will not be modified

## Files to Modify

### Core Implementation (Remove patch functions)

**D:\projects\TheRock\external-builds\pytorch\repo_management.py**
- Remove functions: `save_repo_patches()`, `apply_repo_patches()`, `apply_all_patches()`, `do_save_patches()`, `get_patches_dir_name()`
- **Keep constants**: `TAG_UPSTREAM_DIFFBASE`, `TAG_HIPIFY_DIFFBASE` (still useful for marking upstream and hipify commits)
- Update `do_checkout()`: Remove patch application logic but keep tagging logic
- Keep `read_pytorch_rocm_pins()`: Not patch-related (reads ROCm fork commit pins)

### Repository Scripts (Remove patch arguments and subcommands)

**D:\projects\TheRock\external-builds\pytorch\pytorch_torch_repo.py**
- Remove arguments: `--patch-dir`, `--patchset`, `--patch`
- Remove subcommand: `save-patches`
- Update docstring: Remove patch-related documentation

**D:\projects\TheRock\external-builds\pytorch\pytorch_audio_repo.py**
- Remove arguments: `--patch-dir`, `--patchset`, `--patch`
- Remove subcommand: `save-patches`
- Update docstring: Remove patch-related documentation

**D:\projects\TheRock\external-builds\pytorch\pytorch_vision_repo.py**
- Remove arguments: `--patch-dir`, `--patchset`, `--patch`
- Remove subcommand: `save-patches`
- Update docstring: Remove patch-related documentation

**D:\projects\TheRock\external-builds\pytorch\pytorch_triton_repo.py**
- Remove arguments: `--patch-dir`, `--patchset`, `--patch`
- Remove subcommand: `save-patches`
- Update docstring: Remove patch-related documentation

### Documentation

**D:\projects\TheRock\external-builds\pytorch\README.md**
- Remove entire section: "About patch files and patchsets" (lines ~356-389)
- Remove entire section: "Checking out and applying patches" (lines ~391-434)
- Remove entire section: "Saving new patches" (lines ~436-485)
- Remove patch-related content from: "Alternate branches / patch sets" section (lines ~487-585)
- Update section: "Recommendation: avoid using patch files if possible" (lines ~337-354) to become a brief "Removed Features" note
- Add migration note explaining why patches were removed and pointing to ROCm fork branches

### CI Workflows

**D:\projects\TheRock\.github\workflows\build_portable_linux_pytorch_wheels.yml**
- Remove `pytorch_patchset` input parameter from workflow definition
- Remove `--patchset ${{ inputs.pytorch_patchset }}` from pytorch_torch_repo.py invocation (line ~179)
- Remove `--patch --patchset nightly` from pytorch_triton_repo.py invocation (line ~173)

**D:\projects\TheRock\.github\workflows\build_windows_pytorch_wheels.yml**
- Remove `pytorch_patchset` input parameter from workflow definition
- Remove `--patchset ${{ inputs.pytorch_patchset }}` from pytorch_torch_repo.py invocation (line ~198)

**D:\projects\TheRock\.github\workflows\release_portable_linux_pytorch_wheels.yml**
- Update matrix/strategy to remove patchset mappings
- Remove `pytorch_patchset` from workflow call parameters

**D:\projects\TheRock\.github\workflows\release_windows_pytorch_wheels.yml**
- Update matrix/strategy to remove patchset mappings
- Remove `pytorch_patchset` from workflow call parameters

## Implementation Steps

### Step 1: Update repo_management.py

1. Remove patch-related functions (lines ~117-205):
   - `save_repo_patches()`
   - `apply_repo_patches()`
   - `apply_all_patches()`
   - `do_save_patches()`
   - `get_patches_dir_name()`
   - `repo_hashtag_to_patches_dir_name()` (unused helper)

2. **Keep constants (lines 9-10)** - still useful for tracking commits:
   - `TAG_UPSTREAM_DIFFBASE = "THEROCK_UPSTREAM_DIFFBASE"` ✅ KEEP
   - `TAG_HIPIFY_DIFFBASE = "THEROCK_HIPIFY_DIFFBASE"` ✅ KEEP

3. Update `do_checkout()` function:
   - Remove `repo_patch_dir_base = args.patch_dir` (line ~277)
   - Remove `patches_dir_name = get_patches_dir_name(args)` (line ~279)
   - **Keep** git tag creation for `TAG_UPSTREAM_DIFFBASE` (line ~298, ~313) ✅ KEEP
   - Remove base patches application (lines ~320-327)
   - Remove hipified patches application (lines ~334-341)

4. Keep hipify-related code intact:
   - `do_hipify()`, `tag_hipify_diffbase()`, `commit_hipify_module()`, `commit_hipify()` ✅ KEEP
   - `HIPIFY_COMMIT_MESSAGE` constant ✅ KEEP
   - `TAG_HIPIFY_DIFFBASE` tagging logic in hipify functions ✅ KEEP

### Step 2: Update all four repository scripts

For each of: pytorch_torch_repo.py, pytorch_audio_repo.py, pytorch_vision_repo.py, pytorch_triton_repo.py:

1. Remove argument definitions:
   - `--patch-dir` argument
   - `--patchset` argument
   - `--patch` / `--no-patch` flag

2. Remove `save-patches` subcommand:
   - Remove subparser definition
   - Remove handler function call

3. Update docstrings:
   - Remove all mentions of patch application
   - Remove mentions of "base" vs "hipified" patches
   - Keep checkout and hipify documentation

4. Note: Default values for removed parameters can just be deleted

### Step 3: Update README.md

1. Replace section "Recommendation: avoid using patch files if possible" (~lines 337-354) with:
   ```markdown
   ### Removed Features

   **Patch File System (Removed)**: Previous versions of TheRock supported applying
   git patches to PyTorch repositories. This system has been removed as ROCm-specific
   changes are now maintained in downstream git forks (e.g., ROCm/pytorch release
   branches) rather than as patch files. This approach provides better tooling support,
   easier conflict resolution, and clearer version control.
   ```

2. Remove these entire sections:
   - "About patch files and patchsets" (~lines 356-389)
   - "Checking out and applying patches" (~lines 391-434)
   - "Saving new patches" (~lines 436-485)

3. Update "Alternate branches / patch sets" section (~lines 487-585):
   - Remove all example commands that include `--patchset` flags
   - Remove explanations of patchset subdirectories
   - Keep information about ROCm release branches

### Step 4: Update CI workflows

**build_portable_linux_pytorch_wheels.yml**:
1. Remove `pytorch_patchset` from inputs section
2. Line ~173: Change from `./external-builds/pytorch/pytorch_triton_repo.py checkout --patch --patchset nightly` to `./external-builds/pytorch/pytorch_triton_repo.py checkout`
3. Line ~179: Change from `./external-builds/pytorch/pytorch_torch_repo.py checkout --gitrepo-origin https://github.com/ROCm/pytorch.git --repo-hashtag ${{ inputs.pytorch_git_ref }} --patchset ${{ inputs.pytorch_patchset }}` to `./external-builds/pytorch/pytorch_torch_repo.py checkout --gitrepo-origin https://github.com/ROCm/pytorch.git --repo-hashtag ${{ inputs.pytorch_git_ref }}`

**build_windows_pytorch_wheels.yml**:
1. Remove `pytorch_patchset` from inputs section
2. Line ~198: Remove `--patchset ${{ inputs.pytorch_patchset }}` from pytorch_torch_repo.py invocation

**release_portable_linux_pytorch_wheels.yml**:
1. Remove `pytorch_patchset` from matrix strategy (if mapping patchsets to versions)
2. Remove `pytorch_patchset: ${{ ... }}` from workflow call parameters

**release_windows_pytorch_wheels.yml**:
1. Remove `pytorch_patchset` from matrix strategy (if mapping patchsets to versions)
2. Remove `pytorch_patchset: ${{ ... }}` from workflow call parameters

## Testing Strategy

### Before submitting PR:

1. **Syntax verification**: Ensure Python files have no syntax errors
   ```bash
   python -m py_compile external-builds/pytorch/repo_management.py
   python -m py_compile external-builds/pytorch/pytorch_torch_repo.py
   python -m py_compile external-builds/pytorch/pytorch_audio_repo.py
   python -m py_compile external-builds/pytorch/pytorch_vision_repo.py
   python -m py_compile external-builds/pytorch/pytorch_triton_repo.py
   ```

2. **Functional testing**: Test checkout commands still work
   ```bash
   cd external-builds/pytorch
   python pytorch_torch_repo.py checkout --repo-hashtag main
   python pytorch_audio_repo.py checkout --require-related-commit
   python pytorch_vision_repo.py checkout --require-related-commit
   python pytorch_triton_repo.py checkout
   ```

3. **Help text verification**: Ensure removed parameters don't appear in help
   ```bash
   python pytorch_torch_repo.py checkout --help
   python pytorch_torch_repo.py --help
   ```

4. **Workflow validation**: Use GitHub's workflow validator or local act tool to verify YAML syntax

### After PR merge:

1. Monitor CI workflow runs for any failures
2. Verify PyTorch wheel builds complete successfully
3. Confirm no references to `--patchset`, `--patch-dir`, or `save-patches` remain

## Risk Mitigation

**Risk**: Breaking CI workflows
- **Mitigation**: All workflow changes included in same PR; tested before merge

**Risk**: External scripts depending on removed parameters
- **Mitigation**: Low risk as patch system was unused (no patches/ directory exists)

**Risk**: Confusion about windows_patch_fat_wheel.py
- **Mitigation**: Not touching that file (it patches wheel files, not git repos)

## Success Criteria

- ✅ All patch-related functions removed from repo_management.py
- ✅ All four repo scripts have no patch-related arguments or subcommands
- ✅ README.md updated with migration note, patch sections removed
- ✅ All CI workflows updated to not use `--patchset` or `--patch` flags
- ✅ Checkout commands work without errors
- ✅ CI workflows build PyTorch wheels successfully
- ✅ No pytest test failures

## Files NOT Modified

- `external-builds/pytorch/windows_patch_fat_wheel.py` - UNRELATED (patches wheel files, not git repos)
- `external-builds/pytorch/build_prod_wheels.py` - No patch flags in invocations
- `external-builds/pytorch/checkout_pytorch_all.sh` - No patch flags in invocations
- Any actual .patch files in src/pytorch/ - These are part of upstream PyTorch's third-party deps
