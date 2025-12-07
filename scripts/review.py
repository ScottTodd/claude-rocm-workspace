#!/usr/bin/env python3
"""
review.py - Centralized review workflow script

Supports both local (direct code) and remote (file watcher) VSCode modes.
Used by Claude Code slash commands for review workflow.

Commands:
    incremental [repo] [N]     Stage incremental review (default: 1 commit)
    milestone [repo] [branch]  Stage milestone review (default: main)
    comments [repo]            Collect RVW: comments as JSON
    stack [repo] [branch]      Show commit stack since branch
    open <files...>            Open files in VSCode (respects mode)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Workspace paths
WORKSPACE = Path(__file__).parent.parent
STATE_DIR = WORKSPACE / ".state"
VSCODE_MODE_FILE = STATE_DIR / "vscode-mode"
VSCODE_COMMANDS_FILE = STATE_DIR / "vscode-commands"
ACTIVE_TASK_FILE = WORKSPACE / ".claude" / "active-task"
DIRECTORY_MAP_FILE = WORKSPACE / "directory-map.md"


def get_vscode_mode() -> str:
    """Return 'local' or 'remote'."""
    if VSCODE_MODE_FILE.exists():
        mode = VSCODE_MODE_FILE.read_text().strip().lower()
        if mode in ("local", "remote"):
            return mode
    return "remote"  # default


def parse_directory_map() -> dict[str, Path]:
    """Parse directory-map.md to get repo aliases."""
    aliases = {}
    if not DIRECTORY_MAP_FILE.exists():
        return aliases

    content = DIRECTORY_MAP_FILE.read_text()
    # Find the Repository Aliases table
    in_table = False
    for line in content.split("\n"):
        if "| Alias |" in line:
            in_table = True
            continue
        if in_table:
            if line.startswith("|---"):
                continue
            if not line.startswith("|"):
                break
            # Parse: | alias | path | notes |
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                alias = parts[1]
                path = parts[2]
                if alias and path and not alias.startswith("---"):
                    aliases[alias] = Path(path)
    return aliases


def get_active_task_repos() -> list[str]:
    """Get repositories from active task's frontmatter."""
    if not ACTIVE_TASK_FILE.exists():
        return []

    task_name = ACTIVE_TASK_FILE.read_text().strip()
    task_file = WORKSPACE / "tasks" / "active" / f"{task_name}.md"
    if not task_file.exists():
        return []

    content = task_file.read_text()
    # Parse YAML frontmatter
    if not content.startswith("---"):
        return []

    end_idx = content.find("---", 3)
    if end_idx == -1:
        return []

    frontmatter = content[3:end_idx]
    repos = []
    in_repos = False
    for line in frontmatter.split("\n"):
        if line.strip().startswith("repositories:"):
            in_repos = True
            continue
        if in_repos:
            if line.strip().startswith("-"):
                # Extract repo name, removing comments
                repo = line.strip().lstrip("-").strip()
                repo = repo.split("#")[0].strip()
                if repo:
                    repos.append(repo)
            elif line.strip() and not line.startswith(" "):
                break
    return repos


def resolve_repo(alias: str | None) -> Path:
    """Resolve repo alias to path.

    Resolution order:
    1. If alias provided, look up in directory-map.md
    2. If alias is already a path, use it
    3. If no alias, use active task's first repo
    4. Fall back to current directory
    """
    aliases = parse_directory_map()

    if alias:
        # Check if it's a known alias
        if alias in aliases:
            return aliases[alias]
        # Check if it's already a path
        path = Path(alias)
        if path.exists():
            return path.resolve()
        raise ValueError(f"Unknown repo alias: {alias}")

    # Try active task
    task_repos = get_active_task_repos()
    if task_repos:
        first_repo = task_repos[0]
        if first_repo in aliases:
            return aliases[first_repo]

    # Fall back to current directory
    return Path.cwd()


def git(*args, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run git command and return result."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result


def open_in_vscode(files: list[str], new_window: bool = True) -> None:
    """Open files in VSCode, respecting mode."""
    if not files:
        return

    cmd_parts = ["code"]
    if new_window:
        cmd_parts.append("--new-window")
    cmd_parts.extend(files)
    cmd = " ".join(cmd_parts)

    if get_vscode_mode() == "local":
        subprocess.run(cmd_parts)
    else:
        STATE_DIR.mkdir(exist_ok=True)
        VSCODE_COMMANDS_FILE.write_text(cmd + "\n")


def cmd_incremental(repo: Path, n: int = 1) -> dict:
    """Stage incremental review (last N commits)."""
    base = f"HEAD~{n}"

    # Get changed files
    result = git("diff", "--name-only", base, cwd=repo)
    if result.returncode != 0:
        return {
            "status": "error",
            "error": result.stderr.strip(),
            "repo": str(repo),
        }

    files = [f for f in result.stdout.strip().split("\n") if f]

    if not files:
        return {
            "status": "nothing_to_review",
            "base": base,
            "repo": str(repo),
        }

    # Get current branch
    branch_result = git("branch", "--show-current", cwd=repo)
    current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

    # Open in VSCode
    full_paths = [str(repo / f) for f in files]
    open_in_vscode(full_paths)

    return {
        "status": "staged",
        "mode": get_vscode_mode(),
        "repo": str(repo),
        "branch": current_branch,
        "base": base,
        "head": "HEAD",
        "files": files,
        "file_count": len(files),
    }


def cmd_milestone(repo: Path, branch: str = "main") -> dict:
    """Stage milestone review (all changes since branch)."""
    # Get merge base
    merge_base_result = git("merge-base", "HEAD", branch, cwd=repo)
    if merge_base_result.returncode != 0:
        return {
            "status": "error",
            "error": f"Could not find merge base with {branch}",
            "repo": str(repo),
        }

    merge_base = merge_base_result.stdout.strip()

    # Get changed files
    result = git("diff", "--name-only", merge_base, cwd=repo)
    files = [f for f in result.stdout.strip().split("\n") if f]

    # Get commit count
    count_result = git("rev-list", "--count", f"{merge_base}..HEAD", cwd=repo)
    commit_count = int(count_result.stdout.strip()) if count_result.returncode == 0 else 0

    # Get current branch
    branch_result = git("branch", "--show-current", cwd=repo)
    current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

    if not files:
        return {
            "status": "nothing_to_review",
            "base": branch,
            "merge_base": merge_base[:8],
            "repo": str(repo),
        }

    # Open in VSCode
    full_paths = [str(repo / f) for f in files]
    open_in_vscode(full_paths)

    return {
        "status": "staged",
        "mode": get_vscode_mode(),
        "repo": str(repo),
        "branch": current_branch,
        "base": branch,
        "merge_base": merge_base[:8],
        "files": files,
        "file_count": len(files),
        "commit_count": commit_count,
    }


def cmd_comments(repo: Path) -> dict:
    """Find all RVW: and RVWY: comments in the repo."""
    # Use grep to find RVW/RVWY comments (RVWY = YOLO mode, fix without asking)
    result = subprocess.run(
        [
            "grep",
            "-rn",
            "-E",
            "RVWY?:",
            "--include=*.py",
            "--include=*.cpp",
            "--include=*.c",
            "--include=*.h",
            "--include=*.hpp",
            "--include=*.cmake",
            "--include=CMakeLists.txt",
            "--include=*.md",
            "--include=*.toml",
            "--include=*.yaml",
            "--include=*.yml",
            "--include=*.sh",
            "--include=*.js",
            "--include=*.ts",
            ".",
        ],
        capture_output=True,
        text=True,
        cwd=repo,
    )

    comments = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        # Parse: ./path/file.py:42:    // RVW: fix this
        match = re.match(r"^\.?/?([^:]+):(\d+):(.*)$", line)
        if match:
            filepath = match.group(1)
            lineno = int(match.group(2))
            content = match.group(3).strip()

            # Check for RVWY (yolo) vs RVW (discuss)
            rvwy_match = re.search(r"RVWY:\s*(.*)$", content)
            rvw_match = re.search(r"RVW:\s*(.*)$", content)

            if rvwy_match:
                comment_text = rvwy_match.group(1)
                yolo = True
            elif rvw_match:
                comment_text = rvw_match.group(1)
                yolo = False
            else:
                continue  # Not a real RVW comment

            comments.append({
                "file": str(repo / filepath),
                "relative_path": filepath,
                "line": lineno,
                "raw": content,
                "comment": comment_text,
                "yolo": yolo,
            })

    return {
        "repo": str(repo),
        "count": len(comments),
        "comments": comments,
    }


def cmd_stack(repo: Path, branch: str = "main") -> dict:
    """Show commit stack since branch."""
    # Get merge base
    merge_base_result = git("merge-base", "HEAD", branch, cwd=repo)
    if merge_base_result.returncode != 0:
        return {
            "status": "error",
            "error": f"Could not find merge base with {branch}",
            "repo": str(repo),
        }

    merge_base = merge_base_result.stdout.strip()

    # Get log
    log_result = git("log", "--oneline", f"{merge_base}..HEAD", cwd=repo)
    commits = [c for c in log_result.stdout.strip().split("\n") if c]

    # Get current branch
    branch_result = git("branch", "--show-current", cwd=repo)
    current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

    # Get stats
    stat_result = git("diff", "--stat", merge_base, cwd=repo)
    stats = stat_result.stdout.strip() if stat_result.returncode == 0 else ""

    return {
        "repo": str(repo),
        "branch": current_branch,
        "base": branch,
        "merge_base": merge_base[:8],
        "commits": commits,
        "count": len(commits),
        "stats": stats,
    }


def cmd_open(files: list[str]) -> dict:
    """Open specified files in VSCode."""
    # Resolve paths
    resolved = []
    for f in files:
        path = Path(f)
        if path.exists():
            resolved.append(str(path.resolve()))
        else:
            resolved.append(f)

    open_in_vscode(resolved)

    return {
        "status": "opened",
        "mode": get_vscode_mode(),
        "files": resolved,
        "file_count": len(resolved),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Review workflow helper for Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # incremental
    p_inc = subparsers.add_parser("incremental", help="Stage incremental review")
    p_inc.add_argument("repo", nargs="?", help="Repository alias or path")
    p_inc.add_argument("n", nargs="?", type=int, default=1, help="Number of commits back")

    # milestone
    p_mile = subparsers.add_parser("milestone", help="Stage milestone review")
    p_mile.add_argument("repo", nargs="?", help="Repository alias or path")
    p_mile.add_argument("branch", nargs="?", default="main", help="Base branch")

    # comments
    p_comments = subparsers.add_parser("comments", help="Find RVW: comments")
    p_comments.add_argument("repo", nargs="?", help="Repository alias or path")

    # stack
    p_stack = subparsers.add_parser("stack", help="Show commit stack")
    p_stack.add_argument("repo", nargs="?", help="Repository alias or path")
    p_stack.add_argument("branch", nargs="?", default="main", help="Base branch")

    # open
    p_open = subparsers.add_parser("open", help="Open files in VSCode")
    p_open.add_argument("files", nargs="+", help="Files to open")

    args = parser.parse_args()

    try:
        if args.command == "incremental":
            repo = resolve_repo(args.repo)
            result = cmd_incremental(repo, args.n)
        elif args.command == "milestone":
            repo = resolve_repo(args.repo)
            result = cmd_milestone(repo, args.branch)
        elif args.command == "comments":
            repo = resolve_repo(args.repo)
            result = cmd_comments(repo)
        elif args.command == "stack":
            repo = resolve_repo(args.repo)
            result = cmd_stack(repo, args.branch)
        elif args.command == "open":
            result = cmd_open(args.files)
        else:
            parser.print_help()
            sys.exit(1)

        print(json.dumps(result, indent=2))

    except ValueError as e:
        print(json.dumps({"status": "error", "error": str(e)}), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
