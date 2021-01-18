#!/usr/bin/env python3

import os
import re
import sys
import subprocess
import textwrap

from typing import List, Optional

# Try to fetch and checkout the review by topic.  The end branch is the topic
# name.  If no review of that topic exists, then then script returns exit 1.
# Otherwise exit code 0.  Any other failure is exit code 2.


def usage(progname: str) -> str:
    """Return a string which is the usage string.

    :param progname: the name of the program
    :returns: usage string, multiline
    """
    return textwrap.dedent(
        """{} <topic> [directory]

           where:
              <topic>     - the topic to search reviews for and checkout
              [directory] - optional directory to cd into and then work.


           Try to fetch and checkout the review by topic.  The end branch is
           the topic name.  If no review of that topic exists, then then script
           returns exit 1.  Otherwise exit code 0.  Any other failure is exit
           code 2.
        """.format(sys.argv[0]))


def run_cmd(cmd: str) -> str:
    """Run the command, decode to utf-8 and result the result string.

    :param cmd: the command to run.
    :returns: the string from the output of the command
    :raises: subprocess.CalledProcessError on error
    """
    return subprocess.check_output(cmd.split(' ')).decode('utf-8')


def find_review(topic: str) -> Optional[str]:
    """find a review based on the topic.

    This uses "git review -ll" to get the reviews in this form:

    770365  master  sync-for-21-01  Updates for testing period for 20.01 ...
    768967  master               -  Use unittest.mock instead of mock
    757720  master     bug/1750486  Add NRPE checks for services
    734229  master       drop_mock  Use unittest.mock instead of mock
    721085  master   unittest.mock  Use unittest.mock instead of third ...
    724532  master               -  Add Python3 victoria unit tests

    :param topic: the topic to search for (e.g. sync-for-21-01)
    :returns: the review id for the topic (e.g. 770365)
    """
    cmd = "git review -ll"
    try:
        results = run_cmd(cmd)
    except subprocess.CalledProcessError as e:
        print(f"Something went wrong with the subprocess: {e}")
        return None
    lines = [s.strip() for s in results.splitlines()]
    for line in lines:
        parts = [p for p in line.split(' ') if p.strip()]
        if len(parts) >=2 and parts[2] == topic:
            return parts[0]
    print(f"No review found with topic {topic}")
    return None


def fetch_review(review_id: str, review_topic: str):
    """Fetch the review review_id and change the branch name to review_topic.

    If the topic already exists then it has to do the download twice.  Once to
    fetch the branch to get the review branch name (in the form of
    "review/{id}/topic", then to rename the topic branch to that name, and
    finally to refetch the review to update the topic branch and then rename
    the branch back to the topic.

    :param review_id: the review to fetch.
    :param review_topic: the name of the branch after the fetch
    :raises: subprocess.CalledProcessError if there problems with the git
        commands.
    """
    # get a list of current branches to see if we have one
    topic_branch = None
    branches = [l[2:] for l in run_cmd("git branch").splitlines()]
    for branch in branches:
        if branch.strip() == review_topic:
            topic_branch = review_topic
            break
    # download the review
    result_line = run_cmd(f"git review -d {review_id}").splitlines()[-1]
    gerrit_review_name = re.search(r'"(.*)"', result_line).group(1)
    # if we have a topic branch already, delete the just downloaded one,
    # rename the current one to the downloaded name and then re-download it
    print(f"gerrit name: {gerrit_review_name}")
    if topic_branch:
        print(f"Rename topic: {review_topic} to {gerrit_review_name} for"
               " update")
        run_cmd("git checkout master")
        run_cmd(f"git branch -D {gerrit_review_name}")
        run_cmd(f"git branch -m {topic_branch} {gerrit_review_name}")
        print(run_cmd(f"git review -d {review_id}"))
    # finally rename the review to the topic name
    run_cmd(f"git branch -m {gerrit_review_name} {review_topic}")
    print(f"fetched {gerrit_review_name} as {review_topic}")


def main(args: List[str]):
    """Main entry for the script.

    :param args: The arguments supplied to the script.
    """
    if len(args) < 2:
        print(usage(args[0]))
        sys.exit(2)

    review_topic = args[1]
    chdir = args[2] if len(args) > 2 else None

    try:
        # change directory if supplied
        if chdir:
            os.chdir(chdir)

        review_id = find_review(review_topic)
        if review_id is None:
            sys.exit(1)

        print(f"review found as {review_id}")
        fetch_review(review_id, review_topic)
        sys.exit(0)
    except Exception as e:
        print(f"Something went wrong: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main(list(sys.argv))
