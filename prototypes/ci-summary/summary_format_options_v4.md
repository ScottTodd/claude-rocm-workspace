# format_summary v4: DAG structure + BuildConfig details

---

## Scenario 1: Normal push, submodule changed

## Multi-Arch CI Configuration

Push to `main`, `release` variant. Submodule `rocm-libraries` changed.

```
build-rocm ──┬── test-rocm
             └── build-rocm-python ──┬── build-pytorch ── test-pytorch
                                     └── build-jax (future)
```

### build-rocm

Building all stages from source.

| Platform | Families | Artifact Group |
|----------|----------|----------------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151`, `gfx120X-all`, `gfx950-dcgpu` | `multi-arch-release` |
| Windows | `gfx110X-all`, `gfx1151`, `gfx120X-all` | `multi-arch-release` |

### test-rocm

Test level: **full** (submodule `rocm-libraries` changed).

| Family | Platform | Runner | Scope |
|--------|----------|--------|-------|
| `gfx94X-dcgpu` | Linux | `linux-mi325-1gpu-ossci-rocm` | full |
| `gfx110X-all` | Linux | — (disabled) | sanity check only |
| `gfx1151` | Linux | `linux-gfx1151-gpu-rocm` | sanity check only |
| `gfx120X-all` | Linux | `linux-gfx120X-gpu-rocm` | sanity check only |
| `gfx950-dcgpu` | Linux | `linux-mi355-1gpu-ossci-rocm` | full |
| `gfx110X-all` | Windows | `windows-gfx110X-gpu-rocm` | full |
| `gfx1151` | Windows | `windows-gfx1151-gpu-rocm` | full |
| `gfx120X-all` | Windows | — (disabled) | full |

### build-pytorch

Building pytorch for families where `build_pytorch` is true.

| Platform | Families |
|----------|----------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151`, `gfx120X-all`, `gfx950-dcgpu` |
| Windows | `gfx110X-all`, `gfx1151`, `gfx120X-all` |

### test-pytorch

Testing pytorch on runners with test capability (non-empty `test-runs-on`).

---

## Scenario 2: workflow_dispatch with prebuilt stages and test labels

## Multi-Arch CI Configuration

Workflow dispatch on `multi-arch-configure`, `release` variant.

```
build-rocm ──┬── test-rocm
             └── build-rocm-python ──┬── build-pytorch ── test-pytorch
                                     └── build-jax (future)
```

| Decision | Value | Reason |
|----------|-------|--------|
| Families | explicit selection | Workflow dispatch input |
| Test level | `full` | Test label `test:hipcub` |
| Prebuilt | `foundation`, `compiler-runtime` | Use prebuilt artifacts from run [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293) |

### build-rocm

| Platform | Families | Artifact Group |
|----------|----------|----------------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all` | `multi-arch-release` |
| Windows | `gfx1151` | `multi-arch-release` |

Stages `foundation` and `compiler-runtime` use prebuilt artifacts from run [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293). Remaining stages build from source.

### test-rocm

Test level: **full** (test label `test:hipcub` specified).

| Family | Platform | Runner | Scope |
|--------|----------|--------|-------|
| `gfx94X-dcgpu` | Linux | `linux-mi325-1gpu-ossci-rocm` | full |
| `gfx110X-all` | Linux | — (disabled) | sanity check only |
| `gfx1151` | Windows | `windows-gfx1151-gpu-rocm` | full |

### build-pytorch

| Platform | Families |
|----------|----------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all` |
| Windows | `gfx1151` |

### test-pytorch

Testing pytorch on available runners.

---

## Scenario 3: PR with label overrides

## Multi-Arch CI Configuration

Pull request on `feature-branch`, `release` variant.

```
build-rocm ──┬── test-rocm
             └── build-rocm-python ──┬── build-pytorch ── test-pytorch
                                     └── build-jax (future)
```

| Decision | Value | Reason |
|----------|-------|--------|
| Families | presubmit + `gfx950` | `gfx950` PR label added a postsubmit-only family |
| Test level | `comprehensive` | `test_filter:comprehensive` label (default: `quick`) |
| Test labels | `test:rocprim` | PR label |

### build-rocm

| Platform | Families | Artifact Group |
|----------|----------|----------------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151`, `gfx120X-all`, `gfx950-dcgpu` | `multi-arch-release` |
| Windows | `gfx110X-all`, `gfx1151`, `gfx120X-all` | `multi-arch-release` |

### test-rocm

Test level: **comprehensive** (`test_filter:comprehensive` label overrode default `quick`).

| Family | Platform | Runner | Scope |
|--------|----------|--------|-------|
| `gfx94X-dcgpu` | Linux | `linux-mi325-1gpu-ossci-rocm` | comprehensive |
| `gfx110X-all` | Linux | — (disabled) | sanity check only |
| `gfx1151` | Linux | `linux-gfx1151-gpu-rocm` | sanity check only |
| `gfx120X-all` | Linux | `linux-gfx120X-gpu-rocm` | sanity check only |
| `gfx950-dcgpu` | Linux | `linux-mi355-1gpu-ossci-rocm` | comprehensive |
| `gfx110X-all` | Windows | `windows-gfx110X-gpu-rocm` | comprehensive |
| `gfx1151` | Windows | `windows-gfx1151-gpu-rocm` | comprehensive |
| `gfx120X-all` | Windows | — (disabled) | comprehensive |

Component tests: `test:rocprim`

### build-pytorch / test-pytorch

Building and testing pytorch for all families (no expect_failure).

---

## Scenario 4: Future PR that only affects pytorch packaging (DAG skip)

## Multi-Arch CI Configuration

Pull request on `fix-pytorch-wheel`, `release` variant.

```
build-rocm (prebuilt) ── build-rocm-python (prebuilt) ── build-pytorch ── test-pytorch
                      ╳  test-rocm (skipped — ROCm unchanged)
```

| Decision | Value | Reason |
|----------|-------|--------|
| build-rocm | prebuilt | No ROCm source changes, use prebuilt artifacts from run [23100000000](https://github.com/ROCm/TheRock/actions/runs/23100000000) |
| test-rocm | **skipped** | ROCm libraries unchanged — no need to re-test |
| build-rocm-python | prebuilt | Python packaging unchanged |
| build-pytorch | **rebuild** | Files changed in pytorch packaging |
| test-pytorch | **run** | Verify pytorch wheel works |

### build-pytorch

| Platform | Families |
|----------|----------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151`, `gfx120X-all` |

### test-pytorch

Testing rebuilt pytorch wheels against prebuilt ROCm.

| Family | Platform | Runner |
|--------|----------|--------|
| `gfx94X-dcgpu` | Linux | `linux-mi325-1gpu-ossci-rocm` |

---

## Scenario 5: Skip CI

## Multi-Arch CI Configuration

CI was **skipped**: only documentation files changed.

---

## Notes

- The ASCII DAG at the top orients the reader. For skip scenarios (scenario 4)
  it shows which parts are crossed out — the visual makes it immediately
  clear what's running vs skipped.
- The decision table only appears when there's something non-default to explain.
  A normal schedule run with all defaults could skip it entirely.
- The test-rocm section exposes per-family runner labels and scope from the
  BuildConfig's `matrix_per_family_json`. This is what a contributor needs to
  know: "will my family get tested, and where?"
- The build-pytorch section shows which families actually get pytorch builds
  (derived from `build_pytorch` on BuildConfig + per-family expect_failure).
- Scenario 4 is aspirational (Phase 4 decide_jobs with DAG selection) but
  shows how the format scales — skipped/prebuilt nodes are explained with
  reasons, and only the nodes that actually run get detail sections.
