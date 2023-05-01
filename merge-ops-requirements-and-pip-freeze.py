#!/usr/bin/env python3

import argparse
import logging
from pathlib import Path
import re
import sys
from typing import List, Optional, NamedTuple, Iterator, Dict


logger = logging.getLogger(__name__)


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse command line arguments.

    :param argv: List of configure functions functions
    :returns: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description=(
            "Merge the requirements.txt and a pip freeze to provide a "
            "locked requirements.txt that still tracks the original branch "
            "for any VCS (git only!) python modules."))
    parser.add_argument('--log', dest='loglevel',
                        type=str.upper,
                        default='INFO',
                        choices=('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'),
                        help='Loglevel')
    parser.add_argument(
        '--requirements-file', '-r',
        dest='requirements_file',
        default='requirements.txt',
        type=str,
        help=('The requirements.txt file that contains the requirements that '
              'were used to build the charm.'))
    parser.add_argument(
        '--pip-freeze-file', '-p',
        dest='pip_freeze_file',
        default='pip-freeze.txt',
        type=str,
        help=('The pip freeze text file extracted from the charmcraft '
              'container.'))
    parser.add_argument(
        '--output', '-i',
        dest='output_file',
        default='-',
        type=str,
        help=('The output file to write the merged locked requirements to. '
              'User "-" to direct to STDOUT'))
    return parser.parse_args(argv)


def read_file(file_name: str) -> Iterator[str]:
    """Read the file."""
    with open(file_name) as f:
        for line in f:
            yield line.strip()


def write_file(filename: str, output: List[str]) -> None:
    with open(filename, "wt") as f:
        f.writelines(f"{o}\n" for o in output)


def merge(requirement: str, vcs: Dict[str, str]) -> str:
    """Merge a single requirement by maybe replacing it with a Dict item"""
    # note that we make all '-' to '_' to make the match work better.  e.g.
    # egg=ops_openstack is in the pip-freeze as ops-openstack==....
    module = requirement.split('==')[0]
    module = module.replace("-", "_")
    try:
        return vcs[module]
    except KeyError:
        return requirement


def process_requirements(requirements: List[str]) -> Dict[str, str]:
    """Convert a set of requirements into a dictionary look up.

    Note it only works with "git+https" lines.
    """
    pattern = re.compile(r"git\+https:\/\/.*#egg=(.*)")
    vcs = {}
    for requirement in requirements:
        match = pattern.match(requirement)
        if match:
            module = match[1].replace('-', '_')
            vcs[module] = requirement
    return vcs


def main() -> None:
    args = parse_args(sys.argv[1:])
    logger.setLevel(getattr(logging, args.loglevel, 'INFO'))
    requirements = list(read_file(args.requirements_file))
    vcs = process_requirements(requirements)
    output: List[str] = []
    for line in read_file(args.pip_freeze_file):
        output.append(merge(line, vcs))
    if args.output_file == '-':
        for line in output:
            print(line)
    else:
        write_file(args.output_file, output)

if __name__ == "__main__":
    logging.basicConfig()
    main()
