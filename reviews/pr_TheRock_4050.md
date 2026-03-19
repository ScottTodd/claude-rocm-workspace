# PR Review: [ci] Enabling memory monitor for CI builds and tests

* **PR:** https://github.com/ROCm/TheRock/pull/4050
* **Author:** geomin12 (Geo Min)
* **Base:** `main` ← `users/geomin12/resource-monitor`
* **Reviewed:** 2026-03-19
* **Status:** OPEN

---

## Summary

Adds a `memory_monitor.py` script that wraps CI build/test commands, periodically logging system resource usage (memory, CPU, GPU, disk) to stdout. The script is integrated into 5 workflow files (Linux build, Windows build, multi-arch Linux/Windows builds, test component). The goal is to capture resource data incrementally during builds so that when a runner OOM-kills, there's already diagnostic output in the logs.

**Net changes:** +398 lines, -5 lines across 8 files

---

## Overall Assessment

**⚠️ CHANGES REQUESTED** - The concept is sound and addresses a real debugging need. However, there are blocking issues around Windows signal handling, a behavioral change in test_component.yml that could break test scripts, and missing `psutil` availability in the multi-arch build workflows.

**Strengths:**

- Clean, well-structured Python script with good separation of concerns
- Sensible defaults (30s interval, 75%/90% thresholds)
- Summary statistics at end of run are valuable for post-mortem analysis
- Tests cover the core monitoring functionality
- Carries forward prior work from #2453

**Blocking Issues:**

1. `signal.SIGTERM` crashes on Windows
2. `bash -c` wrapping in test_component.yml changes behavior
3. Redundant `psutil` addition to `requirements.txt`

---

## Detailed Review

### 1. memory_monitor.py — Signal handling on Windows

### ❌ BLOCKING: `signal.SIGTERM` is not supported on Windows

`signal.signal(signal.SIGTERM, handle_signal)` raises `OSError` on Windows because `SIGTERM` is not a valid signal number there. This will crash the monitor before the build command even starts on all Windows build workflows.

**Required action:** Guard the signal registration:

```python
if sys.platform != "win32":
    signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)  # SIGINT works on all platforms
```

Or use `try/except (OSError, ValueError)` around both registrations.

---

### 2. test_component.yml — `bash -c` wrapping changes behavior

### ❌ BLOCKING: Wrapping test_script in `bash -c '...'` changes semantics

The original:
```yaml
run: |
  ${{ fromJSON(inputs.component).test_script }}
```

The new:
```yaml
run: |
  python ./build_tools/memory_monitor.py --phase "Test ${{ fromJSON(inputs.component).job_name }}" -- \
    bash -c '${{ fromJSON(inputs.component).test_script }}'
```

This has two problems:

1. **Single-quote escaping**: If `test_script` contains single quotes (e.g., `echo 'hello'` or paths with apostrophes), the `bash -c '...'` wrapper will break with a syntax error. The current test scripts may not contain single quotes today, but this is fragile.

2. **Multi-line scripts**: If `test_script` is multi-line, `bash -c 'line1\nline2'` collapses into a single argument. The original approach runs each line as a separate command in the workflow shell. `bash -c` receives the entire content as one string, which changes how shell parsing works (e.g., here-docs, continued lines).

3. **Windows tests**: The `test_component.yml` workflow is also used for Windows tests (see `runner.os == 'Windows'` checks). Wrapping in `bash -c` assumes a bash shell is available. While Windows runners on this repo use `shell: bash` as default, `subprocess.run(["bash", "-c", ...])` from Python may resolve a different bash (or none).

**Required action:** Consider an alternative wrapping approach. For example, the monitor could accept `--shell` mode where it reads the command from a file or stdin, or the workflow could write the test script to a temp file and pass it as an argument. At minimum, test with actual multi-line test scripts that currently exist in CI.

---

### 3. requirements.txt — Redundant psutil addition

### ⚠️ IMPORTANT: `psutil` is already in `requirements-test.txt`

`psutil==7.1.3` was already added to `requirements-test.txt` (line 18) prior to this PR. Adding it to `requirements.txt` as well creates two places to maintain the same pin.

For the build workflows that use `requirements.txt`, this addition is needed. However, the commit message and PR description should note that it was already present in `requirements-test.txt` for test contexts. This is not blocking, just worth noting.

---

### 4. memory_monitor.py — `argparse` positional + `--` handling

### ⚠️ IMPORTANT: `command` argument parsing with `--` is fragile

The parser uses:
```python
parser.add_argument("command", nargs="*")
```

And then manually strips `--`:
```python
if command and command[0] == "--":
    command = command[1:]
```

But `argparse` already handles `--` as a separator between options and positional args. The issue is that some commands being wrapped (like `cmake --build ... -- -k 0`) also use `--`. With `nargs="*"`, argparse will consume everything after the first `--` as positional args, which means the inner `-- -k 0` gets properly passed through. This works by accident but is worth a comment explaining why.

However, there's a real problem: if the wrapped command has flags that argparse might try to parse. For example:
```
python memory_monitor.py -- cmake --build build --target foo
```
Argparse sees `--build` after consuming `--` as positional, which works. But:
```
python memory_monitor.py cmake --build build
```
Without `--`, argparse would try to interpret `--build` as its own flag and fail.

The workflow YAML always uses `--`, so this works in practice, but `parse_known_args()` or `argparse.REMAINDER` would be more robust.

---

### 5. memory_monitor.py — `_collect_stats` called without lock

### 💡 SUGGESTION: Consider thread safety for `_collect_stats`

`_collect_stats()` calls `psutil.cpu_percent(interval=None)` which returns the CPU usage since the last call. Since both the initial call in `start()` and the background thread call it, there's no race condition per se (the daemon thread hasn't started yet during the initial call), but the first background sample will measure CPU since `start()` was called rather than since the last background sample.

This is minor and doesn't affect correctness of the monitoring data.

---

### 6. memory_monitor.py — GPU memory detection

### 💡 SUGGESTION: `rocm-smi --json` output format varies by version

The JSON parsing assumes `card_data` keys like `"VRAM Total Used Memory (B)"` and `"VRAM Total Memory (B)"`. These key names have changed across rocm-smi versions. The `try/except` block handles this gracefully (falls back to no GPU data), so it's not a bug, but worth a comment noting that the keys may need updating as ROCm versions change.

---

### 7. Tests — Timing-dependent assertions

### ⚠️ IMPORTANT: `test_monitor_start_stop` may be flaky

```python
monitor = ResourceMonitor(interval=0.1, phase="Test")
monitor.start()
time.sleep(0.5)
monitor.stop()
assert len(monitor.samples) >= 1
```

With interval=0.1 and sleep=0.5, you'd expect ~5-6 samples (1 initial + ~5 from loop). The assertion `>= 1` is very lenient and should pass. However, on overloaded CI runners, the thread may not get scheduled promptly.

The `test_responsive_shutdown` test is better designed with generous bounds (3s timeout for a stop operation).

This is likely fine in practice but worth noting.

---

### 8. Tests — Missing test for `run_with_monitor`

### ⚠️ IMPORTANT: No test for the main integration path

The function `run_with_monitor()` — which is the actual entry point used by CI — has no test. Key behaviors to test:
- Return code propagation (does a failing command return non-zero?)
- Monitor cleanup on command failure
- Signal handling behavior

The existing tests cover `ResourceMonitor` in isolation but not the subprocess wrapping.

---

### 9. Tests — Import path manipulation

### 💡 SUGGESTION: Use pytest discovery instead of `sys.path.insert`

```python
sys.path.insert(0, str(Path(__file__).parent.parent))
from memory_monitor import ResourceMonitor, get_storage_info, get_thread_info
```

Other test files in `build_tools/tests/` may use this pattern, but pytest's standard discovery with a `conftest.py` or running from the right directory would be cleaner. Low priority.

---

### 10. Workflow changes — Multi-arch builds

### 💡 SUGGESTION: Consider whether all workflows need monitoring

Both `multi_arch_build_portable_linux_artifacts.yml` and `multi_arch_build_windows_artifacts.yml` are modified. Since multi-arch builds are already per-stage (smaller), they may be less prone to OOM. The monitoring overhead (psutil calls every 30s, rocm-smi subprocess every 30s) is minimal, so this is fine — just noting that the primary value is in the full-build workflows.

---

## Recommendations

### ❌ REQUIRED (Blocking):

1. **Fix `signal.SIGTERM` on Windows** — Guard with platform check or try/except
2. **Fix `bash -c` wrapping in test_component.yml** — Current approach breaks on single quotes in test scripts and changes multi-line script semantics

### ✅ Recommended:

3. **Add test for `run_with_monitor` return code propagation** — This is the critical integration path
4. **Document argparse `--` behavior** — Add a comment explaining why the double-dash handling works

### 💡 Consider:

5. **Add comment about rocm-smi JSON key volatility**
6. **Use `argparse.REMAINDER` instead of `nargs="*"`** for robustness

### 📋 Future Follow-up:

7. **Structured output** — Consider writing JSON samples to a file (in addition to stdout) for programmatic post-processing of resource data across builds
8. **GitHub step summary** — The resource summary could be written to `$GITHUB_STEP_SUMMARY` for easier visibility

---

## Testing Recommendations

- Run the memory monitor manually on Windows to verify signal handling
- Test with an actual multi-line test script from CI to verify `bash -c` wrapping
- Verify that a failing wrapped command propagates its exit code correctly:
  ```bash
  python build_tools/memory_monitor.py -- bash -c 'exit 42'
  echo $?  # should be 42
  ```
- Check CI logs from the PR's CI run to verify resource data appears in build step output

---

## Conclusion

**Approval Status: ⚠️ CHANGES REQUESTED**

The memory monitor is a useful addition for diagnosing CI resource issues. The two blocking issues (Windows SIGTERM and bash -c wrapping) need to be addressed before merge. The SIGTERM fix is straightforward; the test_component.yml wrapping needs more thought about how to handle arbitrary test scripts safely.
