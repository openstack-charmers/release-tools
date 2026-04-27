#!/usr/bin/env python3
"""Tools for updating tox.ini files in OpenStack charms."""

import argparse
import re
import sys
from pathlib import Path


def _version_to_section(version: str) -> str:
    """Convert a Python version string like '3.10' to a tox section name like 'py310'."""
    return "py" + version.replace(".", "")


def add_py3(args) -> int:
    """Add a new [testenv:pyXYZ] section to a tox.ini by cloning a template section.

    Reads the tox.ini at *args.tox_ini*, finds the section for *args.template*,
    clones it with all occurrences of the template version replaced by
    *args.version*, and inserts the new section immediately after the template.

    Returns 0 on success, non-zero on error.
    """
    tox_ini: Path = args.tox_ini
    version: str = args.version
    template: str = args.template

    if not tox_ini.exists():
        print(f"error: {tox_ini} does not exist", file=sys.stderr)
        return 1

    template_section = _version_to_section(template)
    new_section = _version_to_section(version)

    content = tox_ini.read_text()

    # Find the template section using a regex that captures the header and body
    # up to (but not including) the next section header or end of file.
    pattern = re.compile(
        r"(\[testenv:" + re.escape(template_section) + r"\][^\[]*)",
        re.DOTALL,
    )
    match = pattern.search(content)
    if match is None:
        print(
            f"error: section [testenv:{template_section}] not found in {tox_ini}",
            file=sys.stderr,
        )
        return 1

    # Check whether the target section already exists.
    if re.search(r"\[testenv:" + re.escape(new_section) + r"\]", content):
        print(
            f"warning: section [testenv:{new_section}] already exists in {tox_ini}, skipping",
            file=sys.stderr,
        )
        return 0

    template_block = match.group(1)

    # Replace every occurrence of the template version string and section name
    # within the cloned block.  We replace the longer/more-specific strings
    # first to avoid partial substitutions.
    new_block = template_block.replace(
        f"[testenv:{template_section}]",
        f"[testenv:{new_section}]",
    )
    # Replace dotted form: "3.10" → "3.12"  (matches basepython, constraints…)
    new_block = new_block.replace(template, version)
    # Replace compact form: "py310" → "py312"  (matches filenames like
    # test-requirements-py310.txt that don't contain the dotted version)
    new_block = new_block.replace(template_section, new_section)

    # Ensure the new block ends with exactly one newline before insertion.
    template_end = match.end()

    # Insert the new block right after the template block.
    new_content = content[:template_end] + new_block + content[template_end:]

    tox_ini.write_text(new_content)
    print(f"Added [testenv:{new_section}] to {tox_ini}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Tools for updating tox.ini files in OpenStack charms."
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # add-py3 subcommand
    add_py3_parser = subparsers.add_parser(
        "add-py3",
        help="Add a new pyXYZ testenv section to a tox.ini file.",
    )
    add_py3_parser.add_argument(
        "--version",
        required=True,
        help="Python version to add (e.g. '3.12').",
    )
    add_py3_parser.add_argument(
        "--template",
        required=True,
        help="Existing Python version to use as template (e.g. '3.10').",
    )
    add_py3_parser.add_argument(
        "--tox-ini",
        type=Path,
        default=Path("tox.ini"),
        help="Path to the tox.ini file to modify (default: tox.ini).",
    )
    add_py3_parser.set_defaults(func=add_py3)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
