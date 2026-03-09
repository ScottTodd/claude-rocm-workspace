---
repositories:
  - therock
---

# CLR HostQueue::finish() hang regression test

- **Status:** Blocked
- **Priority:** P2 (Medium)
- **Started:** 2026-03-09

## Overview

Add a regression test for rocm-systems PR #3790 ("Don't wait on command
completion if worker thread is destroyed"). The fix adds an early return in
`HostQueue::finish()` when `!AMD_DIRECT_DISPATCH && !Os::isThreadAlive(thread_)`,
preventing a hang during process exit on Windows.

## Context

### The bug

During process exit on Windows, `ExitProcess` kills all non-main threads before
running atexit handlers. The atexit path through `__hipUnregisterFatBinary` calls
`SyncAllStreams` → `HostQueue::finish()`, which calls `awaitCompletion()` on a
dead worker thread and hangs forever. PyTorch hits this reliably.

Key call chain (`hip_platform.cpp:310-325`):
```
__hipUnregisterFatBinary → SyncAllStreams(true) → finish() → awaitCompletion() [HANGS]
```

### The fix (PR #3790)

```cpp
if (!AMD_DIRECT_DISPATCH && !Os::isThreadAlive(thread_)) {
  command->release();
  return;
}
```

### Related

- PR: https://github.com/ROCm/rocm-systems/pull/3790
- `AMD_DIRECT_DISPATCH` defaults to false on Windows (worker thread mode)
  and true on Linux (direct dispatch, no worker thread)

## Test approach

A subprocess-based test following the existing `hipStreamLegacy_exe` pattern in
`hip-tests/catch/unit/stream/`. A standalone HIP program queues async GPU work
and exits without explicit sync/cleanup. The atexit handler must handle the dead
worker thread gracefully. The Catch2 driver spawns it via `SpawnProc` and asserts
exit code 0.

### Files written (on branch `clr-windows-hang-test` in rocm-systems)

- `projects/hip-tests/catch/unit/stream/hipGracefulExit_exe.cc` — standalone exe
- `projects/hip-tests/catch/unit/stream/hipGracefulExit.cc` — Catch2 test case
- `projects/hip-tests/catch/unit/stream/CMakeLists.txt` — build wiring

### How to run

```bash
cd /d/projects/TheRock/build/core/hip-tests/build
ctest -R Unit_hipStream_GracefulExitWithPendingWork --timeout 30
```

## Blockers

### Running hip-tests locally on Windows

The hip-tests subproject isn't well set up for local dev iteration:

1. **DLL discovery**: `StreamTest.exe` and `hipGracefulExit_exe.exe` fail to load
   `amdhip64_7.dll` at runtime. The DLL lives in `build/core/clr/stage/bin/` but
   isn't on PATH.
2. **CI approach**: In CI, `test_hiptests.py`
   (`build_tools/github_actions/test_executable_scripts/test_hiptests.py`) handles
   setting up the runtime environment. Locally there's no equivalent convenience.
3. **Reconfiguration**: Changes to hip-tests source files require reconfiguring
   the ExternalProject, which means either `ninja hip-tests+expunge && ninja hip-tests+dist`
   or manually running cmake in the subproject build dir.

### Potential fixes

- Set PATH to include `build/core/clr/stage/bin/` before running tests
- Check what `test_hiptests.py` does and replicate locally
- Consider adding a cmake wrapper or script for local hip-tests iteration

## Next steps

1. [ ] Figure out the right PATH / environment to run hip-tests locally
2. [ ] Verify the test hangs before the fix and passes after
3. [ ] Propose the test upstream alongside PR #3790 (or as a follow-up PR)
4. [ ] Consider whether Linux testing (with `AMD_DIRECT_DISPATCH=0`) is needed
