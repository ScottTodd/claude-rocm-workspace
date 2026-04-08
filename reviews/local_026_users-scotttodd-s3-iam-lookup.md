# Branch Review: users/scotttodd/s3-iam-lookup

* **Branch:** `users/scotttodd/s3-iam-lookup`
* **Base:** `main`
* **Reviewed:** 2026-04-07
* **Commits:** 1 commit

---

## Summary

Centralizes S3 bucket selection and IAM role lookup into a new
`s3_buckets.py` module, exposes it via a `configure_aws_artifacts_credentials`
composite action, and migrates 8 workflows from inline
`aws-actions/configure-aws-credentials` blocks to the composite action.
Also updates `workflow_outputs.py` to delegate bucket selection to
`s3_buckets.py` and adds comprehensive tests.

**Net changes:** +525 lines, -327 lines across 15 files

---

## Overall Assessment

**:warning: CHANGES REQUESTED** - One bug that would break fork/external-repo CI runs.

**Strengths:**

- Clean separation: pure bucket inventory (`get_artifacts_bucket_config`),
  GHA-aware wrapper (`get_artifacts_bucket_config_for_workflow_run`), thin CLI
  script, composite action — each layer has a clear responsibility.
- Good test coverage of both public APIs including edge cases (env override,
  API lookup, event payload fork detection).
- Workflow migrations are mechanical and correct — `always()` preserved where
  needed, omitted where not.
- Doc update is well-structured — leads with the composite action, explains
  what it handles, links to source.

**Blocking Issues:**

1. `write_artifacts_bucket_info.py` passes `None` to `gha_set_output` for
   fork/external repos, which becomes the string `"None"` in GITHUB_OUTPUT.

---

## Detailed Review

### 1. `write_artifacts_bucket_info.py` — None becomes "None"

### :x: BLOCKING: `iam_role` output is `"None"` for fork/external repos

`config.write_access_iam_role` returns `None` when `iam_role` is not set
(e.g. `therock-ci-artifacts-external`). `gha_set_output` calls `str(v)` on
every value, producing `iam_role=None` in GITHUB_OUTPUT.

The composite action checks `steps.iam.outputs.iam_role != ''` — `"None"` is
non-empty, so it would attempt to assume IAM role `"None"`, which would fail.

This affects every fork PR and every external-repo CI run.

**Required action:** Coerce `None` to empty string before passing to
`gha_set_output`:

```python
gha_set_output(
    {
        "bucket": config.name,
        "iam_role": config.write_access_iam_role or "",
        "aws_region": config.region,
    }
)
```

### 2. `s3_buckets.py` — `_is_current_run_pr_from_fork` and `get_artifacts_bucket_config_for_workflow_run` fork detection inconsistency

### :bulb: SUGGESTION: Two fork detection strategies

`_is_current_run_pr_from_fork()` checks the `.fork` boolean on the head repo
(matches `github.event.pull_request.head.repo.fork`), while the
`workflow_run` path checks `head_repository.full_name != github_repository`
(name comparison). These are functionally equivalent for practical GitHub
workflows but use different semantics.

Not blocking — both work correctly in all real scenarios. Worth noting for
future readers.

### 3. `workflow_outputs.py` — `external_repo` heuristic change

### :bulb: SUGGESTION: `external_repo` derivation is now bucket-name-based

Old code: `external_repo` was non-empty when `owner != "ROCm" or repo_name != "TheRock" or is_pr_from_fork`.

New code: `external_repo` is non-empty when `bucket_name == "therock-ci-artifacts-external"`.

These are equivalent for all current bucket selection paths, but the new
approach couples `external_repo` to the bucket name rather than to the
repository identity. If a future release-type bucket is ever used with a fork,
`external_repo` would be empty (since the bucket name wouldn't be
`therock-ci-artifacts-external`). This is actually correct behavior — release
builds don't use `external_repo` prefixes — but worth being aware of.

### 4. Workflow migrations

All 4 non-multi-arch workflow migrations (build_portable_linux_artifacts,
build_windows_artifacts, build_portable_linux_python_packages,
build_windows_python_packages) are correct:

- `always()` preserved on build artifact workflows (upload logs on failure)
- `always()` correctly omitted on python package workflows
- `id-token: write` already present in all 4 workflows
- `special-characters-workaround` handled by composite action

### 5. Tests

### :bulb: SUGGESTION: `S3BucketConfig` not tested directly

The `S3BucketConfig` dataclass (frozen, `write_access_iam_role` property) has
no dedicated tests. The `write_access_iam_role` property has three code paths
(no role, role with namespace, role without namespace) that are only exercised
indirectly. Low risk since the dataclass is simple, but the property's error
path (missing namespace) is never tested.

---

## Recommendations

### :x: REQUIRED (Blocking):

1. Fix `write_artifacts_bucket_info.py` to coerce `None` to `""` for `iam_role` output.

### :bulb: Consider:

1. Add a few `S3BucketConfig` tests (frozen, `write_access_iam_role` paths) if scope permits.
2. Document the fork detection inconsistency with a brief inline comment.

### :clipboard: Future Follow-up:

1. Migrate `manifest-diff.yml` and pytorch sccache workflows (out of scope, per discussion).
2. Switch `_log` to `logging.getLogger(__name__)` with info/debug levels (noted in task doc as future work — noisy for scripts like `find_latest_artifacts.py`).

---

## Testing Recommendations

- Run existing tests: `python -m pytest build_tools/tests/s3_buckets_test.py build_tools/tests/workflow_outputs_test.py`
- CI validation: run a fork PR to confirm the composite action correctly skips OIDC (this is the path affected by the blocking bug).
- CI validation: run on `ROCm/TheRock` to confirm OIDC assumption works end-to-end.

---

## Conclusion

**Approval Status: :warning: CHANGES REQUESTED**

Fix the `None`→`"None"` bug in `write_artifacts_bucket_info.py` before merging.
The rest of the PR is clean and well-structured.
