# Branch Review: test-rocm-python

* **Branch:** `test-rocm-python`
* **Base:** `main`
* **Reviewed:** 2026-01-26
* **Commits:** 4 commits

---

## Summary

This branch adds a new GitHub Actions workflow `test_rocm_wheels.yml` that installs ROCm Python wheels from a pip index and runs `rocm-sdk test` to verify package integrity. This enables testing of published wheels (nightlies/dev releases) without requiring the full PyTorch test suite.

**Net changes:** +105 lines across 1 file

---

## Overall Assessment

**✅ APPROVED** - The workflow follows established patterns from `test_pytorch_wheels.yml`, uses minimal permissions, pins actions to SHAs, and correctly supports both `workflow_dispatch` and `workflow_call` triggers.

**Strengths:**

- Follows existing workflow patterns closely (test_pytorch_wheels.yml)
- Minimal permissions (`contents: read`)
- Actions pinned to commit SHAs with version comments
- Reuses existing `setup_venv.py` tooling
- Supports both manual dispatch and reusable workflow triggers

**No Blocking Issues**

---

## Detailed Review

### 1. Workflow Structure

The workflow correctly supports both trigger types:
- `workflow_dispatch` - for manual testing
- `workflow_call` - for integration with other workflows

The `inputs` context works for both trigger types in GitHub Actions, so this is correctly implemented.

### 2. Input Definitions

**💡 SUGGESTION: Add description for python_version**

The `python_version` input in `workflow_dispatch` lacks a description, while other inputs have descriptions:

```yaml
      python_version:
        required: true
        type: string
        default: "3.12"
```

Consider adding a description for consistency:
```yaml
      python_version:
        description: Python version to use
        required: true
        type: string
        default: "3.12"
```

### 3. Environment Variables

**💡 SUGGESTION: AMDGPU_FAMILY env var may be unused**

The job sets `AMDGPU_FAMILY` as an environment variable:

```yaml
    env:
      VENV_DIR: ${{ github.workspace }}/.venv
      AMDGPU_FAMILY: ${{ inputs.amdgpu_family }}
```

This variable doesn't appear to be used in any step. It may be intended for `rocm-sdk test` or future use. If it's not needed, consider removing it to avoid confusion. If it is needed (e.g., `rocm-sdk test` reads it), consider adding a comment explaining why.

### 4. Container Configuration

The container conditional uses the same pattern as `test_pytorch_wheels.yml`:

```yaml
    container:
      image: ${{ contains(inputs.test_runs_on, 'linux') && 'ghcr.io/rocm/...' || null }}
```

This correctly uses a container only for Linux runners. The container image is pinned to a specific SHA digest.

### 5. Actions Pinning

Both actions are correctly pinned to commit SHAs with version comments:

```yaml
uses: actions/checkout@8e8c483db84b4bee98b60c0593521ed34d9990e8 # v6.0.1
uses: actions/setup-python@83679a892e2d95755f2dac6acb0bfd1e9ac5d548 # v6.1.0
```

### 6. Permissions

Permissions are minimal and explicit:

```yaml
permissions:
  contents: read
```

---

## Recommendations

### ❌ REQUIRED Before Human Review (Blocking):

None.

### ✅ Recommended Before Human Review:

None.

### 💡 Consider:

1. Add a description for the `python_version` input for consistency
2. Either remove `AMDGPU_FAMILY` env var if unused, or add a comment explaining its purpose

### 📋 Future Follow-up:

1. Test the workflow via `workflow_dispatch` with actual nightly wheels after merging
2. Integrate with build workflows via `workflow_call` once S3 upload is implemented

---

## Testing Recommendations

Before merging, test the workflow via:

1. **workflow_dispatch**: Manually trigger from GitHub UI with:
   - `amdgpu_family`: `gfx94X-dcgpu`
   - `package_index_url`: `https://rocm.nightlies.amd.com/v2`
   - `rocm_version`: (look up a recent nightly version)
   - `python_version`: `3.12`
   - `test_runs_on`: `linux-mi325-1gpu-ossci-rocm-frac`

2. After successful dispatch test, the workflow is ready for `workflow_call` integration.

---

## Conclusion

**Approval Status: ✅ APPROVED**

The workflow is well-structured and follows project conventions. The suggestions are minor improvements that don't block approval. The workflow should be tested via `workflow_dispatch` after merging to verify it works with actual nightly wheels.
