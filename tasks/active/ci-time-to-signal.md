---
repositories:
  - therock
---

# CI Time-to-Signal Analysis

- **Status:** In progress
- **Priority:** P1 (High)
- **Started:** 2026-03-19
- **Target:** 2026-03-28

## Overview

CI workflows in TheRock are very slow (multi-hour builds, long runner queue times).
This impacts developer productivity — PRs merged prematurely, forced reverts, slow
iteration. Goal: collect timing data, identify trends and bottlenecks, bring data
to the team so they can productionize dashboards.

## Goals

- [ ] Write a script that queries the GitHub API for workflow run timing data
- [ ] Extract per-job timing: queue time, build time, test time, first failure
- [ ] Collect data across recent history (weeks/months) into CSV
- [ ] Generate plots showing trends (time-to-signal, queue time patterns)
- [ ] Bring data to team for dashboard productionization

## Context

### Key Workflows

The main CI workflow is `CI` (id: 89445622, `ci.yml`). It orchestrates:
- `CI - Linux` (ci_linux.yml) and `CI - Windows` (ci_windows.yml)
- Build, test, python package, pytorch build/test jobs per variant
- `Multi-Arch CI` (multi_arch_ci.yml) — newer parallel workflow

### What We Know Already

From a quick sample of recent `CI` runs on `main`:
- Total wall time: ~7-8 hours per run
- Linux build jobs: 1-2.5 hours
- Windows build jobs: 2-4 hours (and ~18 min queue)
- Test runner queue times: up to 2.5-3 hours (gfx950-dcgpu)
- Many test jobs get skipped when builds fail

### API Access

`gh api` works with Scott's token (read access to repo). Plan to either:
1. Use a read-only token scoped to public repo data
2. Put query logic in a script that Scott grants permission to run

### Metrics to Extract Per Run

- **run_created_at**: When the workflow run was triggered
- **run_updated_at**: When the run fully completed
- **wall_time**: updated_at - created_at
- **first_failure_time**: earliest completed_at among failed jobs (minus created_at)
- **time_to_signal**: min(first_failure_time, wall_time)
- **Per-job**: queue_time (started_at - created_at), duration (completed_at - started_at)
- **Aggregates**: total build queue time, total test queue time, longest build, longest test
- **Skipped**: flag runs that exit early in setup

## Approach

### Phase 1: Data Collection Script
- Python script using `subprocess` to call `gh api`
- Query workflow runs, then jobs for each run
- Output CSV with one row per run, columns for all metrics
- Handle pagination (100 runs per page from the API)

### Phase 2: Postprocessing & Plots
- Matplotlib/pandas for analysis
- Time series: wall_time, time_to_signal over time
- Queue time patterns by day-of-week, time-of-day
- Breakdown by platform (Linux vs Windows) and GPU family

### Phase 3: Team Handoff
- Share CSV + plots with team
- Recommend which metrics to add to existing dashboards

## Scripts

- `prototypes/ci_time_to_signal.py` — main data collection script
- `prototypes/ci_time_to_signal_plots.py` — plotting (Phase 2)

## Next Steps

1. [x] Prototype API queries, understand data shape
2. [ ] Write `ci_time_to_signal.py` data collection script
3. [ ] Run against last 30 days of CI runs
4. [ ] Postprocess and generate plots
5. [ ] Share with team
