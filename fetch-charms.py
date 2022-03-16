#!/usr/bin/env python3

# Fetch charms using lp-builder-config

import argparse
import contextlib
import itertools
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict, Generator, Union
import re
import shutil
import subprocess
import sys


SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.append(str(SCRIPT_DIR.parent))
CHARMS_DIR = SCRIPT_DIR / 'charms'

from lib.lp_builder import get_charms, Charm


logger = logging.getLogger(__name__)


@contextlib.contextmanager
def change_directory_to(path: Union[Path, str]) -> Generator:
    """Change working directory to path, and then return afterwards"""
    current_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(current_cwd)


def fetch_charms(charms: List[Charm],
                 where: Path,
                 replace: bool = False,
                 branch: Optional[str] = None,
                 worktrees: Optional[List[str]] = None,
                 ignore_failure: bool = False,
                 worktree_dir: str = '__worktress',
                 ) -> None:
    """Fetch all the charms to where/<charmhub> directories."""
    # ensure the where directory exists.
    where.mkdir(parents=True, exist_ok=True)
    for c in charms:
        dest = where / c.charmhub
        if dest.exists():
            if dest.is_file():
                raise AssertionError(
                    f"Path: {dest} is a file, but we need to checkout "
                    f"{c.charmhub}")
            if dest.is_dir():
                if not replace:
                    raise AssertionError(
                        f"Path: {dest} exists, but replace is false")
                print(f"Removing '{dest}' so that it can be replaced.")
                shutil.rmtree(dest)
        command = f"git clone {c.repository} {dest}"
        print(f"Cloning {c.charmhub} from {c.repository} to {dest}")
        try:
            subprocess.check_call(command.split())
        except subprocess.CalledProcessError as e:
            logger.error("Error cloning repo for %s: %s", c.charmhub, str(e))
            if not ignore_failure:
                raise
        if branch is not None and branch != 'master':
            print(f" -- checking out branch: {branch}")
            try:
                with change_directory_to(dest):
                    command = f"git checkout --track origin/{branch}"
                    subprocess.check_call(command.split())
            except subprocess.CalledProcessError as e:
                logger.error("Error checking out repo for %s: %s", c.charmhub,
                             str(e))
                if not ignore_failure:
                    raise
        if worktrees is not None:
            print(f"Checking out worktrees:")
            for worktree in worktrees:
                path = Path(worktree_dir) / worktree
                command = f"git worktree add {path} {worktree}"
                print(f" -- adding worktree {worktree} to {path}")
                try:
                    with change_directory_to(dest):
                        subprocess.check_call(command.split())
                except subprocess.CalledProcessError as e:
                    logger.error("Error adding worktree for %s: %s",
                                 c.charmhub, str(e))
                    if not ignore_failure:
                        raise

def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse command line arguments.

    :param argv: List of configure functions functions
    :returns: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description=('Fetch charms to a directory (default "charms" in '
                     'the release-tools directory.  Use options to determine '
                     'which charms to fetch.'))
    parser.add_argument('--log', dest='loglevel',
                        type=str.upper,
                        default='INFO',
                        choices=('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'),
                        help='Loglevel')
    parser.add_argument('--section', '-s',
                        dest='section',
                        required=True,
                        type=str.lower,
                        help=('The section name (the part before the .yaml) '
                              'to restrict the charms to. If all the sections '
                              'are required, then :all: should be passed.'))
    parser.add_argument('--charm', '-c',
                       dest='charms',
                       action='append',
                       metavar='CHARM',
                       type=str.lower,
                       help=('If present, adds a specific charm to fetch.  If '
                             'not present, then the section is used. If '
                             'neither the section nor charm(s) are available '
                             'then all the charms are fetched'))
    parser.add_argument('--ignore-charm', '-i',
                        dest='ignore_charms',
                        action='append',
                        metavar='IGNORE_CHARM',
                        help=('Charms to not download. Repeat for multiple '
                              'charms to ignore.'))
    parser.add_argument('--worktree', '-w',
                        dest='worktrees',
                        action='append',
                        metavar='WORKTREE',
                        help=('Add a work tree to (default __worktrees/) for '
                              'the branch mentioned.  See --worktree-dir '
                              'to control where it is added. If the branch '
                              'does not exist then the checkout fails. '))
    parser.add_argument('--worktree-dir',
                        dest="worktree_dir",
                        help=('Set the subdirectory that worktrees are '
                              'checked out into.  Default "__worktrees"'))
    parser.add_argument('--branch', '-b',
                        dest='branch',
                        metavar='BRANCH',
                        help=("The branch to fetch, default of master. If the "
                              "branch doesn't exist then an error is raised "
                              "and the fetch is abandoned."))
    parser.add_argument('--dir', '-d',
                        dest='directory',
                        metavar='DIRECTORY',
                        help=('The colletion directory to put the fetched '
                              'repositories in.  Defaults to '
                              './charms'))
    parser.add_argument('--replace',
                        dest='replace',
                        action='store_true',
                        help=('Overwrite the repository if it exists.  If it '
                              'does exist and replace is not set then the '
                              'fetch fails and the command exits.'))
    parser.add_argument('--ignore-failure',
                        dest='ignore_failure',
                        action='store_true',
                        help=('If set, then failures on branches or worktrees '
                              'are ignored.  Note that assertions that can be '
                              'forced, (e.g. replace) are not ignored.'))
    parser.set_defaults(worktree_dir='__worktrees',
                        ignore_failure=False,
                        loglevel='INFO')
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    logger.setLevel(getattr(logging, args.loglevel, 'INFO'))
    print(args)
    charms = get_charms(args.section)
    if args.charms:
        charms = [c for c in charms if c.charmhub in args.charms]
    if args.ignore_charms:
        charms = [c for c in charms if c.charmhub not in args.ignore_charms]
    directory = Path(args.directory) if args.directory else CHARMS_DIR
    try:
        fetch_charms(
            charms=charms,
            where=directory,
            replace=args.replace,
            branch=args.branch,
            worktrees=args.worktrees,
            worktree_dir=args.worktree_dir,
            ignore_failure=args.ignore_failure)
    except AssertionError as e:
        print("One of the assertions is wrong: {}\n"
              "Please review and perhaps change the options to the command?"
              .format(str(e)))
        print("Aborted!!")


if __name__ == '__main__':
    logging.basicConfig()
    main()
