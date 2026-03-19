"""Generate plots from CI timing data collected by ci_time_to_signal.py.

Usage:
    python prototypes/ci_time_to_signal_plots.py /d/scratch/claude/ci_timing_7d.csv
    python prototypes/ci_time_to_signal_plots.py /d/scratch/claude/ci_timing_7d.csv --jobs-csv /d/scratch/claude/ci_jobs_7d.csv

Outputs PNG files next to the input CSV.
"""

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np


def load_data(csv_path: Path) -> list[dict]:
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # Convert numeric fields
    numeric_fields = [
        "wall_seconds", "first_failure_seconds", "time_to_signal_seconds",
        "total_jobs", "failed_jobs", "skipped_jobs", "successful_jobs",
        "build_max_duration_seconds", "build_max_queue_seconds",
        "build_total_queue_seconds", "test_max_duration_seconds",
        "test_max_queue_seconds", "test_total_queue_seconds",
        "pytorch_max_duration_seconds", "python_max_duration_seconds",
        "longest_job_seconds", "longest_queue_seconds",
    ]
    for r in rows:
        for f in numeric_fields:
            r[f] = float(r[f])
        r["skipped"] = r["skipped"] == "True"
        r["created_dt"] = datetime.fromisoformat(
            r["created_at"].replace("Z", "+00:00")
        )
    return rows


def to_hours(seconds: float) -> float:
    return seconds / 3600.0


def setup_date_axis(ax):
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")


def add_trend_line(ax, dates: list[datetime], values: list[float], color, label=None):
    """Add a LOWESS-style rolling median trend line.

    Uses a rolling window of timestamps rather than indices so it handles
    uneven spacing. Falls back to simple rolling median by index if numpy
    isn't sufficient.
    """
    if len(dates) < 5:
        return
    # Convert to numeric for sorting/windowing
    timestamps = np.array([d.timestamp() for d in dates])
    vals = np.array(values)
    order = np.argsort(timestamps)
    timestamps = timestamps[order]
    vals = vals[order]

    # Rolling mean with a window of ~20% of the data or at least 5 points
    window = max(5, len(vals) // 5)
    smoothed_t = []
    smoothed_v = []
    for i in range(len(vals)):
        lo = max(0, i - window // 2)
        hi = min(len(vals), i + window // 2 + 1)
        smoothed_t.append(timestamps[i])
        smoothed_v.append(np.mean(vals[lo:hi]))

    # Convert back to datetimes
    trend_dates = [datetime.fromtimestamp(t, tz=timezone.utc) for t in smoothed_t]
    ax.plot(trend_dates, smoothed_v, color=color, linewidth=2.5, alpha=0.8,
            label=label)


def plot_time_to_signal(rows: list[dict], out_dir: Path, wf_label: str = "CI",
                        max_hours: float | None = None, suffix: str = ""):
    """Plot 1: Time to signal and wall time over time."""
    non_skipped = [r for r in rows if not r["skipped"]]
    if max_hours:
        non_skipped = [r for r in non_skipped
                       if to_hours(r["wall_seconds"]) <= max_hours]

    dates = [r["created_dt"] for r in non_skipped]
    wall_h = [to_hours(r["wall_seconds"]) for r in non_skipped]
    signal_h = [to_hours(r["time_to_signal_seconds"]) for r in non_skipped]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.scatter(dates, wall_h, alpha=0.3, s=20, color="tab:blue")
    add_trend_line(ax, dates, wall_h, color="tab:blue", label="Time to completion")
    ax.scatter(dates, signal_h, alpha=0.3, s=30, color="tab:red")
    add_trend_line(ax, dates, signal_h, color="tab:red", label="Time to first failure")

    title_extra = f" (< {max_hours:.0f}h)" if max_hours else ""
    ax.set_ylabel("Hours")
    ax.set_title(f"{wf_label}: Time to First Failure vs Completion{title_extra}")
    ax.legend()
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    setup_date_axis(ax)

    filename = f"time_to_signal{suffix}.png"
    fig.tight_layout()
    fig.savefig(out_dir / filename, dpi=150)
    plt.close(fig)
    print(f"  Saved {filename}")


def plot_queue_times(rows: list[dict], out_dir: Path, wf_label: str = "CI",
                     max_hours: float | None = None, suffix: str = ""):
    """Plot 2: Build vs test queue times."""
    non_skipped = [r for r in rows if not r["skipped"]]
    if max_hours:
        non_skipped = [r for r in non_skipped
                       if to_hours(r["test_max_queue_seconds"]) <= max_hours]

    dates = [r["created_dt"] for r in non_skipped]
    build_q = [to_hours(r["build_max_queue_seconds"]) for r in non_skipped]
    test_q = [to_hours(r["test_max_queue_seconds"]) for r in non_skipped]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.scatter(dates, build_q, alpha=0.3, s=25, color="tab:green")
    add_trend_line(ax, dates, build_q, color="tab:green", label="Build runner queue (max)")
    ax.scatter(dates, test_q, alpha=0.3, s=25, color="tab:orange")
    add_trend_line(ax, dates, test_q, color="tab:orange", label="Test runner queue (max)")

    title_extra = f" (< {max_hours:.0f}h)" if max_hours else ""
    ax.set_ylabel("Hours")
    ax.set_title(f"{wf_label}: Runner Queue Times{title_extra}")
    ax.legend()
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    setup_date_axis(ax)

    filename = f"queue_times{suffix}.png"
    fig.tight_layout()
    fig.savefig(out_dir / filename, dpi=150)
    plt.close(fig)
    print(f"  Saved {filename}")


def plot_build_durations(rows: list[dict], out_dir: Path, wf_label: str = "CI"):
    """Plot 3: Max build duration over time."""
    non_skipped = [r for r in rows if not r["skipped"] and r["build_max_duration_seconds"] > 0]

    dates = [r["created_dt"] for r in non_skipped]
    build_h = [to_hours(r["build_max_duration_seconds"]) for r in non_skipped]
    pytorch_h = [to_hours(r["pytorch_max_duration_seconds"]) for r in non_skipped]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.scatter(dates, build_h, alpha=0.6, s=25, label="Build artifacts (max)", color="tab:blue")
    ax.scatter(dates, pytorch_h, alpha=0.6, s=25, label="PyTorch build (max)", color="tab:purple")

    ax.set_ylabel("Hours")
    ax.set_title(f"{wf_label}: Build Job Durations (max per run)")
    ax.legend()
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    setup_date_axis(ax)

    fig.tight_layout()
    fig.savefig(out_dir / "build_durations.png", dpi=150)
    plt.close(fig)
    print(f"  Saved build_durations.png")


def plot_hour_of_day(rows: list[dict], out_dir: Path, wf_label: str = "CI"):
    """Plot 4: Queue time by hour of day (UTC) — shows daily patterns."""
    non_skipped = [r for r in rows if not r["skipped"]]

    hours = [r["created_dt"].hour for r in non_skipped]
    test_q = [to_hours(r["test_max_queue_seconds"]) for r in non_skipped]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(hours, test_q, alpha=0.5, s=30, color="tab:orange")

    ax.set_xlabel("Hour of Day (UTC)")
    ax.set_ylabel("Test Runner Max Queue (hours)")
    ax.set_title(f"{wf_label}: Test Runner Queue by Hour of Day")
    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(range(0, 24, 2))
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_dir / "queue_by_hour.png", dpi=150)
    plt.close(fig)
    print(f"  Saved queue_by_hour.png")


def plot_day_of_week(rows: list[dict], out_dir: Path, wf_label: str = "CI"):
    """Plot 5: Queue time by day of week."""
    non_skipped = [r for r in rows if not r["skipped"]]

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days = [r["created_dt"].weekday() for r in non_skipped]
    test_q = [to_hours(r["test_max_queue_seconds"]) for r in non_skipped]
    signal_h = [to_hours(r["time_to_signal_seconds"]) for r in non_skipped]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    ax1.scatter(days, test_q, alpha=0.5, s=30, color="tab:orange")
    ax1.set_xlabel("Day of Week")
    ax1.set_ylabel("Hours")
    ax1.set_title(f"{wf_label}: Test Runner Queue by Day")
    ax1.set_xticks(range(7))
    ax1.set_xticklabels(day_names)
    ax1.set_ylim(bottom=0)
    ax1.grid(True, alpha=0.3)

    ax2.scatter(days, signal_h, alpha=0.5, s=30, color="tab:red")
    ax2.set_xlabel("Day of Week")
    ax2.set_ylabel("Hours")
    ax2.set_title(f"{wf_label}: Time to Signal by Day")
    ax2.set_xticks(range(7))
    ax2.set_xticklabels(day_names)
    ax2.set_ylim(bottom=0)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_dir / "by_day_of_week.png", dpi=150)
    plt.close(fig)
    print(f"  Saved by_day_of_week.png")


def plot_failure_rate(rows: list[dict], out_dir: Path, wf_label: str = "CI"):
    """Plot 6: Daily failure rate (rolling)."""
    non_skipped = sorted(
        [r for r in rows if not r["skipped"]],
        key=lambda r: r["created_dt"]
    )
    if len(non_skipped) < 3:
        return

    dates = [r["created_dt"] for r in non_skipped]
    failed = [1.0 if r["conclusion"] == "failure" else 0.0 for r in non_skipped]

    # Rolling average (window of 10 runs)
    window = min(10, len(failed))
    rolling = []
    for i in range(len(failed)):
        start = max(0, i - window + 1)
        rolling.append(sum(failed[start:i+1]) / (i - start + 1) * 100)

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(dates, [f * 100 for f in failed], width=0.02, alpha=0.3,
           color="tab:red", label="Per-run (100%=fail)")
    ax.plot(dates, rolling, color="tab:red", linewidth=2,
            label=f"Rolling avg ({window} runs)")

    ax.set_ylabel("Failure Rate (%)")
    ax.set_title(f"{wf_label}: Failure Rate Over Time")
    ax.legend()
    ax.set_ylim(0, 105)
    ax.grid(True, alpha=0.3)
    setup_date_axis(ax)

    fig.tight_layout()
    fig.savefig(out_dir / "failure_rate.png", dpi=150)
    plt.close(fig)
    print(f"  Saved failure_rate.png")


def load_jobs(csv_path: Path) -> list[dict]:
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["queue_seconds"] = float(r["queue_seconds"])
        r["duration_seconds"] = float(r["duration_seconds"])
        r["run_created_dt"] = datetime.fromisoformat(
            r["run_created_at"].replace("Z", "+00:00")
        )
    return rows


def plot_queue_by_variant(jobs: list[dict], out_dir: Path, wf_label: str = "CI"):
    """Plot 8: Test queue times broken down by GPU variant, one plot per platform."""
    test_jobs = [j for j in jobs if j["category"] == "test" and j["variant"]]
    platforms = sorted(set(j["platform"] for j in test_jobs if j["platform"]))

    for platform in platforms:
        pj = [j for j in test_jobs if j["platform"] == platform]
        variants = sorted(set(j["variant"] for j in pj))
        cmap = plt.colormaps["tab10"]
        colors = {v: cmap(i) for i, v in enumerate(variants)}

        fig, ax = plt.subplots(figsize=(14, 6))
        for v in variants:
            vj = [j for j in pj if j["variant"] == v]
            dates = [j["run_created_dt"] for j in vj]
            queues = [to_hours(j["queue_seconds"]) for j in vj]
            ax.scatter(dates, queues, alpha=0.3, s=20, color=colors[v])
            add_trend_line(ax, dates, queues, color=colors[v], label=v)

        ax.set_ylabel("Queue Time (hours)")
        ax.set_title(f"{wf_label}: Test Runner Queue by Variant ({platform})")
        ax.legend(loc="upper left")
        ax.set_ylim(bottom=0)
        ax.grid(True, alpha=0.3)
        setup_date_axis(ax)

        filename = f"queue_by_variant_{platform.lower()}.png"
        fig.tight_layout()
        fig.savefig(out_dir / filename, dpi=150)
        plt.close(fig)
        print(f"  Saved {filename}")


def plot_build_by_variant(jobs: list[dict], out_dir: Path, wf_label: str = "CI"):
    """Plot 9: Build durations broken down by variant, one plot per platform."""
    build_jobs = [j for j in jobs if j["category"] == "build" and j["variant"]]
    platforms = sorted(set(j["platform"] for j in build_jobs if j["platform"]))

    for platform in platforms:
        pj = [j for j in build_jobs if j["platform"] == platform]
        variants = sorted(set(j["variant"] for j in pj))
        cmap = plt.colormaps["tab10"]
        colors = {v: cmap(i) for i, v in enumerate(variants)}

        fig, ax = plt.subplots(figsize=(14, 6))

        for v in variants:
            vj = [j for j in pj if j["variant"] == v]
            dates = [j["run_created_dt"] for j in vj]
            durs = [to_hours(j["duration_seconds"]) for j in vj]
            ax.scatter(dates, durs, alpha=0.3, s=20, color=colors[v])
            add_trend_line(ax, dates, durs, color=colors[v], label=v)

        ax.set_ylabel("Hours")
        ax.set_title(f"{wf_label}: Build Duration by Variant ({platform})")
        ax.legend(loc="upper left", fontsize=8)
        ax.set_ylim(bottom=0)
        ax.grid(True, alpha=0.3)
        setup_date_axis(ax)

        filename = f"build_by_variant_{platform.lower()}.png"
        fig.tight_layout()
        fig.savefig(out_dir / filename, dpi=150)
        plt.close(fig)
        print(f"  Saved {filename}")


def plot_queue_by_runner(jobs: list[dict], out_dir: Path, wf_label: str = "CI"):
    """Plot 10: Queue times by runner label (for test jobs)."""
    test_jobs = [j for j in jobs if j["category"] == "test" and j["runner_labels"]]

    runners = sorted(set(j["runner_labels"] for j in test_jobs))
    cmap = plt.colormaps["tab10"]
    colors = {r: cmap(i) for i, r in enumerate(runners)}

    fig, ax = plt.subplots(figsize=(14, 6))
    for r in runners:
        rj = [j for j in test_jobs if j["runner_labels"] == r]
        dates = [j["run_created_dt"] for j in rj]
        queues = [to_hours(j["queue_seconds"]) for j in rj]
        # Shorten label for legend
        short = r.split(",")[0] if "," in r else r
        ax.scatter(dates, queues, alpha=0.6, s=30, label=short, color=colors[r])

    ax.set_ylabel("Queue Time (hours)")
    ax.set_title(f"{wf_label}: Test Runner Queue by Runner Label")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    setup_date_axis(ax)

    fig.tight_layout()
    fig.savefig(out_dir / "queue_by_runner.png", dpi=150)
    plt.close(fig)
    print(f"  Saved queue_by_runner.png")


def _compute_platform_run_data(jobs: list[dict]) -> dict[str, list[dict]]:
    """Compute per-run per-platform completion and first failure times.

    Returns {platform: [{"created_dt", "completion_h", "first_failure_h", ...}]}
    """
    from collections import defaultdict

    groups = defaultdict(list)
    for j in jobs:
        if not j["platform"] or not j["completed_at"]:
            continue
        groups[(j["run_id"], j["platform"])].append(j)

    platform_data: dict[str, list[dict]] = {}
    for (rid, plat), pjobs in groups.items():
        run_created = datetime.fromisoformat(
            pjobs[0]["run_created_at"].replace("Z", "+00:00")
        )

        completed_times = [
            datetime.fromisoformat(j["completed_at"].replace("Z", "+00:00"))
            for j in pjobs
        ]
        completion_s = (max(completed_times) - run_created).total_seconds()

        failed_times = [
            datetime.fromisoformat(j["completed_at"].replace("Z", "+00:00"))
            for j in pjobs if j["conclusion"] == "failure"
        ]
        first_failure_s = (
            (min(failed_times) - run_created).total_seconds()
            if failed_times else completion_s
        )

        platform_data.setdefault(plat, []).append({
            "created_dt": run_created,
            "completion_h": completion_s / 3600,
            "first_failure_h": first_failure_s / 3600,
            "has_failure": bool(failed_times),
        })

    # Sort each platform's data by time
    for plat in platform_data:
        platform_data[plat].sort(key=lambda r: r["created_dt"])

    return platform_data


def _plot_platform_signal(run_data: list[dict], platform: str, out_dir: Path,
                          wf_label: str, max_hours: float | None = None,
                          suffix: str = ""):
    """Plot time to completion and first failure for one platform."""
    if max_hours:
        run_data = [r for r in run_data if r["completion_h"] <= max_hours]

    if not run_data:
        return

    dates = [r["created_dt"] for r in run_data]
    completion_h = [r["completion_h"] for r in run_data]
    first_failure_h = [r["first_failure_h"] for r in run_data]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.scatter(dates, completion_h, alpha=0.3, s=20, color="tab:blue")
    add_trend_line(ax, dates, completion_h, color="tab:blue",
                   label="Time to completion")
    ax.scatter(dates, first_failure_h, alpha=0.3, s=30, color="tab:red")
    add_trend_line(ax, dates, first_failure_h, color="tab:red",
                   label="Time to first failure")

    title_extra = f" (< {max_hours:.0f}h)" if max_hours else ""
    ax.set_ylabel("Hours")
    ax.set_title(
        f"{wf_label}: First Failure vs Completion — {platform}{title_extra}"
    )
    ax.legend()
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    setup_date_axis(ax)

    filename = f"time_to_signal_{platform.lower()}{suffix}.png"
    fig.tight_layout()
    fig.savefig(out_dir / filename, dpi=150)
    plt.close(fig)
    print(f"  Saved {filename}")


def plot_time_to_signal_by_platform(jobs: list[dict], out_dir: Path,
                                     wf_label: str = "CI"):
    """Plot time to completion and first failure, split by platform.

    Generates both unfiltered and filtered (< 12h) variants.
    """
    platform_data = _compute_platform_run_data(jobs)

    for platform, run_data in sorted(platform_data.items()):
        # Unfiltered
        _plot_platform_signal(run_data, platform, out_dir, wf_label)
        # Filtered
        _plot_platform_signal(run_data, platform, out_dir, wf_label,
                              max_hours=12, suffix="_filtered")


def plot_signal_breakdown(rows: list[dict], out_dir: Path, wf_label: str = "CI",
                          max_hours: float | None = None, suffix: str = ""):
    """Plot 7: Stacked view — build time + queue time = time to signal."""
    non_skipped = sorted(
        [r for r in rows if not r["skipped"]],
        key=lambda r: r["created_dt"]
    )
    if max_hours:
        non_skipped = [r for r in non_skipped
                       if to_hours(r["wall_seconds"]) <= max_hours]

    dates = [r["created_dt"] for r in non_skipped]
    build_h = [to_hours(r["build_max_duration_seconds"]) for r in non_skipped]
    build_q_h = [to_hours(r["build_max_queue_seconds"]) for r in non_skipped]
    test_q_h = [to_hours(r["test_max_queue_seconds"]) for r in non_skipped]
    signal_h = [to_hours(r["time_to_signal_seconds"]) for r in non_skipped]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.scatter(dates, build_q_h, alpha=0.3, s=20, color="tab:green")
    add_trend_line(ax, dates, build_q_h, color="tab:green", label="Build queue")
    ax.scatter(dates, build_h, alpha=0.3, s=20, color="tab:blue")
    add_trend_line(ax, dates, build_h, color="tab:blue", label="Build duration")
    ax.scatter(dates, test_q_h, alpha=0.3, s=20, color="tab:orange")
    add_trend_line(ax, dates, test_q_h, color="tab:orange", label="Test queue")
    ax.scatter(dates, signal_h, alpha=0.3, s=30, color="tab:red", marker="x")
    add_trend_line(ax, dates, signal_h, color="tab:red", label="Time to signal")

    title_extra = f" (< {max_hours:.0f}h)" if max_hours else ""
    ax.set_ylabel("Hours")
    ax.set_title(f"{wf_label}: Time to Signal Breakdown{title_extra}")
    ax.legend()
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    setup_date_axis(ax)

    filename = f"signal_breakdown{suffix}.png"
    fig.tight_layout()
    fig.savefig(out_dir / filename, dpi=150)
    plt.close(fig)
    print(f"  Saved {filename}")


def main():
    parser = argparse.ArgumentParser(description="Plot CI timing data")
    parser.add_argument("csv_file", type=Path, help="Input CSV from ci_time_to_signal.py")
    parser.add_argument("--jobs-csv", type=Path, default=None,
                        help="Per-job detail CSV for variant/runner breakdowns")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output directory for PNGs (default: same as CSV)")
    args = parser.parse_args()

    out_dir = args.output_dir or args.csv_file.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading {args.csv_file}...")
    rows = load_data(args.csv_file)
    print(f"  {len(rows)} total runs, {sum(1 for r in rows if not r['skipped'])} non-skipped")

    # Derive a label from the data for plot titles
    workflow_names = set(r.get("workflow_name", "") for r in rows if r.get("workflow_name"))
    events = set(r.get("event", "") for r in rows if r.get("event"))
    wf_part = " / ".join(sorted(workflow_names)) if workflow_names else "CI"
    event_part = " + ".join(sorted(events)) if events else "all events"
    wf_label = f"{wf_part} (on {event_part})"

    print("Generating run-level plots...")
    # Full range
    plot_time_to_signal(rows, out_dir, wf_label)
    plot_queue_times(rows, out_dir, wf_label)
    plot_signal_breakdown(rows, out_dir, wf_label)
    # Filtered (exclude 24h timeout outliers)
    plot_time_to_signal(rows, out_dir, wf_label, max_hours=12, suffix="_filtered")
    plot_queue_times(rows, out_dir, wf_label, max_hours=12, suffix="_filtered")
    plot_signal_breakdown(rows, out_dir, wf_label, max_hours=12, suffix="_filtered")
    # These don't need filtering
    plot_build_durations(rows, out_dir, wf_label)
    plot_hour_of_day(rows, out_dir, wf_label)
    plot_day_of_week(rows, out_dir, wf_label)
    plot_failure_rate(rows, out_dir, wf_label)

    if args.jobs_csv:
        print(f"Loading {args.jobs_csv}...")
        jobs = load_jobs(args.jobs_csv)
        print(f"  {len(jobs)} jobs")
        print("Generating job-level plots...")
        plot_queue_by_variant(jobs, out_dir, wf_label)
        plot_build_by_variant(jobs, out_dir, wf_label)
        plot_queue_by_runner(jobs, out_dir, wf_label)
        plot_time_to_signal_by_platform(jobs, out_dir, wf_label)

    print(f"Done! {len(list(out_dir.glob('*.png')))} plots saved to {out_dir}")


if __name__ == "__main__":
    main()
