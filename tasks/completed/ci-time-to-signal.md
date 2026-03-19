---
repositories:
  - therock
---

# CI Time-to-Signal Analysis

- **Status:** Complete
- **Priority:** P1 (High)
- **Started:** 2026-03-19
- **Completed:** 2026-03-19

## Overview

CI workflows in TheRock are very slow (multi-hour builds, long runner queue times).
This impacts developer productivity — PRs merged prematurely, forced reverts, slow
iteration. Goal: collect timing data, identify trends and bottlenecks, bring data
to the team so they can productionize dashboards.

## Outcome

Built two scripts (`prototypes/ci-metrics/`) with a README, collected 30 days of
data (292 runs, 30,725 jobs), and generated 19 plots covering:

- Time to first failure vs completion (overall + per-platform)
- Build duration by variant (Linux, Windows)
- Test runner queue times by variant and runner label
- Queue time trends (build vs test runners)
- Failure rate, day-of-week patterns, hour-of-day patterns

### Key Findings (30-day snapshot, 2026-03-19)

| Metric | Median | Max |
|--------|--------|-----|
| Time to completion | 8h19m | 72h33m |
| Time to first failure | 2h09m | 60h34m |
| Max queue time | 2h28m | 43h39m |
| Failure rate | 69% (171/249) | — |

- **Linux builds** are stable at 1.5-2.3h. gfx94X-dcgpu is the slowest variant.
- **Windows builds** improved from ~8h to ~3-5h over the month (gfx110X-all had
  the biggest improvement). Recent regression back to ~6-9h around 03-12.
- **Test queue times** were catastrophic in mid-Feb (gfx950-dcgpu hitting 40h+),
  resolved by 02-24. Recent queue pressure from mi355 runners (2-5h).
- **Time to first failure** is relatively stable at ~2-3h on Linux regardless of
  completion time. On Windows it tracks closer to completion time (~1-2h gap)
  since failures tend to happen during the build phase itself.

### Data & Plots

Snapshot stored in `prototypes/ci-metrics/data/2026-03-19/`.
See `prototypes/ci-metrics/README.md` for usage instructions.

## Goals

- [x] Write a script that queries the GitHub API for workflow run timing data
- [x] Extract per-job timing: queue time, build time, test time, first failure
- [x] Collect data across recent history (weeks/months) into CSV
- [x] Generate plots showing trends (time-to-signal, queue time patterns)
- [x] Bring data to team for dashboard productionization
