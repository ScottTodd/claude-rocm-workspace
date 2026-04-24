# Multi-Arch vs Legacy Release Timing Comparison

**Date:** 2026-04-24
**Multi-arch run:** [rockrel #24859053365](https://github.com/ROCm/rockrel/actions/runs/24859053365) (dev release, Apr 23)
**Legacy Linux:** [TheRock nightly](https://github.com/ROCm/TheRock/actions/workflows/release_portable_linux_packages.yml?query=branch%3Amain+event%3Aschedule) (Apr 22-23)
**Legacy Windows:** [TheRock nightly](https://github.com/ROCm/TheRock/actions/workflows/release_windows_packages.yml?query=branch%3Amain+event%3Aschedule) (Apr 22-23)

## Summary

| Pipeline | Linux wall | Windows wall | Combined wall | Runner-hours |
|----------|-----------|-------------|--------------|-------------|
| **Multi-arch** | 5h04m | 6h13m | **6h13m** | **66.3h** |
| Legacy Apr 23 | 5h23m | 5h05m | 5h23m | 102.6h |
| Legacy Apr 22 | 4h21m | 6h43m | 6h43m | 86.1h |

**Key takeaway:** Multi-arch uses **35% fewer runner-hours** (66h vs 103h) but has comparable or slightly worse wall time (6h13m vs 5h23m-6h43m range). The wall time penalty comes from build topology serialization, while the compute savings come from shared generic stages.

## Bottleneck Analysis

### 1. Build Topology Bottleneck (multi-arch specific)

The multi-arch pipeline has serial generic stages before per-family work can begin:

```
setup (0m) → foundation (4-5m) → compiler-runtime (45-52m) → math-libs (parallel)
                                                                    ↓
                                                              fusilli-libs (5m, waits for ALL)
                                                                    ↓
                                                              tarballs + python (17-22m)
```

This adds **~63m of serial overhead** to the critical path that legacy doesn't have (legacy starts all families immediately). However, this is offset by each family's build being shorter since generic stages are already done.

The **fusilli-libs barrier** is a second topology bottleneck: it must wait for the slowest math-libs family across all 14 families. The slowest family (gfx120X-all) gates everything downstream.

### 2. Windows gfx120X-all is the Overall Bottleneck

The single biggest bottleneck in the multi-arch run was **Windows math-libs gfx120X-all at 4h48m** — nearly double the next-slowest Windows family (gfx103X-all at 3h15m). This is also the bottleneck in legacy Windows (5h00m Apr 23, 6h38m Apr 22).

If gfx120X-all were comparable to other families (~3h), the multi-arch Windows wall time would drop from 6h13m to ~4h30m.

### 3. Per-Family Build Time Savings (Linux)

Multi-arch math-libs is consistently faster than legacy full-build per family because generic stages (foundation, compiler-runtime, comm-libs, profiler-apps, etc.) are shared:

| Family | MA math-libs | Legacy full | Savings |
|--------|-------------|------------|---------|
| gfx900 | 1h08m | 3h30m | +2h21m |
| gfx906 | 1h07m | 3h32m | +2h24m |
| gfx908 | 1h47m | 4h08m | +2h20m |
| gfx101X-dgpu | 1h25m | 4h51m | +3h25m |
| gfx94X-dcgpu | 3h29m | 5h08m | +1h39m |
| gfx120X-all | 3h31m | 5h14m | +1h42m |

Average savings: ~2h per family. With 14 families, that's ~28h of runner time saved — confirmed by the 35% reduction in runner-hours (66h vs 103h).

### 4. Runner Queue Delays

**Multi-arch:** No significant queue delays. All math-libs jobs started within ~1 minute of their dependency (compiler-runtime) completing. Fusilli started <1 minute after the slowest math-libs.

**Legacy Windows:** Some families saw 13-15 minute queue delays (gfx900, gfx908, gfx90a, gfx103X-all, gfx1152, gfx1153). This suggests the Windows runner pool was partially saturated when 12-13 jobs queued simultaneously. The multi-arch pipeline naturally spreads Windows runner demand over time (jobs start after compiler-runtime, not all at once).

**Legacy Linux:** Negligible queue delays (< 3 minutes).

### 5. Post-Build Overhead (multi-arch specific)

Multi-arch has additional post-build jobs not in legacy:
- Build Tarballs: 17-22m
- Build Python: 12-13m
- Publish: <1m (failed fast in this run — expected, no OIDC creds for dev)

These run after fusilli-libs and add ~22m to the Linux critical path and ~17m to Windows. Tarballs and Python run in parallel so the overhead is max(tarballs, python) ≈ 22m.

## Critical Path Comparison

### Multi-arch Linux (5h04m):
```
setup(0m) → foundation(4m) → compiler-runtime(52m) → math-libs gfx120X-all(3h31m) → fusilli(5m) → tarballs(22m)
= 4m gap + 4m + 4m gap + 52m + 1m gap + 3h31m + 0m gap + 5m + 0m gap + 22m = 5h04m
```

### Multi-arch Windows (6h13m):
```
foundation(5m) → compiler-runtime(45m) → math-libs gfx120X-all(4h48m) → tarballs(17m)
= 6h13m (runs parallel with Linux, but finishes later)
```

### Legacy Linux Apr 23 (5h23m):
```
gfx110X-all: 5h20m build (started 3m after run, finished at 5h23m wall)
```

### Legacy Windows Apr 23 (5h05m):
```
gfx120X-all: 5h00m build (started 5m after run, finished at 5h05m wall)
```

## Observations

1. **Wall time is dominated by the slowest family.** In both multi-arch and legacy, the overall wall time is determined by whichever single family takes longest. Multi-arch adds ~63m of serial generic overhead but saves that time (and more) per family. The net effect depends on whether the slowest family's savings exceed the overhead.

2. **gfx120X-all is an outlier on Windows.** At 4h48m it's 1h33m slower than the next-slowest family. Investigating why (ccache state? different target count? RCCL linking?) could reduce overall wall time significantly.

3. **Multi-arch saves substantial compute.** 35% fewer runner-hours means lower cost per release, which matters at scale (nightly * 14 families * 2 platforms).

4. **Legacy has high day-to-day variance.** Linux ranged from 4h21m to 5h23m across two consecutive days. Windows ranged from 5h05m to 6h43m. This is likely ccache variability. Multi-arch should be more stable since generic stages are built once.

5. **No runner queue bottleneck in multi-arch.** The staged job graph naturally distributes runner demand, avoiding the thundering-herd effect of legacy where all families queue simultaneously.

## Recommendations

1. **Investigate Windows gfx120X-all build time.** This family is the critical-path bottleneck for the entire release. Reducing it from 4h48m to ~3h would cut overall wall time by ~1h45m.

2. **Consider whether gfx120X-all needs separate investigation.** In legacy it's also the slowest Windows family (5h00m Apr 23, 6h38m Apr 22). The multi-arch version is actually faster (4h48m) but still dominates because of the topology barrier.

3. **The topology overhead is acceptable.** ~63m of serial generic stages saves ~2h per family in build time. With 14 families, the compute savings far outweigh the wall time cost. The fusilli barrier adds only 5m.

4. **Post-build jobs are cheap.** Tarballs (22m) and Python (13m) are minor compared to build time. No optimization needed here.
