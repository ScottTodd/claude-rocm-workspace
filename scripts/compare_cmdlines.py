#!/usr/bin/env python
"""Compare compiler command lines for the same source file across two ccache logs.

Usage:
    python scripts/compare_cmdlines.py LOG1 LOG2 SOURCE_PATTERN
"""

import re
import sys


def find_cmdline(log_file: str, source_pattern: str) -> dict | None:
    """Find a ccache session matching source_pattern and return its details."""
    current = {}

    with open(log_file, "r", errors="replace") as f:
        for line in f:
            if "CCACHE" in line and "STARTED" in line:
                current = {}
                continue

            m = re.match(r"\[.*? (\d+)\s*\] Source file: (.+)", line)
            if m:
                current["source"] = m.group(2).strip()

            m = re.match(r"\[.*? (\d+)\s*\] Command line: (.+)", line)
            if m:
                current["cmdline"] = m.group(2).strip()

            m = re.match(r"\[.*? (\d+)\s*\] Compiler: (.+)", line)
            if m and "Compiler type" not in line:
                current["compiler"] = m.group(2).strip()

            m = re.match(r"\[.*? (\d+)\s*\] Working directory: (.+)", line)
            if m:
                current["workdir"] = m.group(2).strip()

            m = re.match(r"\[.*? (\d+)\s*\] Hostname: (.+)", line)
            if m:
                current["hostname"] = m.group(2).strip()

            if "CCACHE DONE" in line:
                src = current.get("source", "")
                if (
                    source_pattern in src
                    and "clang++" in current.get("compiler", "")
                    and "clr" in current.get("compiler", "")
                    and "TryCompile" not in src
                    and "CMakeScratch" not in src
                ):
                    return current
                current = {}

    return None


def main():
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} LOG1 LOG2 SOURCE_PATTERN")
        sys.exit(1)

    log1, log2, pattern = sys.argv[1], sys.argv[2], sys.argv[3]

    print(f"Searching for '{pattern}' in both logs...\n")

    s1 = find_cmdline(log1, pattern)
    s2 = find_cmdline(log2, pattern)

    if not s1:
        print(f"Not found in {log1}")
        return
    if not s2:
        print(f"Not found in {log2}")
        return

    print(f"Log1: {s1.get('hostname', '?')}")
    print(f"Log2: {s2.get('hostname', '?')}")
    print(f"Log1 workdir: {s1.get('workdir', '?')}")
    print(f"Log2 workdir: {s2.get('workdir', '?')}")
    print(f"Log1 compiler: {s1.get('compiler', '?')}")
    print(f"Log2 compiler: {s2.get('compiler', '?')}")

    cmd1 = s1.get("cmdline", "")
    cmd2 = s2.get("cmdline", "")

    args1 = cmd1.split()
    args2 = cmd2.split()

    print(f"\nLog1 args: {len(args1)}")
    print(f"Log2 args: {len(args2)}")

    # Find differences
    if args1 == args2:
        print("\nCommand lines are IDENTICAL")
        return

    print("\nDifferences:")
    # Compare sorted args to find additions/removals
    set1 = set(args1)
    set2 = set(args2)

    only1 = set1 - set2
    only2 = set2 - set1

    if only1:
        print(f"  Only in log1 ({len(only1)}):")
        for a in sorted(only1):
            print(f"    {a}")

    if only2:
        print(f"  Only in log2 ({len(only2)}):")
        for a in sorted(only2):
            print(f"    {a}")

    # Also show positional differences
    print(f"\nPositional diff (first 10):")
    shown = 0
    for i in range(max(len(args1), len(args2))):
        a1 = args1[i] if i < len(args1) else "<missing>"
        a2 = args2[i] if i < len(args2) else "<missing>"
        if a1 != a2:
            print(f"  [{i}] {a1}")
            print(f"  [{i}] {a2}")
            shown += 1
            if shown >= 10:
                break


if __name__ == "__main__":
    main()
