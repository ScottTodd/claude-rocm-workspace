#!/usr/bin/env python
# Copyright Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT

"""Compare compiler binaries from two CI runs to find non-deterministic bytes.

Downloads amd-llvm_run_generic.tar.zst from two CI runs, extracts just the
clang++.exe (and clang.exe), and reports byte-level differences.

Usage:
    python scripts/compare_compiler_binaries.py \
        --run-id1 25465494022 --run-id2 25496971293

    # Or compare a CI binary against a local build
    python scripts/compare_compiler_binaries.py \
        --run-id1 25465494022 \
        --local-file2 /d/projects/TheRock/build/compiler/amd-llvm/stage/lib/llvm/bin/clang++.exe
"""

import argparse
import io
import struct
import sys
import tarfile
import urllib.request
from pathlib import Path

S3_BASE = "https://therock-ci-artifacts.s3.amazonaws.com"
SCRATCH = Path("D:/scratch/claude/ccache-investigation/compiler-compare")

# Files to extract from the archive (relative to archive root)
TARGET_FILES = [
    "compiler/amd-llvm/stage/lib/llvm/bin/clang++.exe",
    "compiler/amd-llvm/stage/lib/llvm/bin/clang.exe",
    "compiler/amd-llvm/stage/lib/llvm/bin/lld-link.exe",
]


def extract_from_archive(run_id: str, target_files: list[str]) -> dict[str, Path]:
    """Stream-extract specific files from amd-llvm archive without downloading fully."""
    import zstandard

    out_dir = SCRATCH / f"run_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Check if already extracted
    results = {}
    all_present = True
    for tf in target_files:
        out_path = out_dir / Path(tf).name
        if out_path.exists():
            results[tf] = out_path
        else:
            all_present = False

    if all_present and results:
        print(f"  Using cached extracts for run {run_id}", file=sys.stderr)
        return results

    url = f"{S3_BASE}/{run_id}-windows/amd-llvm_run_generic.tar.zst"
    print(f"  Streaming from: {url}", file=sys.stderr)
    print(f"  Looking for: {target_files}", file=sys.stderr)

    target_basenames = {Path(tf).name for tf in target_files}
    results = {}

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        dctx = zstandard.ZstdDecompressor()
        reader = dctx.stream_reader(resp)
        with tarfile.open(fileobj=reader, mode="r|") as tf:
            for member in tf:
                basename = Path(member.name).name
                if basename in target_basenames and member.isfile():
                    print(f"  Extracting: {member.name} ({member.size} bytes)", file=sys.stderr)
                    f = tf.extractfile(member)
                    if f:
                        out_path = out_dir / basename
                        out_path.write_bytes(f.read())
                        # Find which target_file matches
                        for target in target_files:
                            if Path(target).name == basename and target not in results:
                                results[target] = out_path
                                break
                    if len(results) == len(target_files):
                        break

    return results


def parse_pe_header(data: bytes) -> dict:
    """Parse key PE/COFF header fields."""
    info = {}
    # DOS header: e_lfanew at offset 0x3C
    if len(data) < 0x40 or data[:2] != b"MZ":
        return {"error": "Not a PE file"}

    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 24 > len(data):
        return {"error": "PE header truncated"}

    # PE signature
    sig = data[pe_offset:pe_offset + 4]
    if sig != b"PE\x00\x00":
        return {"error": f"Bad PE signature: {sig}"}

    # COFF header (20 bytes after signature)
    coff = pe_offset + 4
    info["machine"] = struct.unpack_from("<H", data, coff)[0]
    info["num_sections"] = struct.unpack_from("<H", data, coff + 2)[0]
    info["timestamp"] = struct.unpack_from("<I", data, coff + 4)[0]
    info["timestamp_offset"] = coff + 4
    info["symbol_table_ptr"] = struct.unpack_from("<I", data, coff + 8)[0]
    info["num_symbols"] = struct.unpack_from("<I", data, coff + 12)[0]
    info["opt_header_size"] = struct.unpack_from("<H", data, coff + 16)[0]
    info["characteristics"] = struct.unpack_from("<H", data, coff + 18)[0]

    # Optional header
    opt = coff + 20
    if info["opt_header_size"] >= 2:
        magic = struct.unpack_from("<H", data, opt)[0]
        info["pe_type"] = "PE32+" if magic == 0x20B else "PE32"

    return info


def compare_binaries(path1: Path, path2: Path, label1: str, label2: str):
    """Compare two binary files and report differences."""
    data1 = path1.read_bytes()
    data2 = path2.read_bytes()

    print(f"\n{'='*70}")
    print(f"  Comparing: {path1.name}")
    print(f"  {label1}: {len(data1)} bytes")
    print(f"  {label2}: {len(data2)} bytes")
    print(f"{'='*70}")

    if data1 == data2:
        print("  IDENTICAL - binaries are byte-for-byte equal")
        return

    # Parse PE headers
    pe1 = parse_pe_header(data1)
    pe2 = parse_pe_header(data2)
    print(f"\n  PE header ({label1}): timestamp=0x{pe1.get('timestamp', 0):08X}, "
          f"sections={pe1.get('num_sections', '?')}")
    print(f"  PE header ({label2}): timestamp=0x{pe2.get('timestamp', 0):08X}, "
          f"sections={pe2.get('num_sections', '?')}")
    if pe1.get("timestamp") != pe2.get("timestamp"):
        print(f"  ** COFF TIMESTAMP DIFFERS! /Brepro may not be working **")
    else:
        print(f"  COFF timestamps match (0x{pe1.get('timestamp', 0):08X})")

    # Size difference
    if len(data1) != len(data2):
        print(f"\n  Size difference: {len(data1) - len(data2):+d} bytes")
        print("  (Cannot do byte-by-byte diff on different-sized files)")
        # Still try to find common differences
        min_len = min(len(data1), len(data2))
    else:
        min_len = len(data1)

    # Find differing byte ranges
    diff_ranges = []
    i = 0
    while i < min_len:
        if data1[i] != data2[i]:
            start = i
            while i < min_len and data1[i] != data2[i]:
                i += 1
            diff_ranges.append((start, i))
        else:
            i += 1

    print(f"\n  Differing regions in first {min_len} bytes: {len(diff_ranges)}")
    for start, end in diff_ranges[:30]:
        length = end - start
        ctx1 = data1[start:min(end, start + 16)]
        ctx2 = data2[start:min(end, start + 16)]
        print(f"    offset 0x{start:08X} - 0x{end:08X} ({length} bytes)")
        print(f"      {label1}: {ctx1.hex(' ')}")
        print(f"      {label2}: {ctx2.hex(' ')}")
        # Check for embedded strings near the diff
        for offset in range(max(0, start - 64), min(min_len, end + 64)):
            if data1[offset:offset + 8] in (b"__DATE__", b"__TIME__"):
                print(f"      ** Near __DATE__/__TIME__ at 0x{offset:08X} **")
                break

    if len(diff_ranges) > 30:
        print(f"    ... and {len(diff_ranges) - 30} more regions")

    # Summary of total differing bytes
    total_diff = sum(end - start for start, end in diff_ranges)
    print(f"\n  Total differing bytes: {total_diff} / {min_len} ({100*total_diff/min_len:.4f}%)")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id1", required=True, help="First workflow run ID")
    p.add_argument("--run-id2", help="Second workflow run ID")
    p.add_argument("--local-file2", type=Path,
                   help="Local binary to compare against run-id1")
    p.add_argument("--file", default="clang++.exe",
                   choices=["clang++.exe", "clang.exe", "lld-link.exe"],
                   help="Which binary to compare (default: clang++.exe)")
    args = p.parse_args()

    if not args.run_id2 and not args.local_file2:
        p.error("Provide either --run-id2 or --local-file2")

    target = [t for t in TARGET_FILES if args.file in t][0]

    print(f"Extracting from run {args.run_id1}...", file=sys.stderr)
    files1 = extract_from_archive(args.run_id1, [target])
    if target not in files1:
        print(f"ERROR: {target} not found in run {args.run_id1}", file=sys.stderr)
        sys.exit(1)

    if args.run_id2:
        print(f"Extracting from run {args.run_id2}...", file=sys.stderr)
        files2 = extract_from_archive(args.run_id2, [target])
        if target not in files2:
            print(f"ERROR: {target} not found in run {args.run_id2}", file=sys.stderr)
            sys.exit(1)
        compare_binaries(
            files1[target], files2[target],
            f"run {args.run_id1}", f"run {args.run_id2}",
        )
    else:
        compare_binaries(
            files1[target], args.local_file2,
            f"run {args.run_id1}", f"local",
        )


if __name__ == "__main__":
    main()
