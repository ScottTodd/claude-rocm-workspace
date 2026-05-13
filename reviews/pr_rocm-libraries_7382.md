# PR Review: [ci] `therock-ci-*` workflows pull hash from develop

* **PR:** [ROCm/rocm-libraries#7382](https://github.com/ROCm/rocm-libraries/pull/7382)
* **Author:** geomin12
* **Base:** `develop` <- `users/geomin12/at-head`
* **Reviewed:** 2026-05-13
* **Existing approval:** tony-davis (APPROVED)

---

## Summary

Replaces hardcoded TheRock commit hashes in 6 workflow files with a runtime
lookup: each workflow sparse-checkouts `.github/therock-hash-version` from
the `develop` branch, reads the hash, and uses it for the TheRock checkout.
Also adds that file path to `is_path_workflow_file_related_to_ci()` so
version bumps trigger full CI.

**Net changes:** +116 lines, -6 lines across 7 files

---

## Overall Assessment

**CHANGES REQUESTED** - The mechanism fights against a well-understood GitHub
Actions feature (merge base) that already solves this problem, while
introducing real downsides (non-reproducibility, race conditions, code
duplication).

**Issues:**

- The stated problem is already solved by GitHub's pull_request merge mechanism
- CI behavior becomes non-reproducible (depends on when it runs, not what's committed)
- Same 15-line block copy-pasted into 6 workflow files
- `workflow_dispatch` / `push` event semantics change in surprising ways

---

## Detailed Review

### 1. The Problem Statement Doesn't Hold for PR CI

The PR description states:

> Often, developers have complained about having to rebase in order to get
> workflow changes and new runner updates.

For `pull_request` events, GitHub Actions creates a **merge commit** of the
PR head and the base branch. This means:

- If `develop` updates the TheRock hash in the workflow YAML, and the PR
  branch doesn't modify that same file, the merge commit naturally includes
  the new hash. **No rebase needed.**
- If the PR branch also modifies the same workflow file and there's a real
  merge conflict, a rebase is *correctly* required — the developer is making
  workflow changes and should test against the latest base.
- If both branches modify the file but in different regions, git merges
  cleanly and the PR picks up the new hash automatically.

The scenario where a developer needs to rebase *solely to pick up a new
TheRock hash* already works through the merge base mechanism, which is exactly
how GitHub Actions is designed. The version file approach is circumventing
this.

**Why this matters:** If the actual pain point is something different (e.g.,
forked repos, specific triggers, or merge queue behavior), the PR description
should articulate that specific scenario rather than the general claim. The
linked CI run shows a `pull_request` trigger, which is the case that already
works.

### 2. Non-Reproducibility

With this change, CI results depend on the state of `develop` at the time the
workflow runs, not on the committed code. Two runs of the same commit can
produce different results:

- Push a commit at 10:00 → CI uses TheRock hash A (current develop)
- Someone bumps `therock-hash-version` on develop at 10:30
- Re-run CI at 11:00 → CI uses TheRock hash B

This breaks a fundamental CI property: for a given commit, CI should be
deterministic. The hardcoded hash approach provides this — you can always look
at the git history and know exactly what TheRock version was used.

### 3. Surprising Behavior for Non-PR Triggers

The workflows support multiple triggers. The runtime lookup changes semantics
for each:

| Trigger | Before (hardcoded) | After (runtime lookup) |
|---------|--------------------|-----------------------|
| `pull_request` | Uses merge-base hash (already up-to-date) | Uses develop's hash (same result, extra steps) |
| `push` | Uses committed hash | Uses develop's latest hash (may differ from committed) |
| `workflow_dispatch` | Uses hash from selected ref | Uses develop's latest hash (ignores selected ref) |
| `schedule` | Uses hash from default branch | Uses develop's hash (same, but non-deterministic across days) |

For `workflow_dispatch` in particular, this is a regression: you can no longer
dispatch against an older ref and get the TheRock version that was current at
that point in time. The version is always pulled from develop HEAD.

### 4. Code Duplication (6x)

The same ~15-line block is copy-pasted into all 6 workflow files:

```yaml
- name: Fetch TheRock version file from develop
  uses: actions/checkout@...
  with:
    repository: ROCm/rocm-libraries
    ref: develop
    sparse-checkout: .github/therock-hash-version
    path: _therock_version

- name: Set TheRock version
  shell: bash
  run: |
    THEROCK_REF=$(cat _therock_version/.github/therock-hash-version | tr -d '[:space:]')
    echo "THEROCK_REF=$THEROCK_REF" >> $GITHUB_ENV
```

If this approach were to move forward, this should be a [composite action](https://docs.github.com/en/actions/sharing-automations/creating-actions/creating-a-composite-action)
to avoid maintaining 6 identical copies.

### 5. `therock_configure_ci.py` Change

```python
if path == ".github/therock-hash-version":
    return True
```

This is reasonable *if* the version file mechanism is adopted — changes to the
hash file should trigger full CI. But it's a new coupling point that wouldn't
be needed if the hash stayed in the workflow YAML.

### 6. Testing Instructions Are Self-Defeating

The testing comment at the top of `therock-ci.yml`:

> To test a new TheRock commit on a PR branch, temporarily hardcode the ref
> in the "Checkout TheRock repository" step (remember to revert before merging).

This is literally the workflow the PR claims to eliminate. Developers who need
to test a specific TheRock hash on their PR branch still have to hardcode a
ref and remember to revert — the same experience as before, but now with an
extra mechanism to understand.

---

## Recommendations

### REQUIRED (Blocking):

1. **Reconsider the approach.** The merge-base mechanism already solves the
   stated problem for `pull_request` events. If there's a different, specific
   scenario driving this (forks? merge queues? a particular trigger type?),
   the PR should clearly articulate it, and the solution should be scoped to
   that scenario rather than changing all trigger types.

### Consider:

1. **If the approach proceeds despite the above:** Extract the version-file
   lookup into a composite action to eliminate the 6x duplication.
2. **If the approach proceeds:** Add a fallback so that `workflow_dispatch`
   on an older ref still uses the hash from that ref, not from develop HEAD.

### Future Follow-up:

1. If the real pain point is about *workflow file changes* (not the TheRock
   hash), consider GitHub's merge queue feature or branch protection rules
   that require branches to be up-to-date before merging.

---

## Conclusion

**Approval Status: CHANGES REQUESTED**

The PR introduces runtime complexity (non-reproducibility, race conditions,
code duplication) to solve a problem that GitHub's merge-base mechanism
already handles for the primary use case (PR CI). The approach should be
reconsidered, or the PR description should clearly articulate the specific
scenario that the merge base does *not* handle.
