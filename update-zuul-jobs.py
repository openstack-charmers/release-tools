#!/usr/bin/python3
"""Update .zuul.yaml jobs for a charm repository.

Usage:
    update-zuul-jobs.py [options] CHARM_DIR

The script reads <charm-directory>/.zuul.yaml, <charm-directory>/osci.yaml and
<charm-directory>/metadata.yaml and ensures that .zuul.yaml contains a check
job entry for ``charmbuild`` with the correct vars block.
"""

import argparse
import fnmatch
import sys
from pathlib import Path

from ruamel.yaml import YAML


def _make_yaml() -> YAML:
    """Return a ruamel.yaml instance configured for round-trip use."""
    yml = YAML()
    yml.preserve_quotes = True
    yml.width = 4096  # avoid unwanted line wrapping
    return yml


def load_yaml_file(path: Path):
    """Load a YAML file and return its parsed content."""
    yml = _make_yaml()
    with path.open() as fh:
        return yml.load(fh)


def get_charm_name(charm_dir: Path) -> str:
    """Return the charm name from metadata.yaml."""
    metadata_path = charm_dir / "metadata.yaml"
    if not metadata_path.exists():
        sys.exit(f"ERROR: {metadata_path} not found")
    data = load_yaml_file(metadata_path)
    name = data.get("name")
    if not name:
        sys.exit(f"ERROR: 'name' key not found in {metadata_path}")
    return name


def get_charmcraft_channel(charm_dir: Path) -> str:
    """Return the charmcraft_channel value from osci.yaml."""
    osci_path = charm_dir / "osci.yaml"
    if not osci_path.exists():
        sys.exit(f"ERROR: {osci_path} not found")
    data = load_yaml_file(osci_path)
    # osci.yaml is a list of project dicts
    if isinstance(data, list):
        for item in data:
            project = item.get("project", {})
            channel = project.get("vars", {}).get("charmcraft_channel")
            if channel:
                return channel
    sys.exit(f"ERROR: 'charmcraft_channel' not found in {osci_path}")


def process_zuul_yaml(charm_dir: Path, charm_name: str, charmcraft_channel: str):
    """Ensure .zuul.yaml has the charmbuild check job.

    Modifies the file in-place if the job is missing.  Returns True if a
    change was made, False otherwise.
    """
    zuul_path = charm_dir / ".zuul.yaml"
    if not zuul_path.exists():
        sys.exit(f"ERROR: {zuul_path} not found")

    yml = _make_yaml()
    with zuul_path.open() as fh:
        data = yml.load(fh)

    if not isinstance(data, list):
        sys.exit(f"ERROR: Unexpected structure in {zuul_path}")

    changed = False
    for item in data:
        if "project" not in item:
            continue
        project = item["project"]

        # Check if charmbuild is already listed under check.jobs
        check_section = project.get("check", {})
        jobs = check_section.get("jobs", [])
        job_names = []
        for j in jobs:
            if isinstance(j, str):
                job_names.append(j)
            elif isinstance(j, dict):
                job_names.extend(j.keys())

        if "charmbuild" in job_names:
            print(f"charmbuild job already present in {zuul_path}, nothing to do.")
            return False

        # Add check.jobs entry
        if "check" not in project:
            project["check"] = {}
        if "jobs" not in project["check"]:
            project["check"]["jobs"] = []
        project["check"]["jobs"].append("charmbuild")

        # Add / update vars block
        if "vars" not in project:
            project["vars"] = {}
        project["vars"]["charmbuild_charmcraft_channel"] = charmcraft_channel
        project["vars"]["charm_build_name"] = charm_name

        changed = True
        break  # only process the first project stanza

    if not changed:
        print(f"No project stanza found in {zuul_path}, nothing to do.")
        return False

    # Dump back preserving order and style
    with zuul_path.open("w") as fh:
        yml.dump(data, fh)

    print(f"Updated {zuul_path}: added charmbuild job for charm '{charm_name}'.")
    return True


def replace_template_in_zuul_yaml(charm_dir: Path, pattern: str, replacement: str):
    """Replace a template entry in .zuul.yaml whose name matches *pattern*.

    Uses shell-style glob matching (fnmatch).  Exits with an error if more
    than one template matches.  Prints a message and exits successfully if no
    match is found.
    """
    zuul_path = charm_dir / ".zuul.yaml"
    if not zuul_path.exists():
        sys.exit(f"ERROR: {zuul_path} not found")

    yml = _make_yaml()
    with zuul_path.open() as fh:
        data = yml.load(fh)

    if not isinstance(data, list):
        sys.exit(f"ERROR: Unexpected structure in {zuul_path}")

    changed = False
    for item in data:
        if "project" not in item:
            continue
        project = item["project"]

        templates = project.get("templates")
        if not templates:
            continue

        matches = [t for t in templates if fnmatch.fnmatch(t, pattern)]

        if not matches:
            print(
                f"No templates matching '{pattern}' found in {zuul_path}, nothing to do."
            )
            return False

        if len(matches) > 1:
            sys.exit(
                f"ERROR: pattern '{pattern}' matched more than one template in "
                f"{zuul_path}: {', '.join(matches)}"
            )

        old_name = matches[0]
        idx = list(templates).index(old_name)
        templates[idx] = replacement
        changed = True
        print(
            f"Updated {zuul_path}: replaced template '{old_name}' with '{replacement}'."
        )
        break  # only process the first project stanza

    if not changed and not any("project" in item for item in data):
        print(f"No project stanza found in {zuul_path}, nothing to do.")

    if changed:
        with zuul_path.open("w") as fh:
            yml.dump(data, fh)

    return changed


def main():
    parser = argparse.ArgumentParser(
        description="Add charmbuild check job to .zuul.yaml if missing."
    )
    parser.add_argument(
        "charm_dir",
        metavar="CHARM_DIR",
        help="Path to the charm git repository directory.",
    )
    parser.add_argument(
        "--add-charmbuild",
        action="store_true",
        default=False,
        help="Add the charmbuild check job to .zuul.yaml if it is missing.",
    )
    parser.add_argument(
        "--replace",
        metavar="PATTERN",
        default=None,
        help=(
            "Glob pattern to match a template name in .zuul.yaml "
            "(e.g. 'openstack-python3-charm-jobs-*'). Must be used with --with."
        ),
    )
    parser.add_argument(
        "--with",
        metavar="REPLACEMENT",
        dest="replace_with",
        default=None,
        help="Replacement template name to use when --replace finds a match.",
    )
    args = parser.parse_args()

    charm_dir = Path(args.charm_dir).resolve()
    if not charm_dir.is_dir():
        sys.exit(f"ERROR: {charm_dir} is not a directory")

    if args.replace is not None or args.replace_with is not None:
        if args.replace is None:
            sys.exit("ERROR: --with requires --replace.")
        if args.replace_with is None:
            sys.exit("ERROR: --replace requires --with.")
        replace_template_in_zuul_yaml(charm_dir, args.replace, args.replace_with)

    if args.add_charmbuild:
        charm_name = get_charm_name(charm_dir)
        charmcraft_channel = get_charmcraft_channel(charm_dir)
        process_zuul_yaml(charm_dir, charm_name, charmcraft_channel)

    if not args.add_charmbuild and args.replace is None:
        print(
            "Nothing to do. Use --add-charmbuild to add the charmbuild job, "
            "or --replace PATTERN --with REPLACEMENT to replace a template."
        )


if __name__ == "__main__":
    main()
