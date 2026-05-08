#!/usr/bin/env python
"""Compare ccache manifest keys for the same source files across two log files.

Extracts (source_file, manifest_key, compiler, result) tuples from ccache logs
and reports which source files have the same vs different manifest keys.

Usage:
    python scripts/compare_manifest_keys.py LOG1 LOG2
"""

import re
import sys
from collections import defaultdict
from pathlib import Path


def extract_sessions(log_file: str) -> list[dict]:
    """Extract ccache sessions with source, manifest key, compiler, and result."""
    sessions = []
    current = {}

    with open(log_file, "r", errors="replace") as f:
        for line in f:
            if "CCACHE" in line and "STARTED" in line:
                if current.get("source") and current.get("manifest_key"):
                    sessions.append(current)
                current = {}
                continue

            m = re.match(r"\[.*? (\d+)\s*\] Source file: (.+)", line)
            if m:
                current["source"] = m.group(2).strip()
                continue

            m = re.match(r"\[.*? (\d+)\s*\] Manifest key: (.+)", line)
            if m:
                current["manifest_key"] = m.group(2).strip()
                continue

            m = re.match(r"\[.*? (\d+)\s*\] Compiler: (.+)", line)
            if m and "Compiler type" not in line:
                current["compiler"] = m.group(2).strip()
                continue

            m = re.match(
                r"\[.*? (\d+)\s*\] Result: (direct_cache_hit|preprocessed_cache_hit|cache_miss)",
                line,
            )
            if m:
                current["result"] = m.group(2)

            if "CCACHE DONE" in line:
                if current.get("source") and current.get("manifest_key"):
                    sessions.append(current)
                current = {}

    if current.get("source") and current.get("manifest_key"):
        sessions.append(current)

    return sessions


def normalize_source(src: str) -> str:
    """Normalize source path for cross-run comparison."""
    # Strip platform-specific prefixes
    src = src.replace("\\", "/")
    for prefix in [
        "C:/home/runner/_work/TheRock/TheRock/",
        "B:/build/",
        "/__w/TheRock/TheRock/build/",
        "/__w/TheRock/TheRock/",
    ]:
        if src.startswith(prefix):
            src = src[len(prefix) :]
            break
    return src


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} LOG1 LOG2")
        sys.exit(1)

    log1, log2 = sys.argv[1], sys.argv[2]

    print(f"Parsing {log1}...", file=sys.stderr)
    sessions1 = extract_sessions(log1)
    print(f"  {len(sessions1)} sessions", file=sys.stderr)

    print(f"Parsing {log2}...", file=sys.stderr)
    sessions2 = extract_sessions(log2)
    print(f"  {len(sessions2)} sessions", file=sys.stderr)

    # Build lookup by normalized source
    by_source1 = {}
    for s in sessions1:
        key = normalize_source(s["source"])
        if "TryCompile" not in key and "CMakeScratch" not in key and "cmTC_" not in key:
            by_source1[key] = s

    by_source2 = {}
    for s in sessions2:
        key = normalize_source(s["source"])
        if "TryCompile" not in key and "CMakeScratch" not in key and "cmTC_" not in key:
            by_source2[key] = s

    # Compare
    common = set(by_source1.keys()) & set(by_source2.keys())
    same_key = 0
    diff_key = 0
    diff_examples = []

    for src in sorted(common):
        s1 = by_source1[src]
        s2 = by_source2[src]
        if s1["manifest_key"] == s2["manifest_key"]:
            same_key += 1
        else:
            diff_key += 1
            if len(diff_examples) < 5:
                diff_examples.append((src, s1, s2))

    print(f"\nCommon source files: {len(common)}")
    print(f"  Same manifest key: {same_key}")
    print(f"  Different manifest key: {diff_key}")
    print(f"  Only in log1: {len(by_source1) - len(common)}")
    print(f"  Only in log2: {len(by_source2) - len(common)}")

    if diff_examples:
        print(f"\nExamples of different manifest keys:")
        for src, s1, s2 in diff_examples:
            print(f"\n  Source: {src}")
            print(f"    Log1 key:      {s1['manifest_key']}")
            print(f"    Log2 key:      {s2['manifest_key']}")
            print(f"    Log1 compiler: {s1.get('compiler', '?')}")
            print(f"    Log2 compiler: {s2.get('compiler', '?')}")
            print(f"    Log1 result:   {s1.get('result', '?')}")
            print(f"    Log2 result:   {s2.get('result', '?')}")


if __name__ == "__main__":
    main()
