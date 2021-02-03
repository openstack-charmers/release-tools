#!/usr/bin/env python3

import os
import re
import sys
import subprocess
import textwrap

from typing import List, Optional, Dict, Tuple

# Try to fetch and checkout the review by topic.  The end branch is the topic
# name.  If no review of that topic exists, then then script returns exit 1.
# Otherwise exit code 0.  Any other failure is exit code 2.


def usage(progname: str) -> str:
    """Return a string which is the usage string.

    :param progname: the name of the program
    :returns: usage string, multiline
    """
    return textwrap.dedent(
        """{} [directory]

           where:
              [directory] - optional directory to cd into and then work.


           Get a list of all the topics and see if there are any duplicate
           reviews on them.
        """.format(sys.argv[0]))


def run_cmd(cmd: str) -> str:
    """Run the command, decode to utf-8 and result the result string.

    :param cmd: the command to run.
    :returns: the string from the output of the command
    :raises: subprocess.CalledProcessError on error
    """
    return subprocess.check_output(cmd.split(' ')).decode('utf-8')


def find_duplicate_reviews() -> Dict[str, List[Tuple[str, str]]]:
    """Find duplicate reviews by topic.  Returns a dict of list of strings.

    If dictionary entry exists, then there must be at least 2 reviews on it.

    This uses "git review -ll" to get the reviews in this form:

    770365  master  sync-for-21-01  Updates for testing period for 20.01 ...
    768967  master               -  Use unittest.mock instead of mock
    757720  master     bug/1750486  Add NRPE checks for services
    734229  master       drop_mock  Use unittest.mock instead of mock
    721085  master   unittest.mock  Use unittest.mock instead of third ...
    724532  master               -  Add Python3 victoria unit tests

    :returns: a dictionary of duplicate review numbers, where the list is a
        tuple of (id, git review -ll line)
    """
    cmd = "git review -ll"
    try:
        results = run_cmd(cmd)
    except subprocess.CalledProcessError as e:
        print(f"Something went wrong with the subprocess: {e}")
        return None
    lines = [s.strip() for s in results.splitlines()]
    results = {}
    for line in lines:
        parts = [p for p in line.split(' ') if p.strip()]
        if len(parts) >=2 and parts[2] != "-":
            try:
                results[parts[2]].append((parts[0], line))
            except KeyError:
                results[parts[2]] = [(parts[0], line)]
    return {k: vs for k, vs in results.items() if len(vs) > 1}
    return results


def main(args: List[str]):
    """Main entry for the script.

    :param args: The arguments supplied to the script.
    """
    chdir = args[1] if len(args) > 1 else None
    if chdir and chdir.lower() in ("-h", "--help"):
        print(usage())
        sys.exit(0)

    try:
        # change directory if supplied
        if chdir:
            os.chdir(chdir)

        # find duplicate reviews.
        reviews = find_duplicate_reviews()
        if reviews:
            print("found duplicate reviews for:")
            for topic, lines in reviews.items():
                print(f"For topic: {topic}")
                for (_, line) in lines:
                    print(f"  {line}")
        sys.exit(0)
    except Exception as e:
        print(f"Something went wrong: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main(list(sys.argv))
