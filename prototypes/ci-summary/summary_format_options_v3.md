# format_summary v3: incorporating feedback

Combines: K's decision-reason table, D's job-oriented structure as a
per-platform table, prose where it helps, backtick-wrapped family names.

---

## Scenario 1: Normal push to main, submodule changed

## Multi-Arch CI Configuration

Push to `main`, building `release` variant.

| Decision | Value | Reason |
|----------|-------|--------|
| Families | presubmit + postsubmit | Default for push |
| Test level | `full` | Submodule `rocm-libraries` changed |

| Job | Linux `release` | Windows `release` |
|-----|-----------------|-------------------|
| build-rocm | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151`, `gfx120X-all`, `gfx950-dcgpu` | `gfx110X-all`, `gfx1151`, `gfx120X-all` |
| test-rocm | `full` tests | `full` tests |
| build-rocm-python | yes | yes |
| build-pytorch | yes | yes |
| test-pytorch | yes | yes |

---

## Scenario 2: workflow_dispatch with explicit families, test labels, prebuilt

## Multi-Arch CI Configuration

Workflow dispatch on `multi-arch-configure`, building `release` variant.

| Decision | Value | Reason |
|----------|-------|--------|
| Families | explicit selection | Workflow dispatch input |
| Test level | `full` | Test label `test:hipcub` specified |
| Prebuilt stages | `foundation`, `compiler-runtime` | Use prebuilt artifacts from run [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293) |

| Job | Linux `release` | Windows `release` |
|-----|-----------------|-------------------|
| build-rocm | `gfx94X-dcgpu`, `gfx110X-all` | `gfx1151` |
| test-rocm | `full` tests, labels: `test:hipcub` | `full` tests |
| build-rocm-python | yes | yes |
| build-pytorch | yes | yes |
| test-pytorch | yes | yes |

---

## Scenario 3: PR with labels opting into extra targets

## Multi-Arch CI Configuration

Pull request on `feature-branch`, building `release` variant.

| Decision | Value | Reason |
|----------|-------|--------|
| Families | presubmit + `gfx950` | Default presubmit, plus `gfx950` label |
| Test level | `comprehensive` | `test_filter:comprehensive` label (default would be `quick`) |
| Test labels | `test:rocprim` | `test:rocprim` PR label |

| Job | Linux `release` | Windows `release` |
|-----|-----------------|-------------------|
| build-rocm | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151`, `gfx120X-all`, `gfx950-dcgpu` | `gfx110X-all`, `gfx1151`, `gfx120X-all` |
| test-rocm | `comprehensive` tests, labels: `test:rocprim` | `comprehensive` tests |
| build-rocm-python | yes | yes |
| build-pytorch | yes | yes |
| test-pytorch | yes | yes |

---

## Scenario 4: ASAN build (linux-only, single platform column)

## Multi-Arch CI Configuration

Workflow dispatch on `main`, building `asan` variant.

| Decision | Value | Reason |
|----------|-------|--------|
| Families | explicit selection | Workflow dispatch input |
| Test level | `quick` | Default |
| Windows | skipped | No ASAN variant config for Windows |

| Job | Linux `asan` |
|-----|--------------|
| build-rocm | `gfx94X-dcgpu` |
| test-rocm | `quick` tests |
| build-rocm-python | yes |
| build-pytorch | no (expect failure) |
| test-pytorch | no |

---

## Scenario 5: Schedule (nightly)

## Multi-Arch CI Configuration

Scheduled run on `main`, building `release` variant.

| Decision | Value | Reason |
|----------|-------|--------|
| Families | all (presubmit + postsubmit + nightly) | Default for schedule |
| Test level | `comprehensive` | Scheduled run |

| Job | Linux `release` | Windows `release` |
|-----|-----------------|-------------------|
| build-rocm | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151`, `gfx120X-all`, `gfx950-dcgpu`, `gfx906`, `gfx908`, `gfx90a`, `gfx101X-dgpu`, `gfx103X-dgpu`, `gfx1150`, `gfx1152`, `gfx1153` | `gfx110X-all`, `gfx1151`, `gfx120X-all`, `gfx906`, `gfx908`, `gfx90a`, `gfx101X-dgpu`, `gfx103X-dgpu`, `gfx1150`, `gfx1152`, `gfx1153` |
| test-rocm | `comprehensive` tests | `comprehensive` tests |
| build-rocm-python | yes | yes |
| build-pytorch | yes | yes |
| test-pytorch | yes | yes |

---

## Scenario 6: Skip CI

## Multi-Arch CI Configuration

CI was **skipped**: only documentation files changed.

---

## Notes

- The decision table at the top is the "why" — scan it to understand what's
  unusual about this run. Normal defaults don't need explanation so the table
  is short for standard runs.
- The job table is the "what" — shows exactly what each job group does on
  each platform. Column headers include the variant name.
- When a platform is skipped entirely (like Windows for ASAN), it's called
  out in the decision table and the job table drops that column.
- The nightly schedule scenario shows the problem with long family lists in
  table cells. Could truncate with "13 families" and show the full list in
  the log output instead.
