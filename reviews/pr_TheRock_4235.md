# PR Review: Add THEROCK_DEV_PROJECTS option to rebuild subprojects that are not triggered

* **PR:** [#4235](https://github.com/ROCm/TheRock/pull/4235)
* **Author:** aobolensk (Arseniy Obolenskiy)
* **Base:** `main` ← `dev-projects-option`
* **Reviewed:** 2026-04-02
* **Status:** OPEN

---

## Summary

Adds a `THEROCK_DEV_PROJECTS` CMake variable that accepts a semicolon-separated list of subproject names whose inner build should always be invoked. This solves a known pain point: large subprojects like `amd-llvm` cannot use source file globbing (the monorepo is too large), so changes to inner source files go undetected by the outer build system.

The mechanism uses a sentinel file that is touched *after* the build stamp, keeping it perpetually newer and forcing CMake to re-run the build command on every invocation. The inner build system (ninja) then determines what actually needs rebuilding.

**Net changes:** +32 lines, -3 lines across 4 files

---

## Overall Assessment

**✅ APPROVED** - Clean, well-scoped developer ergonomics improvement.

**Strengths:**

- The sentinel-after-stamp trick is elegant and correct — it forces the outer build to invoke the inner build, but the inner build's own dependency tracking avoids unnecessary recompilation
- Good documentation update in `build_system.md`
- Updates the existing comment in `compiler/CMakeLists.txt` that specifically asked for this feature
- No CI impact — this is OFF by default and only activated by explicit developer opt-in

**Issues:**

- One correctness concern with `file(TOUCH)` at configure time (see below)

---

## Detailed Review

### 1. cmake/therock_subproject.cmake — Sentinel mechanism

The core approach is sound:

1. `file(TOUCH "${_dev_sentinel}")` creates the sentinel at configure time
2. The build stamp `DEPENDS` on the sentinel
3. After touching the build stamp, the sentinel is touched again (`_build_post_stamp_commands`)
4. On the next build, sentinel is newer than stamp → inner build is always invoked

### ⚠️ IMPORTANT: `file(TOUCH)` runs at configure time, not build time

`file(TOUCH "${_dev_sentinel}")` executes during CMake configure. This means:

- After a fresh configure, the sentinel exists and has a timestamp
- If the user runs `ninja` immediately, the build stamp doesn't exist yet, so the build runs regardless (fine)
- After the first build, the post-stamp touch keeps the cycle going (fine)

The concern: if the user runs `cmake --build` without reconfiguring, and the sentinel was created during a *previous* configure that's older than the current build stamp, the sentinel might not be newer than the stamp. However, this scenario shouldn't occur in practice because:
- The first build always touches the sentinel via `_build_post_stamp_commands`
- After that, the sentinel is always newer than the stamp

So this works correctly. But there's a minor edge case: if someone manually deletes the sentinel file without reconfiguring, the `DEPENDS` reference becomes a missing file. CMake's behavior with missing dependencies in `add_custom_command` is to always trigger the rebuild, which is actually the desired behavior here — so even this edge case is fine.

**Verdict:** The mechanism is correct. No action needed.

### 2. cmake/therock_subproject.cmake — Code structure

### 💡 SUGGESTION: Use `IN LIST` instead of `list(FIND)`

Modern CMake (3.3+) supports the `IN LIST` operator for `if()`:

```cmake
if(THEROCK_DEV_PROJECTS AND target_name IN_LIST THEROCK_DEV_PROJECTS)
  set(_is_dev_project TRUE)
endif()
```

This replaces the `list(FIND)` + index check pattern and is more idiomatic. Note: requires `cmake_policy(SET CMP0057 NEW)` or `cmake_minimum_required(VERSION 3.3)`, which TheRock already satisfies.

### 3. compiler/CMakeLists.txt — Comment update

Clean update. The old comment said "Consider having a project dev mode option" — now it points to the concrete solution. Good.

### 4. docs/development/build_system.md — Documentation

### 💡 SUGGESTION: Add usage example in documentation

The documentation explains what the variable does but doesn't show the full configure command. A usage example would help:

```markdown
Example: always rebuild the compiler during local development:
```
cmake -B build -S . -DTHEROCK_DEV_PROJECTS="amd-llvm"
```
```

The PR description includes `-DTHEROCK_DEV_PROJECTS="amd-llvm"` as a test result, but having it in the docs would be helpful for discoverability.

### 5. CMakeLists.txt — Cache variable declaration

The `set(... CACHE STRING ...)` declaration is appropriate. The help string is clear and descriptive.

---

## Recommendations

### ❌ REQUIRED (Blocking):

None.

### ✅ Recommended:

1. Consider using `IN_LIST` instead of `list(FIND)` for more idiomatic CMake

### 💡 Consider:

1. Add a concrete usage example (full cmake configure line) to the `build_system.md` docs

### 📋 Future Follow-up:

1. Other large subprojects that skip source globbing could document `THEROCK_DEV_PROJECTS` as the recommended workflow (grep for similar "too large to glob" comments)

---

## Testing Recommendations

- Configure with `-DTHEROCK_DEV_PROJECTS="amd-llvm"`, build, modify an inner source file, rebuild — verify inner build is invoked
- Configure *without* the option, verify no behavior change (no sentinel files created, no forced rebuilds)
- Test with multiple projects: `-DTHEROCK_DEV_PROJECTS="amd-llvm;amd-comgr"` — verify both are always rebuilt

---

## CI Evidence

CI failures (Windows math-libs, some Linux tests) appear to be pre-existing/unrelated — this PR only adds a developer-opt-in CMake variable with no impact when unset. The `CI Summary` on the format/lint run passed.

---

## Conclusion

**Approval Status: ✅ APPROVED**

This is a clean, well-motivated developer ergonomics feature that solves a documented pain point. The sentinel mechanism is correct, the change is safe (opt-in only), and documentation is included. The two suggestions (idiomatic CMake, usage example) are minor improvements that don't block merge.
