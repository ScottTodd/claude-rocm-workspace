# format_summary options

Example data for all options:
- Trigger: workflow_dispatch
- Linux families: gfx94X-dcgpu, gfx110X-all
- Windows families: gfx1151
- Variant: release
- Test type: full (test labels specified)
- Prebuilt stages: foundation, compiler-runtime (baseline run 22909539293)
- Test labels: test:hipcub

---

## Option A: Compact table

## Multi-Arch CI Configuration

| | Linux | Windows |
|---|---|---|
| **Families** | gfx94X-dcgpu, gfx110X-all | gfx1151 |
| **Variant** | release | release |
| **Test level** | full (test labels specified) | full (test labels specified) |
| **Prebuilt stages** | foundation, compiler-runtime | foundation, compiler-runtime |

---

## Option B: Sectioned prose

## Multi-Arch CI Configuration

Building **release** for **Linux** (gfx94X-dcgpu, gfx110X-all) and **Windows** (gfx1151).

Stages **foundation** and **compiler-runtime** will use prebuilt artifacts from run [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293). All other stages build from source.

Running **full** tests because test labels were specified.

---

## Option C: Grouped bullet lists

## Multi-Arch CI Configuration

**Build:**
- Linux: gfx94X-dcgpu, gfx110X-all (release)
- Windows: gfx1151 (release)
- Prebuilt stages: foundation, compiler-runtime (from run [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293))

**Test:**
- Level: full (test labels specified)
- Labels: test:hipcub

---

## Option D: Job-oriented with details

## Multi-Arch CI Configuration

**build-rocm:** Building release for 3 GPU families across 2 platforms.
- Linux: gfx94X-dcgpu, gfx110X-all
- Windows: gfx1151
- Prebuilt: foundation, compiler-runtime (from run [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293))

**test-rocm:** Running full tests (test labels specified).
- Labels: test:hipcub

**build-rocm-python:** Building Python packages.

**build-pytorch:** Building PyTorch.

**test-pytorch:** Testing PyTorch.

---

## Option E: Prose + details blocks

## Multi-Arch CI Configuration

Building **release** variant for Linux (gfx94X-dcgpu, gfx110X-all) and Windows (gfx1151). Running **full** tests because test labels were specified.

<details>
<summary>Build details</summary>

- Prebuilt stages: foundation, compiler-runtime
- Baseline run: [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293)
- Test labels: test:hipcub
- Artifact group: multi-arch-release

</details>

---

## Option F: Minimal — skip-CI variant

## Multi-Arch CI Configuration

CI was **skipped**: only documentation files changed.

---

## Option G: Minimal — no prebuilt, default test type

## Multi-Arch CI Configuration

Building **release** for Linux (gfx94X-dcgpu, gfx110X-all, gfx1151, gfx120X-all) and Windows (gfx110X-all, gfx1151, gfx120X-all). Running **quick** tests.

---

## Option H: Grouped bullets with conditional sections

## Multi-Arch CI Configuration

**Build:**
- Linux: gfx94X-dcgpu, gfx110X-all (release)
- Windows: gfx1151 (release)

**Prebuilt stages:** foundation, compiler-runtime
- Baseline run: [22909539293](https://github.com/ROCm/TheRock/actions/runs/22909539293)
- All other stages build from source.

**Test:** full (test labels specified)
- Labels: test:hipcub
