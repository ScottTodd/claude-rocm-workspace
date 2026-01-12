---
description: Review the current local branch
allowed-tools: Bash(git:*), Read, Write, Glob, Grep, Task
argument-hint: [review-type ...]
---

Review the current local branch comprehensively or with specific focus areas.

## Arguments

- `$ARGUMENTS` contains: `[review-type ...]`
- Optional review types: `style`, `tests`, `documentation`, `architecture`, `security`, `performance`
- If no review types specified, perform a comprehensive review (all aspects)

## Process

### 1. Get Branch Information

```bash
git branch --show-current
git log --oneline main..HEAD  # or upstream/main
git diff --stat main..HEAD
```

Determine:
- Current branch name
- Base branch (main or upstream/main)
- Number of commits
- Files changed

### 2. Determine Review Counter

Scan `reviews/local_*.md` files to find the next counter number (001, 002, etc.).

### 3. Sanitize Branch Name

Convert branch name to filename-safe format:
- Replace `/` with `-`
- Keep other characters

Example: `users/myname/fix-bug` becomes `users-myname-fix-bug`

### 4. Review Setup

- Read `reviews/REVIEW_GUIDELINES.md` for severity levels and format
- Read `reviews/REVIEW_TYPES.md` if doing focused reviews
- Determine output filename: `reviews/local_{COUNTER}_{branch-name}.md` or `reviews/local_{COUNTER}_{branch-name}_{TYPE}.md`

### 5. Perform Review

Get the diff to review:
```bash
git diff main..HEAD
```

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

### 6. Write Review File

Create the review file following the template in `REVIEW_GUIDELINES.md`:
- Header with branch name, base, date, commits
- Summary of changes
- Overall assessment (APPROVED / CHANGES REQUESTED / REJECTED)
- Detailed findings with severity markers (BLOCKING, IMPORTANT, SUGGESTION, FUTURE WORK)
- Recommendations organized by severity
- Testing recommendations
- Conclusion

### 7. Report Results

After writing the review file:
- Report the location of the review file
- Summarize the overall assessment
- List any blocking issues found

## Examples

**Comprehensive review:**
```
/review-branch
```

**Focused style review:**
```
/review-branch style
```

**Multiple focused reviews:**
```
/review-branch tests security
```
