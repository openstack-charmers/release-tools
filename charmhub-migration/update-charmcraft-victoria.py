#!/usr/bin/env python3

# Update the charmcraft.yaml to have some build-on and run-on lines.

import logging
import os
from pathlib import Path
import re
import sys
from typing import List, Optional, Dict
import textwrap


BASES_LIST = [f"{t}\n" for t in textwrap.dedent(
    """\
    bases:
      - build-on:
          - name: ubuntu
            channel: "20.04"
            architectures:
              - amd64
        run-on:
          - name: ubuntu
            channel: "20.04"
            architectures: [amd64, s390x, ppc64el, arm64]
    """).splitlines()]

logger = logging.getLogger(__name__)

BASES_MATCH = re.compile(r'^(\s*)bases:\s+(?:|#.*)$')


def update_bases_yaml_as_text(lines: List[str]) -> List[str]:
    """Update a yaml file as text to add the bases."""
    out = []
    indent: Optional[str] = None
    done: bool = False
    for line in lines:
        print(f"processing {line.strip()}")
        if done:
            print("appending")
            out.append(line)
            continue
        base_match = BASES_MATCH.match(line)
        if base_match:
            print("base matched")
        if base_match and indent is None:
            indent = base_match[1]
            continue
        if indent is not None and not done:
            if line.startswith(indent) and len(line.strip()) != 0:
                # ignore lines that are in the base indent.
                continue
            else:
                # we've reached the end of block so replace the bases with our slot
                out.extend(BASES_LIST)
                done = True
        out.append(line)
    if done is False and indent is not None:
        out.extend(BASES_LIST)
    return out


# update the charmcraft.yaml file (passed on the line as arg1) and ensure that
# it has the bases added.
def main() -> None:
    assert len(sys.argv) > 1
    filename = sys.argv[1]
    try:
        with open(filename) as f:
            file_lines = f.readlines()
    except Exception:
        print(f"Couldn't open {filename}")
        return
    new_lines = update_bases_yaml_as_text(file_lines)
    # for line in new_lines:
        # print(line, end="")
    new_file_name = "charmcraft.yaml.new"
    with open(new_file_name, "wt") as f:
        f.writelines(new_lines)
    # now overwrite the file
    os.rename(new_file_name, filename)


if __name__ == '__main__':
    logging.basicConfig()
    main()
