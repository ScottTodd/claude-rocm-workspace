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

On Linux, the CLR uses the HSA (ROCR) runtime backend. The `RuntimeTearDown`
global destructor (`clr/rocclr/platform/runtime.cpp` line ~114) runs registered
teardown callbacks and calls `Runtime::tearDown()` → `Hsa::shut_down()`. This
properly drains and cleans up GPU work.

**On Windows, the runtime stack is entirely different: CLR uses PAL (Platform
Abstraction Layer), not HSA/ROCR.** PAL is AMD's proprietary GPU abstraction
used by their Windows driver stack. The teardown paths, device management, and
stream synchronization all go through PAL rather than HSA.

Additionally, the `RuntimeTearDown` destructor body is compiled out on Windows:

```cpp
RuntimeTearDown::~RuntimeTearDown() {
#if !defined(_WIN32) && !defined(BUILD_STATIC_LIBS)
  // ... full teardown (HSA path) ...
  Runtime::tearDown();
#endif
}
```

Instead, Windows relies on `DllMain(DLL_PROCESS_DETACH)` in
`clr/hipamd/src/hip_runtime.cpp`, which only calls `ihipDestroyDevice()` (deletes
device handles via PAL). This is far less thorough — no stream draining, no
orderly PAL device shutdown.

**Important:** Because Windows uses PAL, the hang likely involves PAL-level
stream/fence synchronization primitives, not HSA signals. Debugging will need
to look at PAL's wait mechanisms, not HSA's.

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

Strategy: progressively narrow from "PyTorch hangs" to a minimal C/C++ HIP
reproducer that can be handed to the PAL or CLR teams. Each phase produces
concrete evidence that guides the next. Stop early if a phase already reveals
the fix.

### Phase 1: Observe the Hang (no source changes)

**Goal:** Get hard evidence of where the process is stuck.

1. **Get a stack trace of the hung process**
   - Run the 3-line Python repro, wait for hang
   - Attach WinDbg or Process Explorer to the hung `python.exe`
   - `~*k` in WinDbg to dump all thread stacks
   - Record which function(s) are blocked and in which DLL
   - Note: attaching to an already-hung process should be fine — the heisenbug
     (termination when `breakpoint()` is added) shouldn't apply post-mortem

2. **Use AMD logging to trace the shutdown sequence**
   - `AMD_LOG_LEVEL=4` — verbose HIP/CLR logging
   - `HIP_TRACE_API=1` — trace HIP API calls
   - Look for the last log line before silence (= the hang point)
   - Does `__hipUnregisterFatBinary` appear? `SyncAllStreams`? Something else?

**Checkpoint:** After Phase 1 we should know the specific function and DLL where
the hang occurs. If it's not where we expect, reassess before continuing.

### Phase 2: Build a Minimal C++ Reproducer

**Goal:** Strip away PyTorch and reproduce the hang with pure HIP C++ code.

3. **Understand what `torch.randn(1, 1, device="cuda")` does at the HIP level**
   - Use `HIP_TRACE_API=1` output from Phase 1 to get the sequence of HIP calls
   - Key calls are likely: `hipSetDevice`, `hipMalloc`, `hipLaunchKernel` (for
     the RNG kernel), and possibly `hipMemcpy` / `hipStreamCreate`
   - Note which calls are async (return before GPU work completes)

4. **Write a minimal HIP C++ program that reproduces the hang**
   - Start with just the HIP calls identified in step 3
   - Compile with `hipcc` on Windows, run, check if it hangs on exit
   - Iteratively simplify: remove calls until the hang disappears, then add
     the last one back — that's the trigger
   - Candidate minimal repro structure:
     ```cpp
     #include <hip/hip_runtime.h>
     int main() {
         hipSetDevice(0);
         void* ptr;
         hipMalloc(&ptr, sizeof(float));
         // launch a trivial kernel? just the alloc?
         // does it hang here on exit without hipDeviceSynchronize()?
         return 0;
     }
     ```
   - Test variants: with/without `hipDeviceSynchronize()` before return,
     with/without a kernel launch, with/without `hipFree`

5. **If pure HIP doesn't reproduce, try adding library calls**
   - `torch.randn` may go through rocRAND, MIOpen, or hipBLAS
   - Try adding `rocrand` calls to the C++ repro
   - Or try loading/unloading `amdhip64.dll` dynamically to simulate what
     Python's `ctypes.CDLL` does

**Checkpoint:** If we have a C++ reproducer, we can file it directly with the
CLR/PAL team. If we can't reproduce outside PyTorch, the bug may be in
PyTorch's specific usage pattern (e.g., atexit ordering, DLL load method).

### Phase 3: Narrow Within the Runtime

**Goal:** Pinpoint the mechanism — is it the sync, a lock, DLL ordering, etc.?

6. **If we have a C++ repro: instrument and vary**
   - Add `hipDeviceSynchronize()` before `return` — does it fix it? (matches
     the `torch.cuda.synchronize()` workaround)
   - Add `hipDeviceReset()` before `return` — does it fix it?
   - Try `_exit(0)` vs normal `return` — does `_exit` avoid the hang?
     (Tests whether the hang is in atexit handlers vs static destructors)
   - Vary compilation: static vs dynamic linking of HIP runtime

7. **If we don't have a C++ repro: narrow within PyTorch**
   - Write a C++ program that `LoadLibrary("torch_hip.dll")` and calls a
     minimal sequence through PyTorch's C++ API
   - Or write a Python extension (.pyd) that does the equivalent of `torch.randn`
     but with explicit HIP calls, to isolate whether PyTorch's Python layer
     matters
   - Check whether the bug requires PyTorch's atexit handlers to be registered

8. **Test specific hypotheses with CLR source changes**
   - Only after we understand the hang point from stack traces (Phase 1)
   - If `SyncAllStreams` in `__hipUnregisterFatBinary`: comment it out, test
   - If a PAL fence wait: add timeout logging
   - If a lock: check for deadlock (two threads, lock ordering)
   - Each change should be minimal and test one thing

**Checkpoint:** By now we should have either a root-cause-level understanding or
a clean reproducer + stack traces to hand off.

### Phase 4: Fix and Validate

**Goal:** Ship a fix and remove the workaround.

9. **Develop a fix in the appropriate layer**
   - If it's a CLR/PAL bug: fix in CLR, PR to ROCm/clr
   - If it's a PyTorch teardown ordering issue: fix in PyTorch, PR upstream
   - If it's a fundamental Windows DLL unload issue: may need a workaround
     at the PyTorch level (register an atexit sync) even if the root cause
     is in CLR

10. **Validate the fix**
    - Minimal C++ repro exits cleanly
    - Python 3-line repro exits cleanly
    - PyTorch unit tests complete without `os.kill` workaround
    - Test on available GPU architectures (gfx1100, gfx1151)

11. **Remove the TheRock workaround**
    - Remove `force_exit_with_code()` from `run_pytorch_tests.py`
    - Remove `*exit_code.txt` machinery from CI workflow
    - Update skip lists if any tests were skipped due to this bug

## Directories/Files Involved

```
# CLR / HIP runtime (likely fix location)
D:/projects/TheRock/rocm-systems/projects/clr/hipamd/src/hip_platform.cpp    # __hipUnregisterFatBinary + SyncAllStreams
D:/projects/TheRock/rocm-systems/projects/clr/hipamd/src/hip_runtime.cpp     # DllMain (DLL_PROCESS_DETACH)
D:/projects/TheRock/rocm-systems/projects/clr/hipamd/src/hip_device.cpp      # ihipDestroyDevice
D:/projects/TheRock/rocm-systems/projects/clr/rocclr/platform/runtime.cpp    # RuntimeTearDown (compiled out on Windows)

# PAL backend (Windows GPU abstraction — the actual runtime stack on Windows)
# PAL source is in the driver stack; need to identify relevant files for
# stream sync, fence wait, and device teardown

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
4. Windows uses PAL backend (not HSA) → teardown paths are entirely different
5. DLL unload order non-deterministic → PAL or runtime DLLs may be partially torn down
6. `os._exit()` doesn't work but `os.kill(SIGTERM)` does → suggests the hang is
   in a signal-interruptible wait (possibly a Windows event or PAL fence)

**Open question:** The `SyncAllStreams` hypothesis is based on source reading and
is plausible but unconfirmed. The actual hang point could be elsewhere in the PAL
stack. Phase 1 (stack traces) is essential before committing to a fix direction.

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

Phase 1 (no source changes needed):
1. [ ] Attach WinDbg to hung `python.exe` → get all-threads stack trace (`~*k`)
2. [ ] Run minimal repro with `AMD_LOG_LEVEL=4 HIP_TRACE_API=1` → capture log
3. [ ] From the HIP trace, extract the sequence of HIP API calls that `torch.randn` makes

Phase 2 (build a handoff-ready reproducer):
4. [ ] Write minimal HIP C++ program using the call sequence from step 3
5. [ ] Iterate: simplify until we have the smallest program that hangs
6. [ ] Confirm `hipDeviceSynchronize()` before return fixes the C++ repro too
