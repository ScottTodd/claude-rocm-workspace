# ROCm Build Infrastructure Project

## Overview

This workspace is for build infrastructure work on ROCm (Radeon Open Compute) via the TheRock repository and related projects.

Project repository: https://github.com/ROCm/TheRock

## Working Environment

**Important:** See `directory-map.md` for all directory locations.

This is a meta-workspace. Actual source and build directories are scattered
across the filesystem and referenced by absolute paths.

**Important:** Use relative paths when editing files.

For example:

- This meta-workspace directory: `D:/projects/claude-rocm-workspace`
- TheRock directory: `D:/projects/TheRock`
- Relative path to edit a file in TheRock: `../TheRock/docs/development/README.md`

## Project Context

### What is ROCm?

ROCm is AMD's open-source platform for GPU computing. It includes:

- HIP (Heterogeneous-Interface for Portability) - CUDA alternative
- ROCm runtime and drivers
- Math libraries (rocBLAS, rocFFT, etc.)
- Developer tools and compilers

### Build Infrastructure Focus

As a build infra team member, typical work involves:

- CMake build system configuration
- CI/CD pipeline maintenance
- Build dependency management
- Cross-platform build support
- Build performance optimization
- Package generation and distribution

## Common Tasks

### Building

- Builds typically happen in separate build trees (see directory-map.md)
- Out-of-tree builds are standard practice
- Multiple build configurations (Release, Debug, RelWithDebInfo) often maintained simultaneously

How we build depends on what kind of task we are doing:

#### Developing Build Infra

Good for making changes to the build infra when we aren't expecting to need to do C++ debugging.

1. CMake configure:

```
cmake -B /develop/therock-build -S /develop/therock -GNinja -DTHEROCK_AMDGPU_FAMILIES=gfx1201 \
  -DCMAKE_C_COMPILER_LAUNCHER=ccache \
  -DCMAKE_CXX_COMPILER_LAUNCHER=ccache
```

2. Build entire project (very time consuming)

```
cd /develop/therock-build && ninja
```

Configuring the project is often tricky. Rely on me to give you task specific instructions for configuration and incremental builds (or else you will initiate very long build time activities).

#### Working on specific components

Often we have to work on specific subsets of ROCm. We do this with -DTHEROCK_ENABLE_* flags as described in TheRock/README.md. Once the project is configured for the proper subset, it is typical to iterate by expunging and rebuilding a specific named project. Example:

```
cd /develop/therock-build
ninja clr+expunge && ninja clr+dist
```

### Source Navigation

- Source code is across multiple repositories and worktrees
- Git submodules are used extensively
- When editing build configs, check both source tree CMakeLists.txt and build tree caches

### Testing

- Unit tests, integration tests, and packaging tests
- Tests may run on different GPU architectures (gfx906, gfx908, gfx90a, etc.)

## Conventions & Gotchas

### Coding Standards

**Follow the style guides in [TheRock/docs/development/style_guides/](../TheRock/docs/development/style_guides/):**

| Guide | Use For |
|-------|---------|
| [Python Style Guide](../TheRock/docs/development/style_guides/python_style_guide.md) | All Python code |
| [CMake Style Guide](../TheRock/docs/development/style_guides/cmake_style_guide.md) | CMake build configuration |
| [Bash Style Guide](../TheRock/docs/development/style_guides/bash_style_guide.md) | Shell scripts |
| [GitHub Actions Style Guide](../TheRock/docs/development/style_guides/github_actions_style_guide.md) | CI/CD workflows |

Key principles across all languages:

- **Fail-fast**: Never silently continue on errors - raise exceptions immediately
- **Explicit over implicit**: Code should be self-documenting
- **Validate output**: Check that operations actually succeeded
- **DRY/YAGNI/KISS**: Don't repeat yourself, you aren't gonna need it, keep it simple

### Git Workflow

#### Branch Naming

Use the pattern: `users/<username>/<short-description>`

Examples:

- `users/scotttodd/add-simde-third-party`
- `users/scotttodd/fix-cmake-detection`

#### Creating a Branch and Committing

```bash
# Create and switch to a new branch
cd /develop/therock
git checkout -b users/scotttodd/<description>

# Stage changes
git add <files>

# Create commit with structured message and Claude Code footer
git commit -m "$(cat <<'EOF'
<Short summary line>

<Detailed description of what changed and why>

Changes:
- Bullet point list of key changes
- Another change

Additional context or testing notes.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

# Verify commit
git log -1 --stat
```

#### Commit Message Best Practices

- First line: Short summary (50-72 chars)
- Blank line after summary
- Detailed description explaining what and why
- Include "Changes:" section with bullet points for key modifications
- Add testing/verification notes
- Always include the Claude Code footer (emoji + link + Co-Authored-By)
- **DO NOT include issue references** (e.g., "Fixes #123", "Addresses issue #456")
  - Issue tagging happens in pull requests, not individual commits
  - Keeps commit messages focused on what changed, not tracking metadata

#### GPG Signing

- **NEVER retry failed commits with `--no-gpg-sign`**
  - The user uses a hardware device (YubiKey, etc.) to sign commits
  - If signing times out, wait for the user to retry manually
  - Do not attempt to bypass GPG signing under any circumstances

#### Submodules

- Git submodules are used extensively
- When editing build configs, check both source tree and build tree caches

### Review Workflow

Code reviews happen at two levels: **comprehensive reviews** (full PR/branch analysis) and **inline reviews** (quick feedback during iteration).

#### Comprehensive Code Reviews

When you say "review this PR" or "review my branch", Claude performs a comprehensive code review using the system in `reviews/`.

**Triggers** - any of these invoke the review system:

```
Review this PR: https://github.com/ROCm/TheRock/pull/2761
Review PR https://github.com/ROCm/TheRock/pull/2761
Can you review https://github.com/ROCm/TheRock/pull/2761
Review my current branch
Do a style review of my changes
```

**Skills:**

| Command | Description |
|---------|-------------|
| `/review-pr <URL> [types...]` | Review a GitHub PR |
| `/review-branch [types...]` | Review the current local branch |

**Review types** (optional - defaults to comprehensive):
- `style` - Code formatting, naming, conventions
- `tests` - Test coverage and quality
- `documentation` - Docs, comments, help text
- `architecture` - Design, patterns, structure
- `security` - Vulnerabilities, validation, secrets
- `performance` - Efficiency, scaling, resources

**Examples:**

```bash
# Comprehensive review (all aspects)
/review-pr https://github.com/ROCm/TheRock/pull/2761

# Focused reviews
/review-pr https://github.com/ROCm/TheRock/pull/2761 style
/review-branch tests security

# Natural language
Review this PR with focus on architecture: https://github.com/ROCm/TheRock/pull/2761
Do a security review of my branch
```

**Output files:**
- PR reviews: `reviews/pr_{NUMBER}.md` (or `_style.md`, `_tests.md`, etc.)
- Branch reviews: `reviews/local_{COUNTER}_{branch-name}.md`

**Severity levels:**
- `❌ BLOCKING` - Must fix before human review
- `⚠️ IMPORTANT` - Should fix before human review
- `💡 SUGGESTION` - Nice to have
- `📋 FUTURE WORK` - Out of scope for this PR

**Documentation:** See `reviews/README.md` for full details.

#### Inline Reviews (Quick Iteration)

For quick feedback during development, add inline comments with `RVW:` or `RVWY:` markers:

| Marker | Meaning |
|--------|---------|
| `RVW:` | Discuss - Claude proposes fix, waits for confirmation |
| `RVWY:` | YOLO - Claude makes the fix without asking |

```python
# RVW: This logic seems backwards - let's discuss
# RVWY: Add error handling here
```

Then ask Claude to "process review comments" or "fix the RVW comments".

### Task Tracking

Track work items in `tasks/active/`.

**Quick reference:**
- Start a task: `/task task-name` or "I'm working on task-name"
- Create new task: Copy `tasks/example-task.md` template
- Complete a task: Move to `tasks/completed/`

### Tools

- [List common tools: compilers, rocm-cmake, etc.]

## Reference

- [ROCm Documentation](https://rocm.docs.amd.com/)
- [TheRock repository](https://github.com/ROCm/TheRock)

## Notes

[Add your ongoing notes, discoveries, and context here as you work]
- Note that TheRock is a super-project. The builds under the submodules (like rocm-systems) are sub-projects. Since dependency management is handled by the super-project, you want to refer to those build rules. For example, in the case of ROCR-Runtime and clr, see the `core/CMakeLists.txt` file. This is documented in docs/development/build_system.md.
- Never do `git push` without explicit authorization.
- Do not amend commits without explicit authorization. Stage changes and ask for reviews before commiting.
- Don't be a sycophant and stroke my ego about how right I am when I make suggestions. Remember that I can be wrong too and feel free to engage in light debate if my reasoning seems unsound but accept when I make a decision.
- Don't claim that the result of work is "production" code or use shaky metrics to justify how things are progressing. Just say how things are without superlatives.
- Before committing to rocm-kpack, run pre-commit.
- When writing design docs, always include an "Alternatives Considered" section to list major, rejected options. Don't include nit-picky differences, just major architectural alternatives.
