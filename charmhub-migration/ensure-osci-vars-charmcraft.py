#!/usr/bin/env python3

# Update the project: section in the osci.yaml to have the right build part
#
# pass the path/filename of osci.yaml as the first param.

import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import List, Optional, Dict
import textwrap

logger = logging.getLogger(__name__)

PROJECT_MATCH = re.compile(r'^(\s*-\s+)project:\s+(?:|#.*)$')
VARS_MATCH = re.compile(r'^(\s*)vars:\s+(?:|#.*)$')


def template(indent_len: int, charm: str) -> List[str]:
    indent=' ' * indent_len
    block = [f"{indent}{t}\n" for t in textwrap.dedent(
        """\
            vars:
              needs_charm_build: true
              charm_build_name: {charm}
              build_type: charmcraft
        """.format(charm=charm)).splitlines()]
    logger.info('-' * 80)
    logger.info("Block is:")
    for line in block:
        logger.info(line.rstrip())
    logger.info('-' * 80)
    return block


def update_project_yaml_as_text(charm: str, lines: List[str]) -> List[str]:
    """Update a yaml file to add the template to the project as vars."""
    out = []
    indent: Optional[str] = None
    vars_indent: Optional[str] = None
    done: bool = False
    for line in lines:
        logger.debug("processing: %s", line.strip())
        if done:
            out.append(line)
            continue
        # base_match = BASES_MATCH.match(line)
        project_match = PROJECT_MATCH.match(line)
        if project_match and indent is None:
            logger.debug("project matched")
            indent = ' ' * len(project_match[1])
            out.append(line)
            continue
        if indent is not None and not done:
            vars_match = VARS_MATCH.match(line)
            if vars_match and vars_indent is not None:
                raise RuntimeError("Two vars blocks in the project??")
            if vars_match:
                logger.debug("Vars block")
                vars_indent = vars_match[1]
                continue
            if vars_indent is not None:
                if line.startswith(vars_indent) and len(line.strip()) != 0:
                    # ignore the vars line.
                    continue
                else:
                    logger.info(
                        "Hit end of vars block, modifying block at indent %s",
                        len(vars_indent))
                    # we've gobbled up the vars, so replace with the block.
                    vars_lines: List[str] = template(len(vars_indent),
                                                     charm)
                    out.extend(vars_lines)
                    done = True
                    out.append(line)
                    continue
            if line.startswith(indent) and len(line.strip()) != 0:
                out.append(line)
                continue
            else:
                # we've reached the end of block so replace the lines
                logger.info(
                    "Reached end of project block adding at indent %s",
                    len(indent) +2)
                vars_lines: List[str] = template(len(indent) + 2, charm)
                out.extend(vars_lines)
                done = True
        out.append(line)
    if done is False and indent is not None:
        logger.info("Hit end of file, adding at indent %s", len(indent) + 2)
        vars_lines: List[str] = template(len(indent) + 2, charm)
        out.extend(vars_lines)
    return out


def determine_charm_name_from_git() -> str:
    command = "git config remote.origin.url"
    try:
        result = subprocess.check_output(command.split()).decode()
    except subprocess.CalledProcessError as e:
        logger.error("Couldn't determine charm name from git?: %s", e)
        sys.exit(1)
    name_part = result.split('/')[-1]
    if '.' in name_part:
        name_part = name_part.split('.')[0]
    charm_name = '-'.join(name_part.split('-')[1:])
    return charm_name



# need to pass the file to update.
# needs to be run in the git repo for the charm
def main() -> None:
    assert len(sys.argv) > 1
    filename = sys.argv[1]
    logger.info("Ensuring charmcraft vars block is correct.")
    logger.info("File examined is: %s", filename)
    with open(filename) as f:
        file_lines = f.readlines()
    charm = determine_charm_name_from_git()
    logger.info("Determined charm name as: %s", charm)
    new_lines = update_project_yaml_as_text(charm, file_lines)
    new_file_name = "new.yaml.new"
    with open(new_file_name, "wt") as f:
        f.writelines(new_lines)
    # now overwrite the file
    os.rename(new_file_name, filename)
    logger.info("Completed.")


if __name__ == '__main__':
    logging.basicConfig()
    logger.setLevel('INFO')
    main()
