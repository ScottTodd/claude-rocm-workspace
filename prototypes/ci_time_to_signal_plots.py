"""Generate plots from CI timing data collected by ci_time_to_signal.py.

Usage:
    python prototypes/ci_time_to_signal_plots.py /d/scratch/claude/ci_timing_7d.csv

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


def plot_time_to_signal(rows: list[dict], out_dir: Path):
    """Plot 1: Time to signal and wall time over time."""
    non_skipped = [r for r in rows if not r["skipped"]]

    dates = [r["created_dt"] for r in non_skipped]
    wall_h = [to_hours(r["wall_seconds"]) for r in non_skipped]
    signal_h = [to_hours(r["time_to_signal_seconds"]) for r in non_skipped]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.scatter(dates, wall_h, alpha=0.4, s=20, label="Wall time", color="tab:blue")
    ax.scatter(dates, signal_h, alpha=0.7, s=30, label="Time to signal", color="tab:red")

    ax.set_ylabel("Hours")
    ax.set_title("CI Time to Signal vs Wall Time (main branch, push events)")
    ax.legend()
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    setup_date_axis(ax)

    fig.tight_layout()
    fig.savefig(out_dir / "time_to_signal.png", dpi=150)
    plt.close(fig)
    print(f"  Saved time_to_signal.png")


def plot_queue_times(rows: list[dict], out_dir: Path):
    """Plot 2: Build vs test queue times."""
    non_skipped = [r for r in rows if not r["skipped"]]

    dates = [r["created_dt"] for r in non_skipped]
    build_q = [to_hours(r["build_max_queue_seconds"]) for r in non_skipped]
    test_q = [to_hours(r["test_max_queue_seconds"]) for r in non_skipped]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.scatter(dates, build_q, alpha=0.6, s=25, label="Build runner queue (max)", color="tab:green")
    ax.scatter(dates, test_q, alpha=0.6, s=25, label="Test runner queue (max)", color="tab:orange")

    ax.set_ylabel("Hours")
    ax.set_title("Runner Queue Times (max per run)")
    ax.legend()
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    setup_date_axis(ax)

    fig.tight_layout()
    fig.savefig(out_dir / "queue_times.png", dpi=150)
    plt.close(fig)
    print(f"  Saved queue_times.png")


def plot_build_durations(rows: list[dict], out_dir: Path):
    """Plot 3: Max build duration over time."""
    non_skipped = [r for r in rows if not r["skipped"] and r["build_max_duration_seconds"] > 0]

    dates = [r["created_dt"] for r in non_skipped]
    build_h = [to_hours(r["build_max_duration_seconds"]) for r in non_skipped]
    pytorch_h = [to_hours(r["pytorch_max_duration_seconds"]) for r in non_skipped]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.scatter(dates, build_h, alpha=0.6, s=25, label="Build artifacts (max)", color="tab:blue")
    ax.scatter(dates, pytorch_h, alpha=0.6, s=25, label="PyTorch build (max)", color="tab:purple")

    ax.set_ylabel("Hours")
    ax.set_title("Build Job Durations (max per run)")
    ax.legend()
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    setup_date_axis(ax)

    fig.tight_layout()
    fig.savefig(out_dir / "build_durations.png", dpi=150)
    plt.close(fig)
    print(f"  Saved build_durations.png")


def plot_hour_of_day(rows: list[dict], out_dir: Path):
    """Plot 4: Queue time by hour of day (UTC) — shows daily patterns."""
    non_skipped = [r for r in rows if not r["skipped"]]

    hours = [r["created_dt"].hour for r in non_skipped]
    test_q = [to_hours(r["test_max_queue_seconds"]) for r in non_skipped]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(hours, test_q, alpha=0.5, s=30, color="tab:orange")

    ax.set_xlabel("Hour of Day (UTC)")
    ax.set_ylabel("Test Runner Max Queue (hours)")
    ax.set_title("Test Runner Queue Time by Hour of Day")
    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(range(0, 24, 2))
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_dir / "queue_by_hour.png", dpi=150)
    plt.close(fig)
    print(f"  Saved queue_by_hour.png")


def plot_day_of_week(rows: list[dict], out_dir: Path):
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
    ax1.set_title("Test Runner Queue by Day")
    ax1.set_xticks(range(7))
    ax1.set_xticklabels(day_names)
    ax1.set_ylim(bottom=0)
    ax1.grid(True, alpha=0.3)

    ax2.scatter(days, signal_h, alpha=0.5, s=30, color="tab:red")
    ax2.set_xlabel("Day of Week")
    ax2.set_ylabel("Hours")
    ax2.set_title("Time to Signal by Day")
    ax2.set_xticks(range(7))
    ax2.set_xticklabels(day_names)
    ax2.set_ylim(bottom=0)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_dir / "by_day_of_week.png", dpi=150)
    plt.close(fig)
    print(f"  Saved by_day_of_week.png")


def plot_failure_rate(rows: list[dict], out_dir: Path):
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
    ax.set_title("CI Failure Rate Over Time")
    ax.legend()
    ax.set_ylim(0, 105)
    ax.grid(True, alpha=0.3)
    setup_date_axis(ax)

    fig.tight_layout()
    fig.savefig(out_dir / "failure_rate.png", dpi=150)
    plt.close(fig)
    print(f"  Saved failure_rate.png")


def plot_signal_breakdown(rows: list[dict], out_dir: Path):
    """Plot 7: Stacked view — build time + queue time = time to signal."""
    non_skipped = sorted(
        [r for r in rows if not r["skipped"]],
        key=lambda r: r["created_dt"]
    )

    dates = [r["created_dt"] for r in non_skipped]
    build_h = [to_hours(r["build_max_duration_seconds"]) for r in non_skipped]
    build_q_h = [to_hours(r["build_max_queue_seconds"]) for r in non_skipped]
    test_q_h = [to_hours(r["test_max_queue_seconds"]) for r in non_skipped]
    signal_h = [to_hours(r["time_to_signal_seconds"]) for r in non_skipped]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.scatter(dates, build_q_h, alpha=0.5, s=20, label="Build queue", color="tab:green")
    ax.scatter(dates, build_h, alpha=0.5, s=20, label="Build duration", color="tab:blue")
    ax.scatter(dates, test_q_h, alpha=0.5, s=20, label="Test queue", color="tab:orange")
    ax.scatter(dates, signal_h, alpha=0.7, s=30, label="Time to signal", color="tab:red", marker="x")

    ax.set_ylabel("Hours")
    ax.set_title("Time to Signal Breakdown")
    ax.legend()
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    setup_date_axis(ax)

    fig.tight_layout()
    fig.savefig(out_dir / "signal_breakdown.png", dpi=150)
    plt.close(fig)
    print(f"  Saved signal_breakdown.png")


def main():
    parser = argparse.ArgumentParser(description="Plot CI timing data")
    parser.add_argument("csv_file", type=Path, help="Input CSV from ci_time_to_signal.py")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output directory for PNGs (default: same as CSV)")
    args = parser.parse_args()

    out_dir = args.output_dir or args.csv_file.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading {args.csv_file}...")
    rows = load_data(args.csv_file)
    print(f"  {len(rows)} total runs, {sum(1 for r in rows if not r['skipped'])} non-skipped")

    print("Generating plots...")
    plot_time_to_signal(rows, out_dir)
    plot_queue_times(rows, out_dir)
    plot_build_durations(rows, out_dir)
    plot_hour_of_day(rows, out_dir)
    plot_day_of_week(rows, out_dir)
    plot_failure_rate(rows, out_dir)
    plot_signal_breakdown(rows, out_dir)

    print(f"Done! {len(list(out_dir.glob('*.png')))} plots saved to {out_dir}")


if __name__ == "__main__":
    main()
