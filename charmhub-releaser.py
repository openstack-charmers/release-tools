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

# from https://api.snapcraft.io/docs/charms.html
CHARMHUB_BASE = "https://api.charmhub.io/v2/charms"
INFO_URL = CHARMHUB_BASE + "/info/{charm}?fields=channel-map"


logger = logging.getLogger(__name__)


class Release(NamedTuple):
    charmhub: str
    revision: int
    replaces: Optional[int]

class NoRelease(NamedTuple):
    charmhub: str
    issue: str


def release(
    charms: List[Charm],
    track: str,
    base: str,
    from_channel: str,
    to_channel: str,
    arch: Optional[str] = None,
    confirmed: bool = False,
    ignore_errors: bool = False,
):
    """Promote the list of charms from one channel to another."""
    releases: List[Release] = []
    errors: List[NoRelease] = []
    for charm in charms:
        print(charm.charmhub)
        cr = INFO_URL.format(charm=charm.charmhub)
        result = requests.get(cr)
        try:
            from_revision = decode_channel_map(
                charm.charmhub, result, track, from_channel,
                base=base,
                arch=arch)
        except ValueError as e:
            if ignore_errors:
                error = f"Ignoring {charm.charmhub} charm due to ({e})"
                logger.info(error)
                errors.append(NoRelease(charm.charmhub, error))
                continue
            raise
        try:
            to_revision = decode_channel_map(
                charm.charmhub, result, track, to_channel,
                base=base,
                arch=arch)
        except ValueError as e:
            to_revision = None
        if to_revision is not None:
            logger.info(
                "For charm: %s, revision %s will be replaced by revision %s",
                charm.charmhub, to_revision, from_revision)
        releases.append(Release(charm.charmhub, from_revision, to_revision))
    # if we don't automatically confirm (confirmed == True) then print it out
    # and get acceptance.
    if not confirmed:
        print(f"The following releases from {from_channel} to {to_channel} "
              f"on track: {track} for base: {base}")
        if arch:
            print(f"also search restricted to charms built on: {arch}")
        if releases:
            print(f"{'Charm':<30} {'Revision':^15} {'(Replaces)':^15}")
            print(f"{'-' * 30} {'-' * 15} {'-' * 15}")
            for release in releases:
                print(f"{release.charmhub:<30} {release.revision:^15} "
                      f"{release.replaces or '-':^15}")
            print(f"{'-' * 30} {'-' * 15} {'-' * 15}")
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
        cmd = (f"charmcraft release {release.charmhub} "
               f"--release {release.revision} "
               f"--channel={track}/{to_channel}")
        print(f"Doing: {cmd}")
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


def decode_channel_map(charm: str,
                       result: requests.Response,
                       track: str,
                       risk: str,
                       base: Optional[str] = None,
                       arch: Optional[str] = None,
                       ) -> int:
    """Decode the channel.

    Try to work out which revisions belong for a charm and the result from
    charmhub.  This is searched on the track/risk basis.  Optionally, it can
    further be constrained using the base the charm was built on (e.g. '20.04')
    and the arch (e.g. 'amd64').

    If more than one revision is found, then an error is returned.

    """
    assert '/' not in track
    # print(f"dump of result:\n{result.json()}")
    revision_nums = set()
    for i, channel_def in enumerate(result.json()['channel-map']):
        base_arch = channel_def['channel']['base']['architecture']
        base_channel = channel_def['channel']['base']['channel']
        channel_track = channel_def['channel']['track']
        channel_risk = channel_def['channel']['risk']
        revision = channel_def['revision']
        revision_num = revision['revision']
        arches = [f"{v['architecture']}/{v['channel']}"
                  for v in revision['bases']]
        arches_str = ",".join(arches)

        if ((base is None or base_channel == base) and
                (arch is None or base_arch == arch) and
                (channel_track, channel_risk) == (track, risk)):
            print(
                f"{charm:<30} ({i:2}) -> {base_arch:6} {base_channel} "
                f"r:{revision_num:3} "
                f"{channel_track:>10}/{channel_risk:<10} -> [{arches_str}]")
            revision_nums.add(revision_num)

    if not revision_nums:
        raise ValueError("No revisions available.")
    if len(revision_nums) > 1:
        raise ValueError(
            "More than 1 revision num found for charm: %s, revisions: %s",
            charm, sorted(revision_nums))
    return sorted(revision_nums)[-1]


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse command line arguments.

    :param argv: List of configure functions functions
    :returns: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description=(
            "Promote charms from one release channel to a more stable release "
            "channel.  e.g. from beta -> stable or edge -> candidate. "
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
        '--from',
        dest='from_channel',
        required=True,
        metavar='FROM',
        type=str.lower,
        choices=('edge', 'beta', 'candidate',),
        help=('The channel to promote from. Must be one of edge, beta or '
              'candidate.'))
    parser.add_argument(
        '--to',
        dest='to_channel',
        required=True,
        metavar='TO',
        type=str.lower,
        choices=('beta', 'candidate', 'stable'),
        help=('The channel to promote to. Must be more "stable" than FROM. '
              'Must be one of beta, candidate, stable.'))
    parser.add_argument(
        '--i-really-mean-it',
        dest="confirmed",
        action='store_true',
        help=('If provided, then pre-confirms the action, without asking the '
              'caller of the script to confirm.'))
    return parser.parse_args(argv)


def validate_channels(from_channel: str, to_channel: str):
    """Verify that the channels are valid."""
    assert from_channel in ('edge', 'beta', 'candidate')
    assert to_channel in ('beta', 'candidate', 'stable')
    channels = ('edge', 'beta', 'candidate', 'stable')
    from_index = channels.index(from_channel)
    to_index = channels.index(to_channel)
    if from_index == to_index:
        raise AssertionError(f"--from and --to are the same channel "
                             f"'{from_channel}'")
    if from_index > to_index:
        raise AssertionError(f"--from({from_channel}) is more stable than "
                             f"--to({to_channel})")

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
        pass
        print(f"Would do releases from {args.from_channel} -> "
              f"{args.to_channel} on track {args.track}.")
        validate_channels(args.from_channel, args.to_channel)
        release(
            charms=charms,
            track=args.track,
            base=args.base,
            from_channel=args.from_channel,
            to_channel=args.to_channel,
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
