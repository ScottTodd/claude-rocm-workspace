"""Collect CI timing data from GitHub Actions workflow runs.

Queries the GitHub API via `gh` CLI to extract per-run and per-job timing
metrics for TheRock CI workflows. Outputs CSV for analysis.

Usage:
    python scripts/ci_time_to_signal.py [OPTIONS]

Examples:
    # Collect last 30 days of CI runs on main
    python scripts/ci_time_to_signal.py --days 30 --branch main

    # Collect from a specific workflow
    python scripts/ci_time_to_signal.py --workflow ci.yml --days 14

    # Include pull_request events too
    python scripts/ci_time_to_signal.py --days 7 --events push pull_request

    # Query a single run (for debugging)
    python scripts/ci_time_to_signal.py --run-id 23274411292
"""

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO = "ROCm/TheRock"

# Main CI workflows we care about
DEFAULT_WORKFLOWS = [
    "ci.yml",
]


@dataclass
class JobTiming:
    run_id: int
    run_created_at: str
    job_name: str
    category: str  # build, test, pytorch, python, validate, setup, other
    platform: str  # Linux, Windows
    variant: str  # e.g. gfx94X-dcgpu, gfx110X-all
    conclusion: str
    created_at: str
    started_at: str
    completed_at: str
    queue_seconds: float
    duration_seconds: float
    runner_labels: str  # comma-separated


@dataclass
class RunTiming:
    run_id: int
    workflow_name: str
    workflow_file: str
    event: str
    branch: str
    conclusion: str
    created_at: str
    updated_at: str
    # Wall clock
    wall_seconds: float
    # Time to first failure (seconds from run created_at to first failed job completed_at)
    # -1 if no failures
    first_failure_seconds: float
    # Time to signal: min of first_failure_seconds and wall_seconds
    # For successful runs, this equals wall_seconds
    time_to_signal_seconds: float
    # Was the run skipped (setup-only, early exit)?
    skipped: bool
    # Job counts
    total_jobs: int
    failed_jobs: int
    skipped_jobs: int
    successful_jobs: int
    # Aggregate timing by category
    # Build jobs (name contains "Build Artifacts" or "Build release")
    build_max_duration_seconds: float
    build_max_queue_seconds: float
    build_total_queue_seconds: float
    # Test jobs (name contains "Test")
    test_max_duration_seconds: float
    test_max_queue_seconds: float
    test_total_queue_seconds: float
    # PyTorch build jobs
    pytorch_max_duration_seconds: float
    # Python package build jobs
    python_max_duration_seconds: float
    # Longest single job
    longest_job_name: str
    longest_job_seconds: float
    # Longest queue
    longest_queue_job_name: str
    longest_queue_seconds: float
    # HTML URL for reference
    html_url: str


def gh_api(endpoint: str, params: dict | None = None, retries: int = 3) -> dict:
    """Call GitHub API via gh CLI. Returns parsed JSON.

    Retries on transient errors (5xx, network issues).
    """
    import time

    cmd = ["gh", "api", endpoint, "--method", "GET"]
    for k, v in (params or {}).items():
        cmd.extend(["-f", f"{k}={v}"])

    for attempt in range(retries):
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode == 0:
            return json.loads(result.stdout)

        stderr = result.stderr.strip()
        is_transient = any(
            s in stderr for s in ("502", "503", "504", "Server Error", "timeout")
        )
        if is_transient and attempt < retries - 1:
            wait = 2 ** attempt * 5  # 5s, 10s, 20s
            print(
                f"  Retrying ({attempt+1}/{retries}) after {wait}s: {stderr[:80]}",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue

        raise RuntimeError(
            f"gh api failed: {stderr}\nCommand: {' '.join(cmd)}"
        )
    # Unreachable, but satisfies type checker
    raise RuntimeError("gh api: exhausted retries")


def parse_dt(iso_str: str) -> datetime:
    """Parse ISO 8601 datetime string from GitHub API."""
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def seconds_between(start: str, end: str) -> float:
    """Seconds between two ISO 8601 timestamps. Returns -1 if either is None/empty."""
    if not start or not end:
        return -1.0
    return (parse_dt(end) - parse_dt(start)).total_seconds()


def categorize_job(name: str) -> str:
    """Categorize a job by name into build/test/pytorch/python/setup/other."""
    lower = name.lower()
    if "setup" in lower and "/" not in lower:
        return "setup"
    if "build artifacts" in lower or "build release" in lower:
        return "build"
    if "build pytorch" in lower:
        return "pytorch"
    if "build python" in lower:
        return "python"
    if "test" in lower:
        return "test"
    if "validate" in lower:
        return "validate"
    if "summary" in lower:
        return "summary"
    return "other"


def parse_variant(name: str) -> tuple[str, str]:
    """Extract platform and GPU variant from job name.

    Job names look like:
        Linux::gfx94X-dcgpu::release / Build Artifacts / ...
        Windows::gfx110X-all::release / Test Artifacts / ...
        setup / setup
        CI Summary

    Returns (platform, variant) e.g. ("Linux", "gfx94X-dcgpu").
    Returns ("", "") if the name doesn't match the pattern.
    """
    if "::" not in name:
        return ("", "")
    parts = name.split("::")
    if len(parts) >= 2:
        return (parts[0].strip(), parts[1].strip())
    return ("", "")


def fetch_run_jobs(run_id: int) -> list[dict]:
    """Fetch all jobs for a workflow run, handling pagination."""
    jobs = []
    page = 1
    while True:
        data = gh_api(
            f"repos/{REPO}/actions/runs/{run_id}/jobs",
            {"per_page": "100", "page": str(page)},
        )
        jobs.extend(data.get("jobs", []))
        if len(jobs) >= data.get("total_count", 0):
            break
        page += 1
    return jobs


def analyze_run(run: dict) -> tuple[RunTiming, list[JobTiming]]:
    """Analyze a single workflow run and its jobs.

    Returns (run_timing, job_timings) where job_timings is the per-job detail.
    """
    run_id = run["id"]
    created = run["created_at"]
    updated = run["updated_at"]
    wall = seconds_between(created, updated)

    jobs = fetch_run_jobs(run_id)

    # Classify jobs
    total = len(jobs)
    failed = 0
    skipped_count = 0
    successful = 0
    first_failure_completed: datetime | None = None
    is_skipped_run = False

    build_durations = []
    build_queues = []
    test_durations = []
    test_queues = []
    pytorch_durations = []
    python_durations = []

    longest_job_name = ""
    longest_job_dur = 0.0
    longest_queue_name = ""
    longest_queue_dur = 0.0

    job_timings: list[JobTiming] = []

    for j in jobs:
        conclusion = j.get("conclusion") or "unknown"
        if conclusion == "skipped":
            skipped_count += 1
            continue
        if conclusion == "failure" or conclusion == "cancelled":
            failed += 1
        elif conclusion == "success":
            successful += 1

        # Queue and duration
        queue_s = seconds_between(j["created_at"], j["started_at"])
        dur_s = seconds_between(j["started_at"], j["completed_at"])

        # Skip jobs with bogus timing (skipped jobs sometimes have weird timestamps)
        if dur_s < 0:
            continue

        name = j["name"]
        cat = categorize_job(name)
        labels = ",".join(j.get("labels", []))
        platform, variant = parse_variant(name)

        # Record per-job detail
        job_timings.append(JobTiming(
            run_id=run_id,
            run_created_at=created,
            job_name=name,
            category=cat,
            platform=platform,
            variant=variant,
            conclusion=conclusion,
            created_at=j["created_at"],
            started_at=j["started_at"],
            completed_at=j["completed_at"],
            queue_seconds=queue_s,
            duration_seconds=dur_s,
            runner_labels=labels,
        ))

        # Track first failure
        if conclusion in ("failure", "cancelled") and j.get("completed_at"):
            completed_dt = parse_dt(j["completed_at"])
            if first_failure_completed is None or completed_dt < first_failure_completed:
                first_failure_completed = completed_dt

        # Aggregate by category
        if cat == "build":
            build_durations.append(dur_s)
            build_queues.append(queue_s)
        elif cat == "test":
            test_durations.append(dur_s)
            test_queues.append(queue_s)
        elif cat == "pytorch":
            pytorch_durations.append(dur_s)
        elif cat == "python":
            python_durations.append(dur_s)

        # Track longest
        if dur_s > longest_job_dur:
            longest_job_dur = dur_s
            longest_job_name = name
        if queue_s > longest_queue_dur:
            longest_queue_dur = queue_s
            longest_queue_name = name

    # Detect skipped runs: only setup + skipped jobs, very short wall time
    non_skipped = total - skipped_count
    if non_skipped <= 2 and wall < 300:
        is_skipped_run = True

    # First failure timing
    first_failure_s = -1.0
    if first_failure_completed is not None:
        first_failure_s = (first_failure_completed - parse_dt(created)).total_seconds()

    # Time to signal
    if first_failure_s > 0:
        time_to_signal = first_failure_s
    else:
        time_to_signal = wall

    run_timing = RunTiming(
        run_id=run_id,
        workflow_name=run["name"],
        workflow_file=run["path"],
        event=run["event"],
        branch=run.get("head_branch", ""),
        conclusion=run.get("conclusion", ""),
        created_at=created,
        updated_at=updated,
        wall_seconds=wall,
        first_failure_seconds=first_failure_s,
        time_to_signal_seconds=time_to_signal,
        skipped=is_skipped_run,
        total_jobs=total,
        failed_jobs=failed,
        skipped_jobs=skipped_count,
        successful_jobs=successful,
        build_max_duration_seconds=max(build_durations, default=0.0),
        build_max_queue_seconds=max(build_queues, default=0.0),
        build_total_queue_seconds=sum(build_queues),
        test_max_duration_seconds=max(test_durations, default=0.0),
        test_max_queue_seconds=max(test_queues, default=0.0),
        test_total_queue_seconds=sum(test_queues),
        pytorch_max_duration_seconds=max(pytorch_durations, default=0.0),
        python_max_duration_seconds=max(python_durations, default=0.0),
        longest_job_name=longest_job_name[:100],
        longest_job_seconds=longest_job_dur,
        longest_queue_job_name=longest_queue_name[:100],
        longest_queue_seconds=longest_queue_dur,
        html_url=run.get("html_url", ""),
    )
    return run_timing, job_timings


def fetch_workflow_runs(
    workflow_file: str,
    days: int,
    branch: str | None,
    events: list[str],
) -> list[dict]:
    """Fetch completed workflow runs within the time window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    runs = []

    for event in events:
        page = 1
        while True:
            params = {
                "per_page": "100",
                "page": str(page),
                "status": "completed",
                "event": event,
            }
            if branch:
                params["branch"] = branch
            # Use created filter to limit time range
            params["created"] = f">={cutoff.strftime('%Y-%m-%d')}"

            data = gh_api(
                f"repos/{REPO}/actions/workflows/{workflow_file}/runs",
                params,
            )
            page_runs = data.get("workflow_runs", [])
            if not page_runs:
                break

            # Filter by cutoff (API filter is date-level, not datetime)
            for r in page_runs:
                if parse_dt(r["created_at"]) >= cutoff:
                    runs.append(r)

            # Stop if we've gone past the cutoff
            oldest = parse_dt(page_runs[-1]["created_at"])
            if oldest < cutoff:
                break

            page += 1
            # Safety limit
            if page > 20:
                print(
                    f"  Warning: hit page limit (20) for {workflow_file} {event}",
                    file=sys.stderr,
                )
                break

    return runs


def main():
    parser = argparse.ArgumentParser(description="Collect CI timing data")
    parser.add_argument(
        "--workflow",
        nargs="+",
        default=DEFAULT_WORKFLOWS,
        help="Workflow file names to query (default: ci.yml)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to look back (default: 30)",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Filter by branch (default: all branches)",
    )
    parser.add_argument(
        "--events",
        nargs="+",
        default=["push"],
        help="Event types to include (default: push)",
    )
    parser.add_argument(
        "--run-id",
        type=int,
        default=None,
        help="Analyze a single run ID (for debugging)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV file (default: stdout)",
    )
    parser.add_argument(
        "--jobs-csv",
        type=Path,
        default=None,
        help="Also output per-job detail CSV to this path",
    )
    args = parser.parse_args()

    results: list[RunTiming] = []
    all_jobs: list[JobTiming] = []

    if args.run_id:
        # Single run mode
        run_data = gh_api(f"repos/{REPO}/actions/runs/{args.run_id}")
        print(f"Analyzing run {args.run_id}...", file=sys.stderr)
        timing, job_timings = analyze_run(run_data)
        results.append(timing)
        all_jobs.extend(job_timings)
    else:
        # Batch mode
        for wf in args.workflow:
            print(
                f"Fetching {wf} runs (last {args.days} days, "
                f"events={args.events}, branch={args.branch})...",
                file=sys.stderr,
            )
            runs = fetch_workflow_runs(wf, args.days, args.branch, args.events)
            print(f"  Found {len(runs)} runs", file=sys.stderr)

            for i, run in enumerate(runs):
                run_id = run["id"]
                print(
                    f"  [{i+1}/{len(runs)}] Analyzing run {run_id} "
                    f"({run['created_at'][:10]})...",
                    file=sys.stderr,
                )
                timing, job_timings = analyze_run(run)
                results.append(timing)
                all_jobs.extend(job_timings)

    # Sort by created_at
    results.sort(key=lambda r: r.created_at)

    # Output CSV
    if not results:
        print("No runs found.", file=sys.stderr)
        return

    fieldnames = list(asdict(results[0]).keys())

    out_file = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
    writer = csv.DictWriter(out_file, fieldnames=fieldnames)
    writer.writeheader()
    for r in results:
        writer.writerow(asdict(r))

    if args.output:
        out_file.close()
        print(f"Wrote {len(results)} rows to {args.output}", file=sys.stderr)

    # Write per-job detail CSV
    if args.jobs_csv and all_jobs:
        job_fields = list(asdict(all_jobs[0]).keys())
        with open(args.jobs_csv, "w", newline="", encoding="utf-8") as jf:
            jw = csv.DictWriter(jf, fieldnames=job_fields)
            jw.writeheader()
            for j in all_jobs:
                jw.writerow(asdict(j))
        print(f"Wrote {len(all_jobs)} job rows to {args.jobs_csv}", file=sys.stderr)

    # Summary stats
    non_skipped = [r for r in results if not r.skipped]
    if non_skipped:
        walls = [r.wall_seconds for r in non_skipped]
        signals = [r.time_to_signal_seconds for r in non_skipped]
        queues = [r.longest_queue_seconds for r in non_skipped]

        def fmt(s: float) -> str:
            h, rem = divmod(int(s), 3600)
            m, sec = divmod(rem, 60)
            return f"{h}h{m:02d}m"

        print(f"\n--- Summary ({len(non_skipped)} non-skipped runs) ---", file=sys.stderr)
        print(f"  Wall time:       median={fmt(sorted(walls)[len(walls)//2])}  "
              f"max={fmt(max(walls))}", file=sys.stderr)
        print(f"  Time to signal:  median={fmt(sorted(signals)[len(signals)//2])}  "
              f"max={fmt(max(signals))}", file=sys.stderr)
        print(f"  Max queue time:  median={fmt(sorted(queues)[len(queues)//2])}  "
              f"max={fmt(max(queues))}", file=sys.stderr)
        failed_runs = [r for r in non_skipped if r.conclusion == "failure"]
        print(f"  Failure rate:    {len(failed_runs)}/{len(non_skipped)} "
              f"({100*len(failed_runs)/len(non_skipped):.0f}%)", file=sys.stderr)


if __name__ == "__main__":
    main()
