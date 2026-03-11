# Copyright Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT

"""
Query the subproject dependency manifest emitted by CMake at configure time.

Reads therock_subproject_deps.json (written by
therock_subproject_write_dependency_manifest() in therock_subproject.cmake)
and answers dependency queries: which subprojects need testing when a given
set of subprojects change.

Usage:
    # Which packages need testing if rocBLAS changed?
    python query_subproject_deps.py --build-dir /path/to/build --changed rocBLAS

    # Multiple changes
    python query_subproject_deps.py --build-dir /path/to/build --changed rocBLAS hip-clr

    # List all subprojects
    python query_subproject_deps.py --build-dir /path/to/build --list

    # Show full reverse-dependency graph
    python query_subproject_deps.py --build-dir /path/to/build --reverse-deps rocBLAS
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Set


MANIFEST_FILENAME = "therock_subproject_deps.json"


def load_manifest(build_dir: Path) -> dict:
    """Load the dependency manifest from a build directory."""
    manifest_path = build_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Dependency manifest not found: {manifest_path}\n"
            f"Run CMake configure first to generate it."
        )
    return json.loads(manifest_path.read_text())


def build_reverse_deps(subprojects: dict) -> Dict[str, Set[str]]:
    """
    Build a reverse dependency map from the manifest.

    Returns a dict mapping each subproject to the set of subprojects that
    directly depend on it (via runtime_deps).
    """
    reverse: Dict[str, Set[str]] = {name: set() for name in subprojects}
    for name, info in subprojects.items():
        for dep in info["runtime_deps"]:
            if dep in reverse:
                reverse[dep].add(name)
    return reverse


def get_packages_to_test(
    subprojects: dict, changed: list[str]
) -> set[str]:
    """
    Given a list of changed subprojects, return the set that needs testing.

    Returns the changed subprojects plus their direct reverse dependents
    (subprojects whose runtime_deps include a changed subproject).
    """
    reverse = build_reverse_deps(subprojects)
    result = set()
    for name in changed:
        if name not in subprojects:
            raise ValueError(
                f"Unknown subproject: {name!r}. "
                f"Use --list to see available subprojects."
            )
        result.add(name)
        result.update(reverse.get(name, set()))
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Query the subproject dependency manifest"
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        required=True,
        help="Path to the CMake build directory",
    )
    parser.add_argument(
        "--changed",
        nargs="+",
        metavar="SUBPROJECT",
        help="Subproject(s) that changed — outputs packages to test",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all subprojects",
    )
    parser.add_argument(
        "--reverse-deps",
        metavar="SUBPROJECT",
        help="Show direct reverse dependencies of a subproject",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.build_dir)
    subprojects = manifest["subprojects"]

    if args.list:
        for name in sorted(subprojects):
            deps = subprojects[name]["runtime_deps"]
            if deps:
                print(f"{name}  (runtime_deps: {', '.join(deps)})")
            else:
                print(name)
        return

    if args.reverse_deps:
        name = args.reverse_deps
        if name not in subprojects:
            raise ValueError(f"Unknown subproject: {name!r}")
        reverse = build_reverse_deps(subprojects)
        dependents = sorted(reverse.get(name, set()))
        if dependents:
            print(json.dumps(dependents))
        else:
            print(f"No subprojects depend on {name}")
        return

    if args.changed:
        to_test = get_packages_to_test(subprojects, args.changed)
        print(json.dumps(sorted(to_test)))
        return

    parser.error("One of --changed, --list, or --reverse-deps is required")


if __name__ == "__main__":
    main()
