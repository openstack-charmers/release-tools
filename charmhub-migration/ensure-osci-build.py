#!/usr/bin/env python3

# Ensure that osci.yaml has the following vars stanza at the end.
# Filename is passed as first param

# - project:
#     vars:
#       needs_charm_build: true
#       charm_build_name: <charm-name>
#       build_type: charmcraft

import logging
import os
from pathlib import Path
import re
import sys
from typing import List, Optional, Dict
import textwrap


logger = logging.getLogger(__name__)


PROJECT_MATCH = re.compile(r'^- project:\s+(?:|#.*)$')
VARS_MATCH = re.compile(r'^\s+vars:\s+(?:|#.*)$')


def vars_lines(charm_name: str) -> List[str]:
    return [f"    {t}\n" for t in textwrap.dedent(
        """\
            vars:
              needs_charm_build: true
              charm_build_name: {charm_name}
              build_type: charmcraft
        """.format(charm_name=charm_name)).splitlines()]


def update_osci(lines: List[str], charm_name: str) -> List[str]:
    """Update a yaml file as text to add the vars block to the project."""
    out: List[str] = []
    done: bool = False
    in_project: bool = False
    in_vars: bool = False
    add_block: List[str] = vars_lines(charm_name)
    for line in lines:
        print(f"processing in_project: {in_project}: {line.strip()}")
        if done:
            out.append(line)
            continue
        if not in_project:
            project_match = PROJECT_MATCH.match(line)
            if project_match:
                print("matched!")
                in_project = True
                out.append(line)
                continue
        if in_project:
            if len(line.strip()) == 0 or not line.startswith(' '):
                print("ended block")
                # we've reached the end of the block and not hit var, so add
                # the block.
                out.extend(add_block)
                done = True
                in_project = False
                in_vars = False
            vars_match = VARS_MATCH.match(line)
            if vars_match:
                print("matched vars!")
                in_vars = True
            if in_vars:
                # skip lines that are in the vars; we'll replace them at the end of
                # the block
                continue
        out.append(line)
    if done is False and in_project:
        out.extend(add_block)
    return out


# update the charmcraft.yaml file (passed on the line as arg1) and ensure that
# it has the bases added.
def main() -> None:
    assert len(sys.argv) > 1
    filename = sys.argv[1]
    charm_name = sys.argv[2]
    try:
        with open(filename) as f:
            file_lines = f.readlines()
    except Exception:
        print("Couldn't update osci.yaml -- ignoring")
        return
    new_lines = update_osci(file_lines, charm_name)
    # for line in new_lines:
        # print(line, end="")
    new_file_name = "osci.yaml.new"
    with open(new_file_name, "wt") as f:
        f.writelines(new_lines)
    # now overwrite the file
    os.rename(new_file_name, filename)


if __name__ == '__main__':
    logging.basicConfig()
    main()
