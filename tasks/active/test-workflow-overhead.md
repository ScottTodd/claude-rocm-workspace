---
repositories:
  - therock
---

# Test Workflow Overhead Optimization

- **Status:** Not started
- **Priority:** P2 (Medium)
- **Started:** 2026-02-25
- **Target:** TBD

## Overview

Self-hosted GPU test runners have long queue times. While runner capacity expansion
(on-prem + cloud), test filtering (smoketests vs full), and job filtering (change-based
test selection) are being addressed separately, we can also reduce pressure by optimizing
the test jobs themselves. Some jobs show 1-3 minutes of overhead from installing software,
downloading artifacts, and unpacking artifacts.

## Goals

- [ ] Quantitative analysis of current test job overhead (per-job breakdown)
- [ ] Identify caching opportunities for downloaded/unpacked artifacts
- [ ] Identify other overhead reduction opportunities
- [ ] Implement changes to reduce per-job overhead

## Context

### Background

GPU test runners are a scarce resource. Every minute of overhead in a test job is a minute
another job is waiting in the queue. With many jobs running across the matrix, small per-job
savings multiply quickly. For example, saving 2 minutes across 20 test jobs = 40 minutes of
freed runner capacity per CI run.

### Related Work

- Runner capacity expansion (on-prem and cloud hosted) — separate effort
- Test filtering: smoketests vs full test suites — separate effort
- Job filtering: change-based test selection (only run relevant tests) — separate effort
- `pytorch-ci` task — related but focused on PyTorch CI specifically

### Parallel Efforts (Out of Scope)

These reduce *what* runs on GPU runners. This task reduces *how long* each run takes:

| Effort | Approach | Status |
|--------|----------|--------|
| Runner capacity | More machines | In progress |
| Test filtering | Smoketests vs full | In progress |
| Job filtering | Skip unrelated subprojects | In progress |
| **This task** | **Reduce per-job overhead** | **Not started** |

### Directories/Files Involved

```
D:/projects/TheRock/.github/workflows/    # CI workflow definitions
D:/projects/TheRock/build_tools/ci/       # CI support scripts
```

## Investigation Notes

### Phase 1: Quantitative Analysis

Two parts: per-job overhead breakdown and volume/impact modeling.

#### 1a: Per-Job Overhead Breakdown

Analyze recent CI runs to measure per-job overhead breakdown:

- **Setup/checkout time** — How long does repo checkout + submodule init take?
- **Artifact download time** — How long to fetch build artifacts?
- **Artifact unpacking time** — How long to unpack/extract?
- **Software installation** — What gets installed at job start? How long?
- **Test environment setup** — Python env, dependencies, etc.
- **Teardown/upload** — Result upload, cleanup

#### 1b: Volume & Impact Model

Measure the aggregate picture to show concrete queue time impact:

- **Jobs per workflow run** — How many test jobs does a single CI run produce?
- **Workflow runs per day** — How many CI runs are triggered daily?
- **Runner pool size** — How many self-hosted GPU runners are available?
- **Actual test time vs overhead** — What fraction of each job is real work?

Use these to model queue time impact. Example calculation:

```
Given:
  10 runners, 50 workflow runs/day, 15 test jobs/workflow run
  4 min actual test + 1 min overhead = 5 min/job

Total job-minutes/day:  50 × 15 × 5 = 3,750 min
Runner capacity/day:    10 × 24 × 60 = 14,400 min
Queue pressure:         3,750 / 14,400 = 26% utilization (just test jobs)

If overhead drops from 1 min → 30 sec:
  Total job-minutes/day:  50 × 15 × 4.5 = 3,375 min  (saves 375 min/day)
  That's 6.25 runner-hours freed per day
```

The real numbers will be different (and utilization is likely much higher once
build jobs, other workloads, and bursty arrival patterns are factored in), but
this kind of model makes the case for optimization concrete and prioritizable.

### Phase 2: Identify Optimization Opportunities

Ideas to evaluate:

1. **Artifact caching on runners**
   - Self-hosted runners persist between jobs — can we cache unpacked artifacts?
   - Cache invalidation strategy: keyed on commit SHA, artifact hash, or build ID?
   - Disk space management on runners

2. **Pre-installed software on runner images**
   - What gets installed every job that could be baked into the runner image?

3. **Artifact format/compression optimization**
   - Are we using optimal compression for download speed vs size tradeoff?
   - Could we use different archive formats?

4. **Parallel downloads/unpacking**
   - Can artifact download and unpacking be parallelized?

5. **Incremental/delta artifacts**
   - For self-hosted runners, could we do delta updates instead of full downloads?

6. **Workflow structure**
   - Are there setup steps that could be shared across jobs via composite actions?
   - Could some setup be moved to a pre-job hook on self-hosted runners?

## Decisions & Trade-offs

*None yet — pending investigation.*

## Code Changes

### Files Modified

*None yet.*

### Testing Done

*None yet.*

## Blockers & Issues

### Active Blockers

*None.*

## Resources & References

- [GitHub Actions: self-hosted runner caching](https://docs.github.com/en/actions/hosting-your-own-runners)
- TheRock CI workflows in `.github/workflows/`

## Next Steps

1. [ ] Pull timing data from recent CI runs (GitHub Actions API or log analysis)
2. [ ] Create a breakdown table of overhead per job type
3. [ ] Measure volume: jobs per workflow, workflow runs per day, runner pool size
4. [ ] Build impact model showing queue time savings from overhead reduction
5. [ ] Prioritize optimization opportunities by impact vs effort
6. [ ] Prototype the highest-impact optimization (likely artifact caching)
