#!/usr/bin/env python3

# Helper script to promote charm revisions from edge, beta, candidate -> beta,
# candidate, stable as required.
# Works with sections (openstack,ceph,ovn,misc) and individual charms, and on
# specific tracks.  Please see help for the command for more details.

import argparse
import logging
from pathlib import Path
from typing import List, Optional, NamedTuple
import requests
import subprocess
import sys


SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.append(str(SCRIPT_DIR.parent))
CHARMS_DIR = SCRIPT_DIR / 'charms'

from lib.lp_builder import get_charms, Charm
from lib.channel_map import decode_channel_map

# from https://api.snapcraft.io/docs/charms.html
CHARMHUB_BASE = "https://api.charmhub.io/v2/charms"
INFO_URL = CHARMHUB_BASE + "/info/{charm}?fields=channel-map"


logger = logging.getLogger(__name__)


class Release(NamedTuple):
    charmhub: str
    revision: int

class NoRelease(NamedTuple):
    charmhub: str
    issue: str


def clean_track(
    charms: List[Charm],
    track: str,
    risk: str,
    base: str,
    arch: Optional[str] = None,
    confirmed: bool = False,
    ignore_errors: bool = False,
) -> None:
    """Clean a track by finding the most recent revision.

    This uses the arch/base/track/risk to find the most recent revision of
    that is released there, then closes the track, and then re-releases the
    revision back to this track.  That cleans the track up.
    """
    releases: List[Release] = []
    errors: List[NoRelease] = []
    for charm in charms:
        print(f"Looking at {charm.charmhub}")
        cr = INFO_URL.format(charm=charm.charmhub)
        result = requests.get(cr).json()
        try:
            revision = decode_channel_map(
                charm.charmhub, result, track, risk,
                base=base,
                arch=arch)
        except ValueError as e:
            if ignore_errors:
                error = f"Ignoring {charm.charmhub} charm due to ({e})"
                logger.info(error)
                errors.append(NoRelease(charm.charmhub, error))
                continue
            raise
        releases.append(Release(charm.charmhub, revision))
    # if we don't automatically confirm (confirmed == True) then print it out
    # and get acceptance.
    if not confirmed:
        print(f"The following releases on channel: {track}/{risk} "
              f"for base: {base}")
        if arch:
            print(f"also search restricted to charms built on: {arch}")
        if releases:
            print(f"{'Charm':<30} {'Revision':^15}")
            print(f"{'-' * 30} {'-' * 15}")
            for release in releases:
                print(f"{release.charmhub:<30} {release.revision:^15} ")
            print(f"{'-' * 30} {'-' * 15}")
            print()
        if errors:
            print(f"{'Charm':<30} Issue")
            print(f"{'-' * 30} {'-' * 50}")
            for error in errors:
                print(f"{error.charmhub:<30} {error.issue}")
            print(f"{'-' * 30} {'-' * 50}")

        # Ask if we should proceed
        while True:
            yn = input('Process: (y/N): ').lower()
            if yn in ('y', 'yes'):
                confirmed = True
                break
            if yn in ('n', 'no'):
                break
            print("Please enter 'y' or 'n'")
        if not confirmed:
            print("Not doing anything!")
            return
    # Now do the releases
    # do something with resources?
    failures: List[str] = []
    successes: List[str] = []
    for release in releases:
        # first clean the channel
        cmd = (f"charmcraft close {release.charmhub} {track}/{risk}")
        print(f"Cleaning channel using: {cmd}")
        try:
            subprocess.check_call(cmd.split())
        except Exception as e:
            if ignore_errors:
                logger.error("Attempting to clean with '%s' failed: %s",
                             cmd, str(e))
                failures.append(release.charmhub)
                continue
            raise
        # then release the revision back into the channel.
        cmd = (f"charmcraft release {release.charmhub} "
               f"--revision {release.revision} "
               f"--channel={track}/{risk}")
        print(f"Re-releasing: {cmd}")
        try:
            subprocess.check_call(cmd.split())
            successes.append(release.charmhub)
        except Exception as e:
            if ignore_errors:
                logger.error("Attempting to run '%s' resulted in: %s",
                             cmd, str(e))
                failures.append(release.charmhub)
                continue
            raise
    print()
    print("Finished.")
    if errors:
        print("Not attempted due to no revision being found: {}"
              .format(", ".join(e.charmhub for e in errors)))
    if failures:
        print("Failed releases: {}".format(", ".join(failures)))
    else:
        print("No failures")
    if successes:
        print("Successful releases: {}".format(", ".join(successes)))
    else:
        print("No successes!!")


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse command line arguments.

    :param argv: List of configure functions functions
    :returns: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description=(
            "Clean a track/risk (channel) by picking the most recent "
            "arch/base/track/risk revision, closing the track/risk and then "
            "re-releasing the charm to that track/risk.  This removes "
            "existing revisions for older bases, or specific (unsupported) "
            "architectures, and ensures that just the single revision is "
            "released into that track/risk. "
            "Note: use the --i-really-mean-it flag to override asking for "
            "confirmation as this is a potentially destructive action."))
    parser.add_argument('--log', dest='loglevel',
                        type=str.upper,
                        default='INFO',
                        choices=('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'),
                        help='Loglevel')
    parser.add_argument(
        '--section', '-s',
        dest='section',
        required=True,
        type=str.lower,
        help=('The section name (the part before the .yaml) to restrict the '
              'charms to. If all the sections are required, then :all: '
              'should be passed.'))
    parser.add_argument(
        '--charm', '-c',
         dest='charms',
         action='append',
         metavar='CHARM',
         type=str.lower,
         help=('If present, adds a specific charm to fetch.  If not present, '
               'then the section is used. If neither the section nor '
               'charm(s) are available then all the charms are fetched'))
    parser.add_argument(
        '--ignore-charm', '-i',
        dest='ignore_charms',
        action='append',
        metavar='IGNORE_CHARM',
        help=('Charms to not download. Repeat for multiple charms to ignore.'))
    parser.add_argument(
        '--track', '-t',
        dest='track',
        required=True,
        metavar='TRACK',
        help=("The track to adjust.  If the track doesn't exist then an error "
              "is raised unless --ignore-failure is specified."))
    parser.add_argument(
        '--risk', '-r',
        dest='risk',
        required=True,
        metavar='RISK',
        type=str.lower,
        choices=('edge', 'beta', 'candidate', 'stable'),
        help=("The risk to change."))
    parser.add_argument(
        '--base', '-b',
        dest='base',
        required=True,
        metavar='BASE',
        help=("The base to match to.  This is the base from which to choose "
              "the charm revision to promote. Note this the base that the "
              "charm was built on, not the bases that the charm runs on."))
    parser.add_argument(
        '--arch', '-a',
        dest='arch',
        required=False,
        metavar='ARCH',
        default=None,
        help=("The arch to match against."))
    parser.add_argument(
        '--ignore-failure',
        dest='ignore_failure',
        action='store_true',
        help=('If set, then failures on branches or worktrees are ignored. '
              ' Note that assertions that can be forced, (e.g. replace) are '
              'not ignored.'))
    parser.add_argument(
        '--i-really-mean-it',
        dest="confirmed",
        action='store_true',
        help=('If provided, then pre-confirms the action, without asking the '
              'caller of the script to confirm.'))
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
    try:
        print("Checking for cleaning a track.")
        clean_track(
            charms=charms,
            track=args.track,
            risk=args.risk,
            base=args.base,
            arch=args.arch,
            confirmed=args.confirmed,
            ignore_errors=args.ignore_failure)
    except AssertionError as e:
        print("One of the assertions is wrong: {}\n"
              "Please review and perhaps change the options to the command?"
              .format(str(e)))
        print("Aborted!!")


if __name__ == '__main__':
    logging.basicConfig()
    main()
