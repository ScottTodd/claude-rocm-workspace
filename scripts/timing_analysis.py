"""Compare multi-arch release vs legacy nightly release timings."""

from datetime import datetime


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def dur_min(start, end):
    return (parse_ts(end) - parse_ts(start)).total_seconds() / 60


def fmt(mins):
    h = int(mins) // 60
    m = int(mins) % 60
    return f"{h}h{m:02d}m" if h else f"{m}m"


# ============================================
# MULTI-ARCH RELEASE (rockrel #24859053365)
# ============================================
run_start = "2026-04-23T21:11:55Z"

ma_jobs = [
    ("setup", "2026-04-23T21:11:55Z", "2026-04-23T21:12:01Z"),
    # Linux generic stages
    ("L: foundation", "2026-04-23T21:12:45Z", "2026-04-23T21:17:23Z"),
    ("L: compiler-runtime", "2026-04-23T21:21:54Z", "2026-04-23T22:14:45Z"),
    ("L: dctools-core", "2026-04-23T22:15:30Z", "2026-04-23T22:33:29Z"),
    ("L: debug-tools", "2026-04-23T22:15:30Z", "2026-04-23T22:22:07Z"),
    ("L: media-libs", "2026-04-23T22:15:32Z", "2026-04-23T22:18:36Z"),
    ("L: iree-compiler", "2026-04-23T22:15:30Z", "2026-04-23T22:30:07Z"),
    ("L: profiler-apps", "2026-04-23T22:15:33Z", "2026-04-23T23:07:34Z"),
    ("L: comm-libs", "2026-04-23T22:15:33Z", "2026-04-23T23:53:09Z"),
    # Linux math-libs (per family)
    ("L: math-libs gfx900", "2026-04-23T22:15:36Z", "2026-04-23T23:24:15Z"),
    ("L: math-libs gfx906", "2026-04-23T22:15:36Z", "2026-04-23T23:23:03Z"),
    ("L: math-libs gfx908", "2026-04-23T22:15:34Z", "2026-04-24T00:03:27Z"),
    ("L: math-libs gfx90a", "2026-04-23T22:15:35Z", "2026-04-24T00:35:03Z"),
    ("L: math-libs gfx94X-dcgpu", "2026-04-23T22:15:35Z", "2026-04-24T01:45:09Z"),
    ("L: math-libs gfx950-dcgpu", "2026-04-23T22:15:34Z", "2026-04-24T01:24:26Z"),
    ("L: math-libs gfx101X-dgpu", "2026-04-23T22:15:36Z", "2026-04-23T23:40:59Z"),
    ("L: math-libs gfx103X-all", "2026-04-23T22:15:36Z", "2026-04-24T01:36:26Z"),
    ("L: math-libs gfx110X-all", "2026-04-23T22:15:34Z", "2026-04-24T00:53:11Z"),
    ("L: math-libs gfx1150", "2026-04-23T22:15:34Z", "2026-04-24T00:40:55Z"),
    ("L: math-libs gfx1151", "2026-04-23T22:15:35Z", "2026-04-24T00:56:11Z"),
    ("L: math-libs gfx1152", "2026-04-23T22:15:34Z", "2026-04-24T00:44:54Z"),
    ("L: math-libs gfx1153", "2026-04-23T22:15:36Z", "2026-04-24T00:42:15Z"),
    ("L: math-libs gfx120X-all", "2026-04-23T22:15:36Z", "2026-04-24T01:47:24Z"),
    # Linux fusilli + post-build
    ("L: fusilli-libs", "2026-04-24T01:47:35Z", "2026-04-24T01:53:25Z"),
    ("L: Build Tarballs", "2026-04-24T01:53:31Z", "2026-04-24T02:16:15Z"),
    ("L: Build Python", "2026-04-24T01:53:38Z", "2026-04-24T02:05:41Z"),
    ("L: Publish", "2026-04-24T02:16:38Z", "2026-04-24T02:16:44Z"),
    # Windows stages
    ("W: foundation", "2026-04-23T21:12:52Z", "2026-04-23T21:18:10Z"),
    ("W: compiler-runtime", "2026-04-23T21:22:00Z", "2026-04-23T22:07:31Z"),
    # Windows math-libs
    ("W: math-libs gfx900", "2026-04-23T22:12:41Z", "2026-04-23T23:29:55Z"),
    ("W: math-libs gfx906", "2026-04-23T22:17:03Z", "2026-04-23T23:21:29Z"),
    ("W: math-libs gfx908", "2026-04-23T22:20:11Z", "2026-04-24T00:01:32Z"),
    ("W: math-libs gfx90a", "2026-04-23T22:18:02Z", "2026-04-24T00:25:00Z"),
    ("W: math-libs gfx101X-dgpu", "2026-04-23T22:13:43Z", "2026-04-23T23:43:28Z"),
    ("W: math-libs gfx103X-all", "2026-04-23T22:14:08Z", "2026-04-24T01:29:10Z"),
    ("W: math-libs gfx110X-all", "2026-04-23T22:12:18Z", "2026-04-24T01:04:47Z"),
    ("W: math-libs gfx1150", "2026-04-23T22:15:20Z", "2026-04-24T00:02:00Z"),
    ("W: math-libs gfx1151", "2026-04-23T22:13:31Z", "2026-04-24T00:03:20Z"),
    ("W: math-libs gfx1152", "2026-04-23T22:22:43Z", "2026-04-23T23:58:35Z"),
    ("W: math-libs gfx1153", "2026-04-23T22:12:31Z", "2026-04-24T00:28:43Z"),
    ("W: math-libs gfx120X-all", "2026-04-23T22:17:55Z", "2026-04-24T03:06:46Z"),
    # Windows post-build
    ("W: Build Tarballs", "2026-04-24T03:07:03Z", "2026-04-24T03:24:45Z"),
    ("W: Build Python", "2026-04-24T03:08:31Z", "2026-04-24T03:21:37Z"),
    ("W: Publish", "2026-04-24T03:24:58Z", "2026-04-24T03:25:05Z"),
]

# Legacy Linux Apr 23
leg_linux = [
    ("gfx900", "2026-04-23T03:17:54Z", "2026-04-23T06:48:25Z"),
    ("gfx906", "2026-04-23T03:16:53Z", "2026-04-23T06:49:03Z"),
    ("gfx908", "2026-04-23T03:17:32Z", "2026-04-23T07:26:03Z"),
    ("gfx90a", "2026-04-23T03:17:05Z", "2026-04-23T07:45:40Z"),
    ("gfx94X-dcgpu", "2026-04-23T03:17:36Z", "2026-04-23T08:26:33Z"),
    ("gfx950-dcgpu", "2026-04-23T03:17:38Z", "2026-04-23T08:23:01Z"),
    ("gfx101X-dgpu", "2026-04-23T03:17:52Z", "2026-04-23T08:08:57Z"),
    ("gfx103X-all", "2026-04-23T03:17:38Z", "2026-04-23T08:31:31Z"),
    ("gfx110X-all", "2026-04-23T03:17:45Z", "2026-04-23T08:37:56Z"),
    ("gfx1150", "2026-04-23T03:17:50Z", "2026-04-23T07:38:32Z"),
    ("gfx1151", "2026-04-23T03:16:39Z", "2026-04-23T07:25:50Z"),
    ("gfx1152", "2026-04-23T03:17:17Z", "2026-04-23T07:31:52Z"),
    ("gfx1153", "2026-04-23T03:17:59Z", "2026-04-23T07:28:01Z"),
    ("gfx120X-all", "2026-04-23T03:17:38Z", "2026-04-23T08:31:45Z"),
]
leg_linux_start = "2026-04-23T03:14:21Z"

# Legacy Linux Apr 22
leg_linux2 = [
    ("gfx900", "2026-04-22T03:18:58Z", "2026-04-22T05:57:22Z"),
    ("gfx906", "2026-04-22T03:18:50Z", "2026-04-22T05:53:51Z"),
    ("gfx908", "2026-04-22T03:16:09Z", "2026-04-22T05:28:30Z"),
    ("gfx90a", "2026-04-22T03:17:56Z", "2026-04-22T05:33:25Z"),
    ("gfx94X-dcgpu", "2026-04-22T03:16:23Z", "2026-04-22T07:30:19Z"),
    ("gfx950-dcgpu", "2026-04-22T03:17:48Z", "2026-04-22T06:59:05Z"),
    ("gfx101X-dgpu", "2026-04-22T03:16:10Z", "2026-04-22T05:34:13Z"),
    ("gfx103X-all", "2026-04-22T03:18:16Z", "2026-04-22T07:35:30Z"),
    ("gfx110X-all", "2026-04-22T03:16:00Z", "2026-04-22T05:35:54Z"),
    ("gfx1150", "2026-04-22T03:18:13Z", "2026-04-22T06:04:46Z"),
    ("gfx1151", "2026-04-22T03:19:09Z", "2026-04-22T06:00:35Z"),
    ("gfx1152", "2026-04-22T03:18:13Z", "2026-04-22T05:27:19Z"),
    ("gfx120X-all", "2026-04-22T03:16:40Z", "2026-04-22T05:43:43Z"),
    ("gfx1153", "2026-04-22T03:18:23Z", "2026-04-22T05:57:57Z"),
]
leg_linux2_start = "2026-04-22T03:14:27Z"

# Legacy Windows Apr 23
leg_win = [
    ("gfx900", "2026-04-23T03:29:49Z", "2026-04-23T05:35:34Z"),
    ("gfx906", "2026-04-23T03:20:06Z", "2026-04-23T06:47:43Z"),
    ("gfx908", "2026-04-23T03:29:22Z", "2026-04-23T06:13:22Z"),
    ("gfx90a", "2026-04-23T03:29:22Z", "2026-04-23T06:34:04Z"),
    ("gfx101X-dgpu", "2026-04-23T03:28:49Z", "2026-04-23T05:57:32Z"),
    ("gfx103X-all", "2026-04-23T03:28:29Z", "2026-04-23T07:51:06Z"),
    ("gfx110X-all", "2026-04-23T03:19:33Z", "2026-04-23T07:21:30Z"),
    ("gfx1150", "2026-04-23T03:19:38Z", "2026-04-23T06:39:29Z"),
    ("gfx1151", "2026-04-23T03:20:32Z", "2026-04-23T06:11:29Z"),
    ("gfx1152", "2026-04-23T03:28:47Z", "2026-04-23T06:20:45Z"),
    ("gfx1153", "2026-04-23T03:29:36Z", "2026-04-23T06:17:57Z"),
    ("gfx120X-all", "2026-04-23T03:19:38Z", "2026-04-23T08:20:37Z"),
]
leg_win_start = "2026-04-23T03:14:52Z"

# Legacy Windows Apr 22
leg_win2 = [
    ("gfx900", "2026-04-22T03:20:11Z", "2026-04-22T06:40:09Z"),
    ("gfx906", "2026-04-22T03:20:26Z", "2026-04-22T05:28:53Z"),
    ("gfx908", "2026-04-22T03:19:48Z", "2026-04-22T07:37:15Z"),
    ("gfx90a", "2026-04-22T03:19:45Z", "2026-04-22T08:17:19Z"),
    ("gfx101X-dgpu", "2026-04-22T03:29:00Z", "2026-04-22T05:53:41Z"),
    ("gfx103X-all", "2026-04-22T03:20:18Z", "2026-04-22T08:32:12Z"),
    ("gfx110X-all", "2026-04-22T03:19:43Z", "2026-04-22T08:50:35Z"),
    ("gfx1150", "2026-04-22T03:28:29Z", "2026-04-22T06:15:33Z"),
    ("gfx1151", "2026-04-22T03:19:35Z", "2026-04-22T07:30:53Z"),
    ("gfx1152", "2026-04-22T03:29:24Z", "2026-04-22T06:15:31Z"),
    ("gfx1153", "2026-04-22T03:29:13Z", "2026-04-22T06:06:42Z"),
    ("gfx120X-all", "2026-04-22T03:19:40Z", "2026-04-22T09:58:16Z"),
]
leg_win2_start = "2026-04-22T03:14:46Z"


def print_section(title):
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def print_jobs(jobs, run_start_ts, prefix=""):
    for name, start, end in sorted(jobs, key=lambda x: x[2]):
        d = dur_min(start, end)
        wall = dur_min(run_start_ts, end)
        print(f"  {prefix}{name:40s}  dur={fmt(d):>6s}  wall={fmt(wall):>6s}")


# ============ MULTI-ARCH ============
print_section("MULTI-ARCH RELEASE (rockrel run 24859053365)")

print("\n--- Linux jobs (sorted by completion) ---")
linux_jobs = [(n, s, e) for n, s, e in ma_jobs if n.startswith("L:")]
print_jobs(linux_jobs, run_start)
linux_last = max(parse_ts(e) for n, s, e in ma_jobs if n.startswith("L:"))
linux_wall = (linux_last - parse_ts(run_start)).total_seconds() / 60
print(f"\n  Linux total wall time: {fmt(linux_wall)}")

print("\n--- Windows jobs (sorted by completion) ---")
win_jobs = [(n, s, e) for n, s, e in ma_jobs if n.startswith("W:")]
print_jobs(win_jobs, run_start)
win_last = max(parse_ts(e) for n, s, e in ma_jobs if n.startswith("W:"))
win_wall = (win_last - parse_ts(run_start)).total_seconds() / 60
print(f"\n  Windows total wall time: {fmt(win_wall)}")
print(f"  Overall wall time: {fmt(max(linux_wall, win_wall))}")


# ============ LEGACY LINUX ============
print_section("LEGACY LINUX NIGHTLY - Apr 23 (run 24814714541)")
for name, start, end in sorted(leg_linux, key=lambda x: dur_min(x[1], x[2])):
    d = dur_min(start, end)
    wall = dur_min(leg_linux_start, end)
    print(f"  {name:20s}  dur={fmt(d):>6s}  wall={fmt(wall):>6s}")
last = max(parse_ts(e) for _, _, e in leg_linux)
total = (last - parse_ts(leg_linux_start)).total_seconds() / 60
print(f"  Total wall time: {fmt(total)}")

print_section("LEGACY LINUX NIGHTLY - Apr 22 (run 24758253765)")
for name, start, end in sorted(leg_linux2, key=lambda x: dur_min(x[1], x[2])):
    d = dur_min(start, end)
    wall = dur_min(leg_linux2_start, end)
    print(f"  {name:20s}  dur={fmt(d):>6s}  wall={fmt(wall):>6s}")
last = max(parse_ts(e) for _, _, e in leg_linux2)
total = (last - parse_ts(leg_linux2_start)).total_seconds() / 60
print(f"  Total wall time: {fmt(total)}")


# ============ LEGACY WINDOWS ============
print_section("LEGACY WINDOWS NIGHTLY - Apr 23 (run 24814728779)")
for name, start, end in sorted(leg_win, key=lambda x: dur_min(x[1], x[2])):
    d = dur_min(start, end)
    wall = dur_min(leg_win_start, end)
    q = dur_min(leg_win_start, start)
    print(f"  {name:20s}  dur={fmt(d):>6s}  wall={fmt(wall):>6s}  queue={fmt(q):>5s}")
last = max(parse_ts(e) for _, _, e in leg_win)
total = (last - parse_ts(leg_win_start)).total_seconds() / 60
print(f"  Total wall time: {fmt(total)}")

print_section("LEGACY WINDOWS NIGHTLY - Apr 22 (run 24758262812)")
for name, start, end in sorted(leg_win2, key=lambda x: dur_min(x[1], x[2])):
    d = dur_min(start, end)
    wall = dur_min(leg_win2_start, end)
    q = dur_min(leg_win2_start, start)
    print(f"  {name:20s}  dur={fmt(d):>6s}  wall={fmt(wall):>6s}  queue={fmt(q):>5s}")
last = max(parse_ts(e) for _, _, e in leg_win2)
total = (last - parse_ts(leg_win2_start)).total_seconds() / 60
print(f"  Total wall time: {fmt(total)}")


# ============ HEAD-TO-HEAD ============
print_section("HEAD-TO-HEAD: per-family build duration (multi-arch vs legacy Apr 23)")

# Multi-arch math-libs durations
ma_linux_math = {}
for n, s, e in ma_jobs:
    if n.startswith("L: math-libs"):
        family = n.replace("L: math-libs ", "")
        ma_linux_math[family] = dur_min(s, e)

ma_win_math = {}
for n, s, e in ma_jobs:
    if n.startswith("W: math-libs"):
        family = n.replace("W: math-libs ", "")
        ma_win_math[family] = dur_min(s, e)

# Legacy durations
leg_linux_dur = {n: dur_min(s, e) for n, s, e in leg_linux}
leg_win_dur = {n: dur_min(s, e) for n, s, e in leg_win}

print("\nLinux: multi-arch math-libs vs legacy full-build (includes generic stages)")
hdr = f"  {'Family':20s}  {'MA math':>8s}  {'Legacy':>8s}  {'Savings':>8s}"
print(hdr)
print(f"  {'-' * 20}  {'-' * 8}  {'-' * 8}  {'-' * 8}")
for fam in sorted(ma_linux_math.keys()):
    ma_d = ma_linux_math[fam]
    leg_d = leg_linux_dur.get(fam, 0)
    savings = leg_d - ma_d if leg_d else 0
    print(
        f"  {fam:20s}  {fmt(ma_d):>8s}  {fmt(leg_d):>8s}"
        f"  {'+' + fmt(savings) if savings > 0 else '-' + fmt(-savings) if leg_d else 'N/A':>8s}"
    )
print("  Note: legacy includes generic stages (~63m in multi-arch) per family")

print("\nWindows: multi-arch math-libs vs legacy full-build")
print(hdr)
print(f"  {'-' * 20}  {'-' * 8}  {'-' * 8}  {'-' * 8}")
for fam in sorted(ma_win_math.keys()):
    ma_d = ma_win_math[fam]
    leg_d = leg_win_dur.get(fam, 0)
    savings = leg_d - ma_d if leg_d else 0
    print(
        f"  {fam:20s}  {fmt(ma_d):>8s}  {fmt(leg_d):>8s}"
        f"  {'+' + fmt(savings) if savings > 0 else '-' + fmt(-savings) if leg_d else 'N/A':>8s}"
    )


# ============ TOPOLOGY ANALYSIS ============
print_section("BUILD TOPOLOGY / WORKFLOW OVERHEAD")

print("\nMulti-arch Linux critical path:")
print(f"  1. setup:                    {fmt(dur_min(run_start, '2026-04-23T21:12:01Z'))}")
print(f"  2. foundation:               {fmt(dur_min('2026-04-23T21:12:45Z', '2026-04-23T21:17:23Z'))}")
print(f"  3. compiler-runtime:         {fmt(dur_min('2026-04-23T21:21:54Z', '2026-04-23T22:14:45Z'))}")
print(f"     (gap setup->foundation):  {fmt(dur_min('2026-04-23T21:12:01Z', '2026-04-23T21:12:45Z'))}")
print(f"     (gap found->comp-rt):     {fmt(dur_min('2026-04-23T21:17:23Z', '2026-04-23T21:21:54Z'))}")
print(f"  4. math-libs (slowest):      {fmt(dur_min('2026-04-23T22:15:36Z', '2026-04-24T01:47:24Z'))} (gfx120X-all)")
print(f"     (gap comp-rt->math):      {fmt(dur_min('2026-04-23T22:14:45Z', '2026-04-23T22:15:36Z'))}")
print(f"  5. fusilli-libs:             {fmt(dur_min('2026-04-24T01:47:35Z', '2026-04-24T01:53:25Z'))}")
print(f"  6. Build Tarballs:           {fmt(dur_min('2026-04-24T01:53:31Z', '2026-04-24T02:16:15Z'))}")
print(f"  Total critical path:         {fmt(dur_min(run_start, '2026-04-24T02:16:44Z'))}")

print("\nMulti-arch Windows critical path:")
print(f"  1. foundation:               {fmt(dur_min('2026-04-23T21:12:52Z', '2026-04-23T21:18:10Z'))}")
print(f"  2. compiler-runtime:         {fmt(dur_min('2026-04-23T21:22:00Z', '2026-04-23T22:07:31Z'))}")
print(f"  3. math-libs (slowest):      {fmt(dur_min('2026-04-23T22:17:55Z', '2026-04-24T03:06:46Z'))} (gfx120X-all)")
print(f"  4. Build Tarballs:           {fmt(dur_min('2026-04-24T03:07:03Z', '2026-04-24T03:24:45Z'))}")
print(f"  Total critical path:         {fmt(dur_min(run_start, '2026-04-24T03:25:05Z'))}")

print("\nLegacy: all families start immediately (no serial generic stages)")
print(f"  Linux Apr 23 slowest family: gfx110X-all = {fmt(dur_min('2026-04-23T03:17:45Z', '2026-04-23T08:37:56Z'))}")
print(f"  Linux Apr 22 slowest family: gfx103X-all = {fmt(dur_min('2026-04-22T03:18:16Z', '2026-04-22T07:35:30Z'))}")
print(f"  Win   Apr 23 slowest family: gfx120X-all = {fmt(dur_min('2026-04-23T03:19:38Z', '2026-04-23T08:20:37Z'))}")
print(f"  Win   Apr 22 slowest family: gfx120X-all = {fmt(dur_min('2026-04-22T03:19:40Z', '2026-04-22T09:58:16Z'))}")


# ============ RUNNER QUEUE ANALYSIS ============
print_section("RUNNER QUEUE ANALYSIS")

print("\nMulti-arch: gaps between job dependency met and job start")
print("  (All math-libs jobs started within ~1min of compiler-runtime completing)")
print("  (Fusilli started <1min after slowest math-libs)")
print("  => No significant runner queue delays observed")

print("\nLegacy Linux Apr 23: all jobs queued <3min from run start")
print("Legacy Windows Apr 23: queue delays up to 15min for some families")
leg_win_queues = []
for n, s, e in leg_win:
    q = dur_min(leg_win_start, s)
    leg_win_queues.append((n, q))
for n, q in sorted(leg_win_queues, key=lambda x: x[1], reverse=True):
    print(f"  {n:20s}  queue={fmt(q):>5s}")


# ============ RUNNER-HOURS ============
print_section("RUNNER-HOURS (compute cost comparison)")

ma_linux_total = sum(dur_min(s, e) for n, s, e in ma_jobs if n.startswith("L:"))
ma_win_total = sum(dur_min(s, e) for n, s, e in ma_jobs if n.startswith("W:"))
leg_linux_total = sum(dur_min(s, e) for _, s, e in leg_linux)
leg_win_total = sum(dur_min(s, e) for _, s, e in leg_win)

print(f"\nMulti-arch Linux runner-minutes:  {ma_linux_total:.0f}m ({ma_linux_total / 60:.1f}h)")
print(f"Multi-arch Windows runner-minutes: {ma_win_total:.0f}m ({ma_win_total / 60:.1f}h)")
print(f"Multi-arch combined:               {(ma_linux_total + ma_win_total):.0f}m ({(ma_linux_total + ma_win_total) / 60:.1f}h)")
print(f"\nLegacy Linux runner-minutes:       {leg_linux_total:.0f}m ({leg_linux_total / 60:.1f}h)")
print(f"Legacy Windows runner-minutes:     {leg_win_total:.0f}m ({leg_win_total / 60:.1f}h)")
print(f"Legacy combined (L+W):             {(leg_linux_total + leg_win_total):.0f}m ({(leg_linux_total + leg_win_total) / 60:.1f}h)")

savings_pct = (1 - (ma_linux_total + ma_win_total) / (leg_linux_total + leg_win_total)) * 100
print(f"\nRunner-hour savings: {savings_pct:+.1f}%")


# ============ SUMMARY ============
print_section("SUMMARY TABLE")

print("""
Pipeline             | Linux wall | Windows wall | Combined wall | Runner-hours
---------------------|------------|--------------|---------------|-------------""")
print(
    f"Multi-arch release   | {fmt(linux_wall):>10s} | {fmt(win_wall):>12s} | {fmt(max(linux_wall, win_wall)):>13s} | {(ma_linux_total + ma_win_total) / 60:>10.1f}h"
)

for label, ldata, lstart, wdata, wstart in [
    ("Legacy Apr 23", leg_linux, leg_linux_start, leg_win, leg_win_start),
    ("Legacy Apr 22", leg_linux2, leg_linux2_start, leg_win2, leg_win2_start),
]:
    ll = max(parse_ts(e) for _, _, e in ldata)
    lw = (ll - parse_ts(lstart)).total_seconds() / 60
    wl = max(parse_ts(e) for _, _, e in wdata)
    ww = (wl - parse_ts(wstart)).total_seconds() / 60
    lt = sum(dur_min(s, e) for _, s, e in ldata)
    wt = sum(dur_min(s, e) for _, s, e in wdata)
    # Legacy L and W run as separate workflows, so combined = max(L, W)
    # But they run concurrently since they're separate workflow runs
    print(
        f"{label:20s} | {fmt(lw):>10s} | {fmt(ww):>12s} | {fmt(max(lw, ww)):>13s} | {(lt + wt) / 60:>10.1f}h"
    )

print("""
Notes:
- Multi-arch runs Linux and Windows in the SAME workflow run (serialized by
  shared setup, but builds run in parallel). Wall = max(Linux, Windows).
- Legacy runs Linux and Windows as SEPARATE workflows (fully parallel).
  Combined wall = max(Linux wall, Windows wall).
- Runner-hours = sum of all job durations (compute cost, ignoring queue waits).
- Multi-arch math-libs only builds the per-family portion; generic stages are
  shared. Legacy builds everything per family (generic + math + comm + fusilli).
- Multi-arch has additional post-build jobs (tarballs, python packages, publish)
  not present in legacy build workflow.
""")
