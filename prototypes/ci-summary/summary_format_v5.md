# format_summary v5: final direction

Structure:
1. One-line intro (trigger, branch, variant)
2. Non-default decisions block (only if something is unusual)
3. Fixed DAG (always the same, orients the reader)
4. ### sections per DAG node with real data from BuildConfig

---

## Scenario 1: Normal push, submodule changed

## Multi-Arch CI Configuration

Push to `main`, `release` variant.

```
build-rocm ──┬── test-rocm
             └── build-rocm-python ── build-pytorch
```

### build-rocm

Building all stages from source.

| Platform | Families | Artifact Group |
|----------|----------|----------------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151`, `gfx120X-all`, `gfx950-dcgpu` | `multi-arch-release` |
| Windows | `gfx110X-all`, `gfx1151`, `gfx120X-all` | `multi-arch-release` |

### test-rocm

Test level: **full** (submodule `rocm-libraries` changed).

| Platform | Family | Runner | Scope |
|----------|--------|--------|-------|
| Linux | `gfx94X-dcgpu` | `linux-mi325-1gpu-ossci-rocm` | full |
| Linux | `gfx110X-all` | — | sanity check only |
| Linux | `gfx1151` | `linux-gfx1151-gpu-rocm` | sanity check only |
| Linux | `gfx120X-all` | `linux-gfx120X-gpu-rocm` | sanity check only |
| Linux | `gfx950-dcgpu` | `linux-mi355-1gpu-ossci-rocm` | full |
| Windows | `gfx110X-all` | `windows-gfx110X-gpu-rocm` | full |
| Windows | `gfx1151` | `windows-gfx1151-gpu-rocm` | full |
| Windows | `gfx120X-all` | — | full |

### build-pytorch

| Platform | Families |
|----------|----------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151`, `gfx120X-all`, `gfx950-dcgpu` |
| Windows | `gfx110X-all`, `gfx1151`, `gfx120X-all` |

---

## Scenario 2: PR with label overrides

## Multi-Arch CI Configuration

Pull request on `feature-branch`, `release` variant.

> **Non-default configuration:**
> - Label `gfx950`: added family `gfx950` (not in default presubmit set)
> - Label `test_filter:comprehensive`: overrode test level (default would be `quick`)
> - Label `test:rocprim`: requested component tests

```
build-rocm ──┬── test-rocm
             └── build-rocm-python ── build-pytorch
```

### build-rocm

Building all stages from source.

| Platform | Families | Artifact Group |
|----------|----------|----------------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151`, `gfx120X-all`, `gfx950-dcgpu` | `multi-arch-release` |
| Windows | `gfx110X-all`, `gfx1151`, `gfx120X-all` | `multi-arch-release` |

### test-rocm

Test level: **comprehensive** (`test_filter:comprehensive` label).
Component tests: `test:rocprim`.

| Platform | Family | Runner | Scope |
|----------|--------|--------|-------|
| Linux | `gfx94X-dcgpu` | `linux-mi325-1gpu-ossci-rocm` | comprehensive |
| Linux | `gfx110X-all` | — | sanity check only |
| Linux | `gfx1151` | `linux-gfx1151-gpu-rocm` | sanity check only |
| Linux | `gfx120X-all` | `linux-gfx120X-gpu-rocm` | sanity check only |
| Linux | `gfx950-dcgpu` | `linux-mi355-1gpu-ossci-rocm` | comprehensive |
| Windows | `gfx110X-all` | `windows-gfx110X-gpu-rocm` | comprehensive |
| Windows | `gfx1151` | `windows-gfx1151-gpu-rocm` | comprehensive |
| Windows | `gfx120X-all` | — | comprehensive |

### build-pytorch

| Platform | Families |
|----------|----------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151`, `gfx120X-all`, `gfx950-dcgpu` |
| Windows | `gfx110X-all`, `gfx1151`, `gfx120X-all` |

---

## Scenario 3: workflow_dispatch with prebuilt stages

## Multi-Arch CI Configuration

Workflow dispatch on `multi-arch-configure`, `release` variant.

> **Non-default configuration:**
> - Explicit family selection: Linux (`gfx94X-dcgpu`, `gfx110X-all`), Windows (`gfx1151`)
> - Test label `test:hipcub`
> - Prebuilt stages: `foundation`, `compiler-runtime` from run [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293)

```
build-rocm ──┬── test-rocm
             └── build-rocm-python ── build-pytorch
```

### build-rocm

Using prebuilt artifacts for stages: `[foundation, compiler-runtime]` from run [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293). Remaining stages build from source.

| Platform | Families | Artifact Group |
|----------|----------|----------------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all` | `multi-arch-release` |
| Windows | `gfx1151` | `multi-arch-release` |

### test-rocm

Test level: **full** (test label `test:hipcub`).

| Platform | Family | Runner | Scope |
|----------|--------|--------|-------|
| Linux | `gfx94X-dcgpu` | `linux-mi325-1gpu-ossci-rocm` | full |
| Linux | `gfx110X-all` | — | sanity check only |
| Windows | `gfx1151` | `windows-gfx1151-gpu-rocm` | full |

### build-pytorch

| Platform | Families |
|----------|----------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all` |
| Windows | `gfx1151` |

---

## Scenario 4: Normal PR, no labels (minimal output)

## Multi-Arch CI Configuration

Pull request on `fix-typo`, `release` variant.

```
build-rocm ──┬── test-rocm
             └── build-rocm-python ── build-pytorch
```

### build-rocm

Building all stages from source.

| Platform | Families | Artifact Group |
|----------|----------|----------------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151`, `gfx120X-all` | `multi-arch-release` |
| Windows | `gfx110X-all`, `gfx1151`, `gfx120X-all` | `multi-arch-release` |

### test-rocm

Test level: **quick** (default).

| Platform | Family | Runner | Scope |
|----------|--------|--------|-------|
| Linux | `gfx94X-dcgpu` | `linux-mi325-1gpu-ossci-rocm` | quick |
| Linux | `gfx110X-all` | — | sanity check only |
| Linux | `gfx1151` | `linux-gfx1151-gpu-rocm` | sanity check only |
| Linux | `gfx120X-all` | `linux-gfx120X-gpu-rocm` | sanity check only |
| Windows | `gfx110X-all` | `windows-gfx110X-gpu-rocm` | quick |
| Windows | `gfx1151` | `windows-gfx1151-gpu-rocm` | quick |
| Windows | `gfx120X-all` | — | quick |

### build-pytorch

| Platform | Families |
|----------|----------|
| Linux | `gfx94X-dcgpu`, `gfx110X-all`, `gfx1151`, `gfx120X-all` |
| Windows | `gfx110X-all`, `gfx1151`, `gfx120X-all` |

---

## Scenario 5: Skip CI

## Multi-Arch CI Configuration

CI was **skipped**: no CI-relevant files changed (see [configure_ci_path_filters.py](https://github.com/ROCm/TheRock/blob/main/build_tools/github_actions/configure_ci_path_filters.py) for skip patterns).

Changed files:
```
docs/development/README.md
README.md
```

---

## Scenario 6: ASAN (linux-only)

## Multi-Arch CI Configuration

Workflow dispatch on `main`, `asan` variant.

> **Non-default configuration:**
> - ASAN variant (linux only, no Windows ASAN config)
> - Explicit family selection: `gfx94X-dcgpu`

```
build-rocm ──┬── test-rocm
             └── build-rocm-python ── build-pytorch
```

### build-rocm

Building all stages from source.

| Platform | Families | Artifact Group |
|----------|----------|----------------|
| Linux | `gfx94X-dcgpu` | `multi-arch-asan` |
| Windows | — (no ASAN config) | — |

### test-rocm

Test level: **quick** (default).

| Platform | Family | Runner | Scope |
|----------|--------|--------|-------|
| Linux | `gfx94X-dcgpu` | `linux-mi325-1gpu-ossci-rocm` | quick |

### build-pytorch

Not building pytorch (ASAN variant).
