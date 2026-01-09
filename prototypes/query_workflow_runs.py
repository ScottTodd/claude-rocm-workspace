#!/usr/bin/env python3
"""
Prototype: Query GitHub API for workflow runs and map commits to run_ids.

This script validates the bisect tooling design by querying real workflow runs
for the rocm-systems commits from PR #2812.

Uses `gh` CLI for authenticated API access.

Usage:
    python prototypes/query_workflow_runs.py
"""

import json
import subprocess
import sys
from typing import Any

# Commits from PR #2812 (rocm-systems: 2789ea4...050e88e)
COMMITS = [
    "3568e0df02c7f8d203de29b9e175ac87f7da337f",
    "0f0504d79dae96269631a21af3636bfe00044894",
    "88f4bb19883f04524c32564792bb411a7050b440",
    "7871f53563e7747daaca113d3d2a08b3fcaaf087",
    "11d9472e5fae5b5efc3703eca4a4db3b4a75d6dd",
    "39d84328932de5b9fbc26f958c0467d479072831",
    "1d5a6e9bfefb937ae9cfc15bcae9cc8786b691d5",
    "9e4d1c31c7da2c7cd56651b4bb46b842e64e8e9f",
    "7fcea905f34a5c74be45a6b88c96eda59437cee6",
    "e005f8487b84fe1aba4ee91acd4e126028c72892",
    "637b0d71f0ea7da409d7126b5828cc1982f02d92",
    "6c98c49362f3dbb76a6f8814c7dc90a889d14175",
    "c6b7448227aee6ca449241f1b8bde6a9d02b3d2f",
    "32fde0f73d79d699c2b9de1573652cca40898af6",
    "50644f5aef0358eb2808483159d754c2f0b18611",
    "cb372748f8112ca5951e18e8f43a231d640053c8",
    "81eed26ec6fcbb0ed41865c168c471d6042f1749",
    "1ef6a86ee3ad85b97070c27b631ed0aceec31611",
    "050e88ee710f0d8580e2df31425c9fd03e8f1a77",
]

REPO = "ROCm/rocm-systems"
WORKFLOW_FILE = "therock-ci.yml"


def gh_api(endpoint: str) -> dict[str, Any]:
    """Call GitHub API using gh CLI."""
    cmd = ["gh", "api", endpoint, "--paginate"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error calling gh API: {e}", file=sys.stderr)
        print(f"Stdout: {e.stdout}", file=sys.stderr)
        print(f"Stderr: {e.stderr}", file=sys.stderr)
        raise
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}", file=sys.stderr)
        raise


def query_workflow_runs(repo: str, workflow_file: str) -> list[dict[str, Any]]:
    """Query workflow runs for a specific workflow file."""
    endpoint = f"/repos/{repo}/actions/workflows/{workflow_file}/runs"
    print(f"Querying: {endpoint}", file=sys.stderr)

    data = gh_api(endpoint)

    # Handle paginated results - gh --paginate returns array of results
    if isinstance(data, list):
        all_runs = []
        for page_data in data:
            all_runs.extend(page_data.get("workflow_runs", []))
        return all_runs
    else:
        return data.get("workflow_runs", [])


def build_commit_mapping(
    commits: list[str],
    runs: list[dict[str, Any]],
) -> dict[str, dict[str, Any] | None]:
    """Build mapping from commits to workflow runs."""
    mapping = {commit: None for commit in commits}

    for run in runs:
        head_sha = run.get("head_sha", "")
        if head_sha in mapping:
            mapping[head_sha] = {
                "run_id": run["id"],
                "run_number": run["run_number"],
                "status": run["status"],
                "conclusion": run["conclusion"],
                "created_at": run["created_at"],
                "html_url": run["html_url"],
            }

    return mapping


def print_mapping_results(mapping: dict[str, dict[str, Any] | None]) -> None:
    """Print the commit→run_id mapping results."""
    print("\n" + "=" * 80)
    print("COMMIT → RUN_ID MAPPING")
    print("=" * 80)

    found_count = 0
    missing_count = 0

    for idx, (commit, run_info) in enumerate(mapping.items(), 1):
        commit_short = commit[:8]

        if run_info:
            found_count += 1
            print(f"\n{idx:2d}. {commit_short} ✓ HAS RUN")
            print(f"    Run ID:     {run_info['run_id']}")
            print(f"    Run #:      {run_info['run_number']}")
            print(f"    Status:     {run_info['status']}")
            print(f"    Conclusion: {run_info['conclusion']}")
            print(f"    Created:    {run_info['created_at']}")
            print(f"    URL:        {run_info['html_url']}")
        else:
            missing_count += 1
            print(f"\n{idx:2d}. {commit_short} ✗ NO RUN FOUND")

    print("\n" + "=" * 80)
    print(f"SUMMARY: {found_count} commits with runs, {missing_count} commits without runs")
    print("=" * 80)


def main() -> None:
    """Main entry point."""
    print(f"Querying workflow runs for {REPO}/{WORKFLOW_FILE}...\n", file=sys.stderr)

    # Query workflow runs using gh CLI
    runs = query_workflow_runs(REPO, WORKFLOW_FILE)
    print(f"\nTotal runs fetched: {len(runs)}\n", file=sys.stderr)

    # Build commit→run mapping
    mapping = build_commit_mapping(COMMITS, runs)

    # Print results
    print_mapping_results(mapping)


if __name__ == "__main__":
    main()
