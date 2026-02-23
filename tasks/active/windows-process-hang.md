---
repositories:
  - therock
---

# Debug Windows Process Hang on Exit (PyTorch + ROCm)

- **Status:** In progress
- **Priority:** P1 (High)
- **Started:** 2026-02-23
- **Target:** TBD

## Overview

PyTorch processes using ROCm on Windows complete their work correctly but never
terminate. The process hangs indefinitely after `main()` / the Python script
finishes. This affects unit tests, real programs, and trivial 3-line repros.

The current workaround in TheRock CI is to `os.kill(os.getpid(), signal.SIGTERM)`
after stashing the test return code to a file (commit beecb8cc). The goal is to
find and fix the root cause so this hack can be removed.

## Goals

- [ ] Confirm the exact hang location (stack trace of blocked thread)
- [ ] Identify root cause in CLR / HIP runtime / PyTorch shutdown
- [ ] Develop and test a fix (likely in CLR or PyTorch)
- [ ] Remove the `os.kill` workaround from TheRock CI

## Context

### Tracking Issues

- Upstream: [pytorch/pytorch#160759](https://github.com/pytorch/pytorch/issues/160759)
- Downstream: [ROCm/TheRock#999](https://github.com/ROCm/TheRock/issues/999)
- Workaround commit: [beecb8cc](https://github.com/ROCm/TheRock/commit/beecb8cc8e908e430faff15c7d52cebb9b0f8feb) (PR #2265)
- Related: TheRock#1073 (Windows test triage), TheRock#2258 (Windows CI tests)

### Minimal Repro

```python
# HANGS — never terminates
import torch
tensor_gpu = torch.randn(1, 1, device="cuda")
```

```python
# WORKS — terminates normally
import torch
tensor_gpu = torch.randn(1, 1, device="cuda")
torch.cuda.synchronize()  # or print(tensor_gpu)
```

### Key Observations

- **Windows-only** — Linux ROCm does not have this problem
- **Reproduces across ROCm versions** — TheRock wheels, HIP SDK builds, 6.4.2–7.10
- **Reproduces across GPUs** — gfx1100 (W7900), gfx1151, RX 7900 XTX
- **Heisenbug under debugger** — adding `breakpoint()` causes normal termination
- **`sys.exit()` and `os._exit()` don't help** — only `os.kill(SIGTERM)` works
- **Any implicit sync fixes it** — `print(tensor)`, `torch.cuda.synchronize()`,
  `hipMemcpy` (GPU→CPU)

### Root Cause Analysis

Research into CLR, HIP runtime, and PyTorch source reveals a strong hypothesis:

#### The Shutdown Sequence

1. **Python exits** → runs `atexit` handlers → garbage collects → unloads modules
2. **C/C++ atexit handlers run** → includes `__hipUnregisterFatBinary`
3. **Static/global destructors run** (DLL unload order non-deterministic on Windows)
4. **OS reclaims resources**

#### The Smoking Gun: `__hipUnregisterFatBinary`

In `clr/hipamd/src/hip_platform.cpp` (line ~214), HIP's fat binary unregistration
handler calls:

```cpp
std::call_once(unregister_device_sync, []() {
  for (auto& hipDevice : g_devices) {
    hipDevice->SyncAllStreams(true);  // CPU-wait sync — BLOCKS HERE
  }
});
```

This `SyncAllStreams(true)` does a CPU-wait synchronization on ALL device streams.
If any stream has a pending async GPU operation that cannot complete (because the
runtime is partially torn down, or the DLL providing the operation has been
unloaded), this blocks forever.

#### Why Linux Doesn't Hang

On Linux, the CLR has a full `RuntimeTearDown` global destructor
(`clr/rocclr/platform/runtime.cpp` line ~114) that runs registered teardown
callbacks and calls `Runtime::tearDown()` → `Hsa::shut_down()`. This properly
drains and cleans up GPU work.

**On Windows, this entire teardown body is compiled out:**

```cpp
RuntimeTearDown::~RuntimeTearDown() {
#if !defined(_WIN32) && !defined(BUILD_STATIC_LIBS)
  // ... full teardown ...
  Runtime::tearDown();
#endif
}
```

Instead, Windows relies on `DllMain(DLL_PROCESS_DETACH)` in
`clr/hipamd/src/hip_runtime.cpp`, which only calls `ihipDestroyDevice()` (deletes
device handles). This is far less thorough — no stream draining, no HSA shutdown.

#### Why `torch.cuda.synchronize()` Fixes It

Calling `synchronize()` before exit drains all pending GPU work. When
`__hipUnregisterFatBinary` later calls `SyncAllStreams`, there's nothing left to
wait for, so it returns immediately.

#### Why the Debugger Fixes It (Heisenbug)

Likely timing-related: attaching a debugger or hitting `breakpoint()` introduces
enough delay for async GPU operations to complete naturally before the atexit
handler runs.

### Related PyTorch Patterns

PyTorch intentionally leaks many GPU resources to avoid shutdown crashes:
- Event pools (`c10/hip/HIPCachingAllocator.cpp`): `new EventPool()` never deleted
- Library handles (hipBLAS, MIOpen, etc.): destroy functions commented out
- Allocation traces: "can hold references to Python state which will already be destroyed"
- MIOpen PoolWindows: "lazily-initialized to avoid initialization issues that caused hangs on Windows"

This is a deliberate strategy — PyTorch relies on the OS to reclaim resources at
process exit rather than attempting orderly teardown (which has historically caused
crashes).

## Investigation Plan

### Phase 1: Confirm the Hypothesis

**Goal:** Prove the hang is in `SyncAllStreams` inside `__hipUnregisterFatBinary`.

1. **Get a stack trace of the hung process**
   - Use Process Explorer or WinDbg to attach to a hung `python.exe`
   - `~*k` in WinDbg to dump all thread stacks
   - Look for `SyncAllStreams`, `__hipUnregisterFatBinary`, or similar in the stack
   - Note: the "heisenbug" behavior with `breakpoint()` might not apply to
     post-mortem attach — attaching to an already-hung process should be fine

2. **Use AMD logging to trace shutdown**
   - `AMD_LOG_LEVEL=4` — verbose HIP runtime logging
   - `HIP_TRACE_API=1` — trace all HIP API calls
   - Look for the last HIP call before the hang
   - Check if `__hipUnregisterFatBinary` appears in the log

3. **Instrument `__hipUnregisterFatBinary` directly**
   - Add `fprintf(stderr, ...)` before and after `SyncAllStreams` in
     `clr/hipamd/src/hip_platform.cpp`
   - Rebuild CLR/HIP and test with the minimal repro
   - Confirm whether the hang is before, during, or after the sync

### Phase 2: Narrow the Root Cause

**Goal:** Understand WHY `SyncAllStreams` hangs.

4. **Check what's pending on the streams**
   - Add logging inside `SyncAllStreams` to print stream count, pending operations
   - Is it waiting on a specific stream? A specific operation type?
   - Does the underlying `hipStreamSynchronize` or PAL-level wait actually hang,
     or is it some higher-level locking issue?

5. **Test with `__hipUnregisterFatBinary` sync disabled**
   - Comment out the `SyncAllStreams` call in `__hipUnregisterFatBinary`
   - Does the process exit cleanly? Does it crash instead?
   - This tells us whether the sync is the proximate cause vs a symptom

6. **Compare DLL unload order**
   - Use Loader Snaps (`gflags +sls`) or Process Monitor to trace DLL unload
   - Is `hsa-runtime64.dll` or `amd_comgr.dll` being unloaded before
     `amdhip64.dll` finishes its atexit handler?
   - DLL unload order on Windows is non-deterministic and a known source of
     shutdown bugs

7. **Test the RuntimeTearDown hypothesis**
   - Remove the `!defined(_WIN32)` guard from `RuntimeTearDown::~RuntimeTearDown()`
   - Does enabling the full Linux-style teardown on Windows fix the hang?
   - Or does it crash (which would explain why it was disabled)?

### Phase 3: Develop a Fix

Based on Phase 2 findings, likely approaches (in order of preference):

8. **Fix A: Remove or guard the `SyncAllStreams` in `__hipUnregisterFatBinary`**
   - If the sync is unnecessary on Windows (since the OS reclaims GPU resources),
     skip it with `#if !defined(_WIN32)` or make it non-blocking
   - Simplest fix, lowest risk

9. **Fix B: Enable `RuntimeTearDown` on Windows**
   - If the proper teardown sequence makes the sync work correctly, enable it
   - Higher risk — may need to handle DLL unload ordering carefully

10. **Fix C: Add `torch.cuda.synchronize()` to PyTorch's atexit**
    - Register a Python atexit handler that syncs all devices before CLR's atexit
    - Workaround at the PyTorch level — doesn't fix the HIP runtime bug
    - But pragmatic if the CLR fix takes time to land

11. **Fix D: Use `TerminateProcess` instead of waiting**
    - In `__hipUnregisterFatBinary`, if running during process exit (detectable
      via `DLL_PROCESS_DETACH` reserved parameter), skip the sync
    - Standard Windows pattern: many libraries skip cleanup during process exit

### Phase 4: Validate and Upstream

12. **Run PyTorch unit tests without the `os.kill` workaround**
13. **Test on multiple GPU architectures** (gfx1100, gfx1151)
14. **Submit fix PR** to appropriate repo (CLR or PyTorch)
15. **Remove TheRock workaround** once fix is available

## Directories/Files Involved

```
# CLR / HIP runtime (likely fix location)
D:/projects/TheRock/rocm-systems/projects/clr/hipamd/src/hip_platform.cpp    # __hipUnregisterFatBinary
D:/projects/TheRock/rocm-systems/projects/clr/hipamd/src/hip_runtime.cpp     # DllMain
D:/projects/TheRock/rocm-systems/projects/clr/hipamd/src/hip_device.cpp      # ihipDestroyDevice
D:/projects/TheRock/rocm-systems/projects/clr/rocclr/platform/runtime.cpp    # RuntimeTearDown

# PyTorch (alternative fix location)
# torch/csrc/cuda/Module.cpp    # CUDA/HIP module init
# c10/hip/HIPCachingAllocator.cpp  # Caching allocator, event pools

# TheRock workaround (to be removed after fix)
D:/projects/TheRock/external-builds/pytorch/run_pytorch_tests.py             # force_exit_with_code()
```

## Investigation Notes

### 2026-02-23 - Initial Research

Gathered information from both GitHub issues and deep-dived into CLR source.
Strong hypothesis formed around `SyncAllStreams` in `__hipUnregisterFatBinary`.

Key evidence chain:
1. `torch.cuda.synchronize()` fixes the hang → pending async work is the trigger
2. `RuntimeTearDown` is compiled out on Windows → no proper stream draining
3. `__hipUnregisterFatBinary` atexit handler calls `SyncAllStreams(true)` → blocks
4. DLL unload order non-deterministic → runtime may be partially torn down
5. `os._exit()` doesn't work but `os.kill(SIGTERM)` does → suggests the hang is
   in a signal-interruptible wait (possibly a Windows event or semaphore)

## Blockers & Issues

### Potential Blockers
- **Need Windows machine with AMD GPU** — can't reproduce on Linux
- **CLR rebuild cycle time** — iterating on HIP runtime changes requires rebuilding CLR
- **Heisenbug with debugger** — may need non-invasive debugging (logging, ETW traces)

## Resources & References

- [pytorch/pytorch#160759](https://github.com/pytorch/pytorch/issues/160759) — upstream tracking
- [ROCm/TheRock#999](https://github.com/ROCm/TheRock/issues/999) — downstream tracking
- [ROCm/ROCm#3418](https://github.com/ROCm/ROCm/issues/3418) — HIP programs hang in amdhip64.dll after main
- [Win32 DLL unload ordering](https://devblogs.microsoft.com/oldnewthing/20070503-00/?p=27003) — Raymond Chen's classic post
- [UCRT surprise at exit: static variables destruction deadlock](https://victor-istomin.github.io/c-with-crosses/posts/surprise-at-exit/)
- `clr/hipamd/src/hip_platform.cpp` — `__hipUnregisterFatBinary` with `SyncAllStreams`
- `clr/rocclr/platform/runtime.cpp` — `RuntimeTearDown` (compiled out on Windows)

## Next Steps

1. [ ] Attach WinDbg/Process Explorer to hung `python.exe` and get stack traces
2. [ ] Run minimal repro with `AMD_LOG_LEVEL=4` to see shutdown sequence
3. [ ] Instrument `__hipUnregisterFatBinary` with logging and rebuild CLR
4. [ ] Test with `SyncAllStreams` disabled on Windows
