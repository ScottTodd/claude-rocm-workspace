# Style Review: PR #2851

* **PR:** [#2851 - Enable Linux FBGEMM_GENAI by default for all pytorch versions](https://github.com/ROCm/TheRock/pull/2851)
* **Author:** @araravik-psd (Aravind Ravikumar)
* **Review Type:** Style
* **Reviewed:** 2026-01-12
* **Base Branch:** main

---

## Summary

This PR simplifies the FBGEMM_GENAI configuration logic in `external-builds/pytorch/build_prod_wheels.py` by enabling FBGEMM_GENAI by default on Linux for all PyTorch versions, rather than only for PyTorch 2.9.x. The change removes version-specific conditional logic and related warnings.

**Net changes:** +6 lines, -30 lines across 1 file

---

## Overall Assessment

**✅ APPROVED** - The style changes are clean and follow project conventions.

**Strengths:**

- Significant simplification of conditional logic (removes complex version-checking)
- Consistent code formatting
- Clear, simple control flow that's easy to understand
- Reduces 30 lines to 6 lines while maintaining functionality

**Issues:** None blocking or important.

---

## Detailed Review

### 1. `external-builds/pytorch/build_prod_wheels.py`

#### 💡 SUGGESTION: Inconsistent print indentation

The new code has inconsistent indentation in print statements:

```python
if args.enable_pytorch_fbgemm_genai_linux is False:
    use_fbgemm_genai = "OFF"
    print("  FBGEMM_GENAI explicitly disabled by user.")  # Has leading spaces
else:
    use_fbgemm_genai = "ON"
    print("FBGEMM_GENAI enabled by default.")  # No leading spaces
```

The first print has `"  "` (two leading spaces) while the second has none. Looking at the surrounding code context (the line `print(f"  Using PYTORCH_BUILD_VERSION: {pytorch_build_version}")` above), other prints in this function use two leading spaces for consistency.

**Recommendation:** Add two leading spaces to the "enabled" message for consistency:
```python
print("  FBGEMM_GENAI enabled by default.")
```

#### 💡 SUGGESTION: Consider f-string format for consistency

The messages were simplified from f-strings to plain strings:
- Old: `print(f"  [WARN] User-requested override to set FBGEMM_GENAI = OFF.")`
- New: `print("  FBGEMM_GENAI explicitly disabled by user.")`

This is fine since there are no interpolated values, but the surrounding code uses f-strings for similar messages. Both approaches work, and removing f-strings where not needed is actually slightly more efficient.

**No action required** - This is just noting the style choice is acceptable.

#### 💡 SUGGESTION: The `[WARN]` prefix was removed

The original code used `[WARN]` prefixes for user messages. The new code removed these. This is fine as the messages are now informational rather than warnings (since enabling FBGEMM_GENAI is now the default expected behavior rather than a potential problem).

**No action required** - The semantic change in messaging matches the semantic change in functionality.

---

## Recommendations

### ❌ REQUIRED Before Human Review (Blocking):

None.

### ✅ Recommended Before Human Review:

None.

### 💡 Consider:

1. **Print indentation consistency:** Add two leading spaces to `print("FBGEMM_GENAI enabled by default.")` to match other print statements in the function.

### 📋 Future Follow-up:

None.

---

## Testing Recommendations

No style-specific testing required. The functional changes should be tested per the PR description (which references passing CI runs).

---

## Conclusion

**Approval Status: ✅ APPROVED**

The code style is clean and consistent with the project. The simplification is well-done, removing unnecessary complexity while maintaining clear, readable code. The only suggestion is a minor print indentation inconsistency that doesn't affect functionality.

The PR is ready for human review from a style perspective.
