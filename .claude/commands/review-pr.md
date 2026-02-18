---
description: Review a GitHub pull request
allowed-tools: Bash(gh:*), Read, Write, Glob, Grep, WebFetch, Task
argument-hint: <PR_URL> [review-type ...]
---

Review a GitHub pull request comprehensively or with specific focus areas.

## Arguments

- `$ARGUMENTS` contains: `<PR_URL> [review-type ...]`
- First argument is the GitHub PR URL (required)
- Additional arguments are optional review types: `style`, `tests`, `documentation`, `architecture`, `security`, `performance`
- If no review types specified, perform a comprehensive review (all aspects)

## Process

### 1. Parse Arguments

Extract PR URL and optional review types from `$ARGUMENTS`.

### 2. Fetch PR Information

Use `gh` CLI to get PR details:
```bash
gh pr view <URL> --json number,title,author,body,files,additions,deletions,state,baseRefName,headRefName
```

Also fetch the diff:
```bash
gh pr diff <URL>
```

### 3. Review Setup

- Read `reviews/REVIEW_GUIDELINES.md` for severity levels, format, and the
  evidence-based review methodology
- Read `reviews/REVIEW_TYPES.md` if doing focused reviews
- Determine output filename: `reviews/pr_{NUMBER}.md` or `reviews/pr_{NUMBER}_{TYPE}.md`

### 3a. Gather CI Evidence (if available)

Check the PR body for linked CI/test runs. If found:

1. Fetch step-level data for the PR run:
   ```bash
   gh api repos/OWNER/REPO/actions/jobs/JOB_ID \
     --jq '{name, steps: [.steps[] | {name, conclusion, started_at, completed_at}]}'
   ```

2. Find a recent baseline run on `main` for the same workflow to compare
   against (look at the workflow's recent runs via `gh run list`).

3. Note any step timing anomalies, cache behavior differences, or status
   changes between the PR run and the baseline.

This evidence will be used during the review to validate or disprove
hypotheses formed from the diff. See the "Evidence-Based Review" section
in `REVIEW_GUIDELINES.md` for the full methodology.

If no CI runs are linked or discoverable, proceed with code-only review
and note hypotheses as conditional (with suggested verification steps).

### 4. Perform Review

Follow the review guidelines:

**Comprehensive review (default):** Analyze all aspects:
- Correctness and logic
- Code style and conventions
- Test coverage
- Documentation
- Architecture and design
- Security concerns
- Performance implications

**Focused review(s):** If specific types requested, focus only on those areas.

**Multiple types:** If multiple types given (e.g., `style tests`), either:
- Combine findings into sections in one review file, OR
- Use Task tool to run reviews in parallel if appropriate

### 5. Write Review File

Create the review file following the template in `REVIEW_GUIDELINES.md`:
- Header with PR link, author, date, status
- Summary of changes
- Overall assessment (APPROVED / CHANGES REQUESTED / REJECTED)
- Detailed findings with severity markers (BLOCKING, IMPORTANT, SUGGESTION, FUTURE WORK)
- Recommendations organized by severity
- Testing recommendations
- Conclusion

### 6. Report Results

After writing the review file:
- Report the location of the review file
- Summarize the overall assessment
- List any blocking issues found

## Examples

**Comprehensive review:**
```
/review-pr https://github.com/ROCm/TheRock/pull/2761
```

**Focused style review:**
```
/review-pr https://github.com/ROCm/TheRock/pull/2761 style
```

**Multiple focused reviews:**
```
/review-pr https://github.com/ROCm/TheRock/pull/2761 tests security
```
