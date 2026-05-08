#!/usr/bin/env python
"""Check results for source files that have matching manifest keys across two runs.

Usage:
    python scripts/check_same_key_results.py LOG1 LOG2
"""

import re
import sys
from collections import Counter


def extract_sessions(log_file: str) -> dict[str, dict]:
    """Extract ccache sessions keyed by normalized source path."""
    sessions = {}
    current = {}

    with open(log_file, "r", errors="replace") as f:
        for line in f:
            if "CCACHE" in line and "STARTED" in line:
                current = {}
                continue

            m = re.match(r"\[.*? (\d+)\s*\] Source file: (.+)", line)
            if m:
                current["source"] = m.group(2).strip()

            m = re.match(r"\[.*? (\d+)\s*\] Manifest key: (.+)", line)
            if m:
                current["manifest_key"] = m.group(2).strip()

            m = re.match(r"\[.*? (\d+)\s*\] Compiler: (.+)", line)
            if m and "Compiler type" not in line:
                current["compiler"] = m.group(2).strip()

            m = re.match(
                r"\[.*? (\d+)\s*\] Result: (direct_cache_hit|preprocessed_cache_hit|cache_miss)",
                line,
            )
            if m:
                current["result"] = m.group(2)

            m = re.match(r"\[.*? (\d+)\s*\] Considering result entry", line)
            if m:
                current["entries"] = current.get("entries", 0) + 1

            if "CCACHE DONE" in line:
                src = current.get("source", "")
                if src and current.get("manifest_key"):
                    norm = normalize(src)
                    if "TryCompile" not in norm and "CMakeScratch" not in norm and "cmTC_" not in norm:
                        sessions[norm] = current
                current = {}

    return sessions


def normalize(src: str) -> str:
    src = src.replace("\\", "/")
    for prefix in [
        "C:/home/runner/_work/TheRock/TheRock/",
        "B:/build/",
    ]:
        if src.startswith(prefix):
            return src[len(prefix):]
    return src


def main():
    log1, log2 = sys.argv[1], sys.argv[2]

    print(f"Parsing logs...", file=sys.stderr)
    s1 = extract_sessions(log1)
    s2 = extract_sessions(log2)

    common = set(s1.keys()) & set(s2.keys())
    same_key = [(k, s1[k], s2[k]) for k in common if s1[k]["manifest_key"] == s2[k]["manifest_key"]]
    diff_key = [(k, s1[k], s2[k]) for k in common if s1[k]["manifest_key"] != s2[k]["manifest_key"]]

    print(f"Common source files: {len(common)}")
    print(f"Same manifest key: {len(same_key)}")
    print(f"Different manifest key: {len(diff_key)}")

    # For same-key files, what are the results?
    results = Counter()
    for src, a, b in same_key:
        r1 = a.get("result", "?")
        r2 = b.get("result", "?")
        results[(r1, r2)] += 1

    print(f"\nResults for SAME-KEY files (log1_result, log2_result):")
    for (r1, r2), count in results.most_common():
        print(f"  {r1:25s} / {r2:25s} : {count}")

    # For same-key files that miss: how many entries were considered?
    both_miss = [(src, a, b) for src, a, b in same_key
                 if a.get("result") == "cache_miss" and b.get("result") == "cache_miss"]
    print(f"\nBoth-miss same-key files: {len(both_miss)}")
    if both_miss:
        entry_counts = Counter()
        for src, a, b in both_miss:
            e1 = a.get("entries", 0)
            e2 = b.get("entries", 0)
            if e1 == 0 and e2 == 0:
                entry_counts["both 0"] += 1
            elif e1 > 0 and e2 > 0:
                entry_counts["both >0"] += 1
            else:
                entry_counts["mixed"] += 1
        for k, v in entry_counts.most_common():
            print(f"  {k}: {v}")

    # For different-key files: are the compilers the same?
    diff_compiler = sum(1 for _, a, b in diff_key if a.get("compiler") != b.get("compiler"))
    print(f"\nDifferent-key files with different compiler: {diff_compiler}")
    print(f"Different-key files with same compiler: {len(diff_key) - diff_compiler}")


if __name__ == "__main__":
    main()
