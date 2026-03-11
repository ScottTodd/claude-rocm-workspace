"""Reorder artifact TOML component sections to match the extends chain.

Canonical order: lib -> run -> dbg -> dev -> doc -> test

Files are organized into subproject blocks delimited by comment lines
(e.g. "# rocm_smi_lib"). Within each block, sections are sorted by
canonical component order while preserving basedir sub-grouping.
"""

import pathlib
import re
import sys

CANONICAL_ORDER = ["lib", "run", "dbg", "dev", "doc", "test"]
RANK = {c: i for i, c in enumerate(CANONICAL_ORDER)}

SECTION_RE = re.compile(r"^\[components\.(\w+)\.")
COMMENT_RE = re.compile(r"^#\s")


def parse_sections(text: str) -> list[dict]:
    """Parse a TOML file into sections.

    Each section is a dict with:
      - 'kind': 'component', 'comment', or 'preamble'
      - 'type': component type (e.g. 'lib', 'run') or None
      - 'basedir': the basedir string, or None
      - 'lines': list of lines (including the header/comment line)
    """
    sections = []
    current = {"kind": "preamble", "type": None, "basedir": None, "lines": []}

    for line in text.splitlines(keepends=True):
        m = SECTION_RE.match(line)
        if m:
            if current["lines"]:
                sections.append(current)
            comp_type = m.group(1)
            quote_start = line.index('"') + 1
            quote_end = line.rindex('"')
            basedir = line[quote_start:quote_end]
            current = {
                "kind": "component",
                "type": comp_type,
                "basedir": basedir,
                "lines": [line],
            }
        elif COMMENT_RE.match(line):
            if current["lines"]:
                sections.append(current)
            current = {
                "kind": "comment",
                "type": None,
                "basedir": None,
                "lines": [line],
            }
        else:
            current["lines"].append(line)

    if current["lines"]:
        sections.append(current)
    return sections


def group_into_blocks(sections: list[dict]) -> list[list[dict]]:
    """Group sections into subproject blocks.

    A block starts with a comment section or the file preamble. All
    component sections following a comment belong to that block.
    """
    blocks = []
    current_block = []

    for section in sections:
        if section["kind"] in ("comment", "preamble"):
            if current_block:
                blocks.append(current_block)
            current_block = [section]
        else:
            current_block.append(section)

    if current_block:
        blocks.append(current_block)

    return blocks


def _strip_trailing_blanks(lines: list[str]) -> tuple[list[str], list[str]]:
    """Split lines into (content, trailing_blanks)."""
    trailing = []
    content = list(lines)
    while content and content[-1].strip() == "":
        trailing.insert(0, content.pop())
    return content, trailing


def sort_block(block: list[dict]) -> list[dict]:
    """Sort component sections within a block by canonical order.

    The leading comment/preamble stays first. Component sections are sorted
    by (basedir_first_appearance, canonical_rank). Trailing blank lines from
    the original last section are moved to the new last section.
    """
    header = []
    components = []
    for section in block:
        if section["kind"] == "component":
            components.append(section)
        else:
            header.append(section)

    if len(components) <= 1:
        return block

    # Strip trailing blank lines from all component sections, remember
    # the trailing blanks from the last one (inter-block spacing).
    last_trailing = []
    for i, comp in enumerate(components):
        content, trailing = _strip_trailing_blanks(comp["lines"])
        comp["lines"] = content
        if i == len(components) - 1:
            last_trailing = trailing

    # Determine first-appearance order of basedirs within this block
    basedir_order = {}
    for s in components:
        if s["basedir"] not in basedir_order:
            basedir_order[s["basedir"]] = len(basedir_order)

    # Sort by (basedir_first_appearance, canonical_rank)
    components.sort(
        key=lambda s: (basedir_order[s["basedir"]], RANK.get(s["type"], 999))
    )

    # Restore trailing blanks on the new last section
    components[-1]["lines"].extend(last_trailing)

    return header + components


def reorder_file(filepath: pathlib.Path, dry_run: bool = False) -> bool:
    """Reorder component sections in a single TOML file.

    Returns True if the file was changed.
    """
    text = filepath.read_text()
    sections = parse_sections(text)
    blocks = group_into_blocks(sections)
    sorted_blocks = [sort_block(b) for b in blocks]

    # Reconstruct
    new_lines = []
    for block in sorted_blocks:
        for section in block:
            new_lines.extend(section["lines"])

    new_text = "".join(new_lines)

    if new_text == text:
        return False

    if not dry_run:
        filepath.write_text(new_text)
    return True


def main():
    dry_run = "--dry-run" in sys.argv

    toml_dir = pathlib.Path("D:/projects/TheRock")
    files = sorted(toml_dir.rglob("artifact*.toml"))
    files = [f for f in files if "external" not in str(f) and "_deps" not in str(f)]

    changed = []
    unchanged = []
    for f in files:
        if reorder_file(f, dry_run=dry_run):
            changed.append(f)
            rel = f.relative_to(toml_dir)
            print(f"{'[dry-run] ' if dry_run else ''}changed: {rel}")
        else:
            unchanged.append(f)

    print(f"\n{'Would change' if dry_run else 'Changed'}: {len(changed)}")
    print(f"Unchanged: {len(unchanged)}")


if __name__ == "__main__":
    main()
