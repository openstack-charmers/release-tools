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


def master_main_swap(branch):
    """Swap branch name with alias of master or main"""
    if branch == 'master':
        return 'main'
    elif branch == 'main':
        return 'master'
    return None


def fetch_charms(charms: List[Charm],
                 where: Path,
                 replace: bool = False,
                 branch: Optional[str] = None,
                 worktrees: Optional[List[str]] = None,
                 ignore_failure: bool = False,
                 worktree_dir: str = '__worktrees',
                 checkout_topic: Optional[str] = None,
                 skip_if_present: bool = False,
                 reuse: bool = False,
                 ) -> None:
    """Fetch all the charms to where/<charmhub> directories."""

    def check_call(cmd: List[str]) -> None:
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as e:
            logger.error("Error running command %s: %s", " ".join(cmd), str(e))
            if not ignore_failure:
                raise

    def check_output(cmd: List[str]) -> str:
        try:
            out = subprocess.check_output(cmd).decode()
        except subprocess.CalledProcessError as e:
            logger.error("Error running command %s: %s", " ".join(cmd), str(e))
            if not ignore_failure:
                raise
        return out

    # ensure the where directory exists.
    where.mkdir(parents=True, exist_ok=True)
    for c in charms:
        dest = where / c.charmhub
        if dest.exists():
            if dest.is_file():
                raise AssertionError(
                    f"Path: {dest} is a file, but we need to checkout "
                    f"{c.charmhub}")
            if reuse:
                print(f"For {c.charmhub}, destination: {dest} exists, but "
                      f"--reuse is set, so reusing dirctory if other checks "
                      f"pass.")
            elif skip_if_present:
                print(f"For {c.charmhub}, destination: {dest} exists, but "
                      f"skip-if-present is set, so not fetching.")
                continue
            elif dest.is_dir():
                if not replace:
                    raise AssertionError(
                        f"Path: {dest} exists, but replace is false")
                print(f"Removing '{dest}' so that it can be replaced.")
                shutil.rmtree(dest)

        # Fetch the repository if we are not re-using and it doesn't exist
        if not dest.exists():
            print(f"Cloning {c.charmhub} from {c.repository} to {dest}")
            command = f"git clone {c.repository} {dest}"
            check_call(command.split())

        # Ensure that the stable branch has a --track version.
        if branch is not None and branch != 'master':
            # first get a list of branchs.
            command = ["git", "branch", "--format", '"%(refname)"']
            with change_directory_to(dest):
                branches = check_output(command)
                ref_branch = f"refs/heads/{branch}"
                if ref_branch not in branches:
                    print(f" -- checking out tracking branch: {branch}")
                    command = f"git checkout --track origin/{branch}"
                    check_call(command.split())

        # verify we are checked out into the required branch
        target_branch = "master" if branch is None else branch
        command = f"git checkout {target_branch}"
        with change_directory_to(dest):
            try:
                check_call(command.split())
            except subprocess.CalledProcessError as e:
                target_branch = master_main_swap(target_branch)
                if target_branch:
                    command = f"git checkout {target_branch}"
                    check_call(command.split())

        if worktrees is not None:
            print(f"Checking out worktrees:")
            for worktree in worktrees:
                path = Path(worktree_dir) / worktree
                if not path.exists():
                    print(f" -- adding worktree {worktree} to {path}")
                    command = f"git worktree add {path} {worktree}"
                    with change_directory_to(dest):
                        check_call(command.split())
                else:
                    print(f" -- worktree {path} already exists?")

        if checkout_topic is not None:
            print(f"Checking out topic: {checkout_topic}")
            with change_directory_to(dest):
                # first just set up the gerrit hook
                command = "git review -s"
                check_call(command.split())
                # now list the reviews and find the topic.
                command = "git review -ll"
                reviews = check_output(command.split())
                matched_reviews = []
                num = -1
                for review in reviews.splitlines()[:-1]:
                    (r_num, r_branch, r_topic, desc) = (
                        review.split(maxsplit=3))
                    print(f"'{r_num}' '{r_branch}' '{r_topic}' '{desc}'")
                    if (r_topic == checkout_topic and
                            r_branch == (branch or 'master')):
                        matched_reviews.append((r_num, r_branch, desc))
                if len(matched_reviews) == 0:
                    if ignore_failure:
                        logger.info(
                            "No matching topic for %s but ignore_faiure "
                            "is set, so continuing", c.charmhub)
                    else:
                        raise RuntimeError(
                            f"No matching topic {checkout_topic} for "
                            f"{c.charmhub}.")
                elif len(matched_reviews) > 1:
                    # now have to pick the review.
                    print("More than one matching review; please select "
                          "by index number")
                    print(f'{"Index":7} {"ID":8} {"Topic":25} '
                          f'{"Branch":15} Description')
                    for i, (n, b, desc) in enumerate(matched_reviews):
                        print(f"{i:^7} {n:<8} {checkout_topic:<25} "
                              f"{b:<15} {desc}")
                    while True:
                        reply = str(
                            input(
                                f"\nEnter 1..{len(matched_reviews)} or "
                                f"[Q]uit: ")).lower().strip()
                        if reply == "q":
                            raise RuntimeError("Quitting")
                        try:
                            num = int(reply) - 1
                            if num < 0 or num >= len(matched_reviews):
                                raise ValueError()
                            break
                        except ValueError:
                            print("Enter number or Q?")
                            continue
                else:
                    num = 0
                # now with review num, let's check it out.
                if num >= 0:
                    command = f"git review -d {matched_reviews[num][0]}"
                    print(f"Fetching review '{matched_reviews[num][2]}'")
                    check_call(command.split())

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
                              "branch does not exist then an error is raised "
                              "and the fetch is abandoned. Note that the "
                              "branch is something like 'stable/ussuri'. "
                              "'master' and 'main' are treated as an alias. "
                              "If 'master' is specified and does not exist, "
                              "'main' will also be tried and vice versa."))
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
    parser.add_argument('--checkout-topic',
                        dest='checkout_topic',
                        help=('Optionally, fetch a topic from gerrit for the '
                              'charm.  If more than one review is available '
                              'then the user is asked to choose the review '
                              'to download.  If no review is found then an '
                              'error occurs unless --ignore-failure is set.'))
    parser.add_argument('--skip-if-present',
                        dest='skip_if_present',
                        action='store_true',
                        help=('If set, then ignore any directories that '
                              'already exist.  Use this for incremental '
                              'fetches if an error occurs, but you want to '
                              'continue fetching.'))
    parser.add_argument('--reuse',
                        dest='reuse',
                        action='store_true',
                        help=('If set, then reuse the directory/repo if it '
                              'exists.  This is useful to try to check out '
                              'a topic/branch after already fetching charms.'))
    parser.set_defaults(worktree_dir='__worktrees',
                        ignore_failure=False,
                        loglevel='INFO')
    return parser.parse_args(argv)


def aborted(e):
    print("One of the assertions is wrong: {}\n"
          "Please review and perhaps change the options to the command?"
          .format(str(e)))
    print("Aborted!!")


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
            ignore_failure=args.ignore_failure,
            checkout_topic=args.checkout_topic,
            skip_if_present=args.skip_if_present,
            reuse=args.reuse,
        )
    except AssertionError as e:
        branch = master_main_swap(branch)
        if branch:
            try:
                fetch_charms(
                    charms=charms,
                    where=directory,
                    replace=args.replace,
                    branch=args.branch,
                    worktrees=args.worktrees,
                    worktree_dir=args.worktree_dir,
                    ignore_failure=args.ignore_failure,
                    checkout_topic=args.checkout_topic,
                    skip_if_present=args.skip_if_present,
                    reuse=args.reuse,
                )
            except AssertionError as e:
                aborted(e)
        else:
            aborted(e)


if __name__ == '__main__':
    logging.basicConfig()
    main()
