#!/usr/bin/env python3

# Add a candidate channel to openstack-charmers/<charm> in bundles.
# Call as script-name.py charm

# It looks in ./charms/<name> and adds (or changes) the bundle to read from the
# candidate channel

import argparse
import itertools
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict
import re
import sys

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.append(str(SCRIPT_DIR.parent))

from lib.lp_builder import get_lp_builder_config


logger = logging.getLogger(__name__)


CUR_DIR = Path(__file__).parent.resolve()
LP_DIR = CUR_DIR / 'lp-builder-config'
assert LP_DIR.is_dir(), f"{LP_DIR} doesn't seem to exist?"

# type Alias for LpConfig struture.
LpConfig = Dict[str, Dict[str, List[str]]]

# This matches against a charm: <spec> where spec is either quoted or unquoted
# version of cs:~openstack-charmers/<name> or
# cs:~openstack-charmers-next/<name>
# or ch:<name>
# Includes 3 capture groups:
# 1. the whitespace at the beginning of the line
# 2. the prefix (cs: or ch:)
# 3. the charm name
CHARM_MATCH = re.compile(
    r'^(\s*)charm:\s+(?:|' + r"'" + r'|")'
    r'(ch:|cs:(?:~openstack-charmers/|~openstack-charmers-next/))'
    r'([a-zA-Z0-9-]+)(?:|' + r"'" + r'|")\s*(?:|#.*)$')
CHANNEL_MATCH = re.compile(r'^(\s*)channel:\s+(\S+)\s*(?:|#.*)$')
# Match any charm; used after the specific CHARM_MATCH to re-write charms using
# as cs: prefix to a ch: prefix if needed.
ANY_CHARM_MATCH = re.compile(
    r'^(\s*)charm:\s+(?:|' + r"'" + r'|")'
    r'(cs:.*/)'
    r'([a-zA-Z0-9-]+)(?:|' + r"'" + r'|")\s*(?:|#.*)$')


def find_bundles_dirs(charm_dir: Path) -> List[Path]:
    """Find the directory with bundles.

    :param charm_dir: the root dir of the charm
    :returns: the dir where the bundles are.
    """
    paths = (('tests', 'bundles'),
             ('tests', 'bundles', 'overlays'),
             ('src', 'tests', 'bundles'),
             ('src', 'tests', 'bundles', 'overlays'))

    found_list: List[Path] = []
    for path in paths:
        logging.debug("Searching: %s", path)
        dir_ = charm_dir.joinpath(*path)
        if dir_.is_dir():
            found_list.append(dir_)
    return found_list


def find_bundles(bundles_dir: Path) -> List[Path]:
    """Get a list of all bundles, including any overlays.

    :param bundles_dir: the directory with bundles (hopefully).
    :returns: List of filenames of bundles (yaml or yaml.j2)
    """
    logger.debug("scanning: %s", bundles_dir)
    bundles: List[Path] = []
    for file in bundles_dir.iterdir():
        path = bundles_dir.joinpath(file)
        if path.is_file() and not path.is_symlink():
            if path.suffix == '.yaml' or path.suffixes == ['.yaml', '.j2']:
                bundles.append(path)
    return bundles


def find_bundles_in_dirs(bundles_dirs: List[Path]) -> List[Path]:
    """Get a list of all bundles, including any overlays in all dirs passed.

    :param bundles_dirs: the list of directories with bundles (hopefully).
    :returns: List of filenames of bundles (yaml or yaml.j2)
    """
    return list(set(itertools.chain(
        *(find_bundles(path) for path in bundles_dirs))))


def modify_channel(charms: List[str],
                   lp_config: LpConfig,
                   bundle_filename: Path,
                   channel: Optional[str],
                   branches: List[str],
                   ensure_charmhub_prefix: bool,
                   ignore_tracks: List[str],
                   set_local_charm: Optional[str],
                   disable_local_overlay: bool,
                   ) -> None:
    """Modify the candidate channel to the bundle as needed.

    If the :param:`branches` is populated, then they are the github branches
    from the lp builder config. In this case the lp builder config is used to
    determine the channel.  If the charm doesn't have the branch, then it is
    ignored.  This allows the program to be run with a branch of
    'stable/queens' for the openstack charms, 'stable/nautilus' for the ceph
    charms and 'stable/focal' for the misc charms.  Multiple branches may be
    used and they will all be tried against the charm if it exists in the
    config.

    Otherwise, if the :param:`channel` is not None, then it adds a "channel:
    <channel>" to the charms in the bundle that match one of the charms in the
    :param:`charms` for ~openstack-charmers or ~openstack-charmers-next.

    If the :param:`channel` is None, then the "channel:" specify is removed
    from the charm spec (as long as it matches one of the charms in
    :param:`charms`).

    The :param:`ignore_tracks` argument is a list of tracks (with optional
    /channel part) that will not be used. e.g. if latest is never to be used,
    then it is ignored.

    :param charms: the list of charms that this will apply to.
    :param lp_config: The lp config as derived from lp-builder-config/*.yaml
    :param bundle_filename: the filename of the bundle to update.
    :param channel: the channel to add/modify or if None, remove.
    :param branches: the branch(es) to test if branches are specified.
    :param ensure_charmhub_prefix: if set to True, switches a cs:.../ prefix to
        "ch:"
    :param ignore_tracks: Tracks or prefixes to ignore.  Note that the test is
        "starts with" so that 'latest' can match against any channel, for
        example.
    """
    logger.debug("Looking at file: %s", bundle_filename)
    new_file_name = bundle_filename.with_suffix(
        f"{bundle_filename.suffix}.new")
    with open(bundle_filename) as f:
        file_lines = f.readlines()

    new_lines = []

    # get the list of charms to match against
    if branches:
        valid_charms = list(lp_config.keys())
    else:
        valid_charms = charms[:]

    def _get_channel(_charm: Optional[str]) -> Optional[str]:
        """Get the channel based on branches and channel contents.

        If the branches are set, then use the LpConfig to find the channel
        based on any of the branches supplied.  If none are found then don't
        update this charm (returns None).

        If the track/channel found matches an ignore_tracks (from the parent
        closure) then None is returned.

        Otherwise just return the current channel in the `channel` var.

        :param _charm: the charm to check against.
        """
        if _charm is None:
            return None
        if not branches:
            return channel
        for branch in branches:
            try:
                for track in lp_config[_charm][branch]:
                    for ignore in ignore_tracks:
                        if track.startswith(ignore):
                            # ignore this track
                            break
                    else:
                        # return lp_config[_charm][branch][0]
                        return track
            except (KeyError, IndexError):
                pass
        # The charm/branch didn't match so return None
        return None

    ###
    # The following for-loop code implements an algorithm that searches for a
    # 'charm:' specification line that matches the regex in CHARM_MATCH, and
    # when found, it then looks for a 'channel:' specification in the same
    # level block in the yaml file. The CHARM_MATCH regex extracts the indent
    # of the line and the name of the charm.  The CHANNEL_MATCH regex also
    # extracts the indent of the line and the channel that is assigned.
    #
    # The 'indent' variable both indicates the indent of the yaml dictionary
    # that the 'charm:' key is at AND whether the for-loop is searching for a
    # 'channel:' key.
    #
    # The algorithm is:
    #  * set the indent to None, so that the for-loop searches for a charm:
    #    key.
    #  * If a 'charm:' match is found, store the indent, to indicate to search
    #    for a 'channel:' key.
    #  * When seaching for the channel:
    #    - if the line doesn't start with the indent string, then the yaml
    #      dictionary that the charm: was found in has ended so ADD the
    #      channel: spec at that point, and then go back to searching for
    #      charm:.
    #    - if the line does start with the indent string, see if it is a match
    #      to the CHANNEL_REGEX. If so, check the indents are the same, and if
    #      so, replace the channel, go back to searching for charm: AND don't
    #      add the existing channel: line.
    #  * If th indent is still a string at the end of the file, then add the
    #    channel: as the yaml dictionary with the 'charm:' key was at the end
    #    of the file.
    #
    #  The 'continue' statement is to drop the channel: line that is being
    #  replaced.  In all other cases a channel: line is added to the block.
    #
    ###

    print(f"set_local_charm is {set_local_charm}")
    if set_local_charm:
        LOCAL_CHARM_MATCH = re.compile(
            r'^(\s*)charm:\s+[./]*' + set_local_charm + r'\s*(?:|#.*)$')
        print(f"set local regex for {set_local_charm}")
    indent = None
    current_charm: Optional[str] = None
    for line in file_lines:
        if indent is not None:
            # searching for channel: inside the same yaml dict as charm: found
            if line.startswith(indent):
                channel_match = CHANNEL_MATCH.match(line)
                if channel_match:
                    # only replace the channel: if it is at the same indent.
                    if channel_match[1] == indent:
                        # replace the channel at the indent for the charm block
                        # if the specified channel is not None:
                        if channel is not None or branches:
                            _channel = _get_channel(current_charm)
                            if _channel is not None:
                                new_lines.append(
                                    "{}channel: {}\n".format(indent, _channel))
                            else:
                                new_lines.append(line)
                        indent = None
                        current_charm =None
                        continue
            else:
                # reached the end of the yaml dict with the charm: key, so add
                # the channel: spec at the end of that dict, then go back to
                # searching for "charm:"
                # add the channel at the indent for the charm block
                # if the specified channel is not None:
                if channel is not None or branches:
                    _channel = _get_channel(current_charm)
                    if _channel is not None:
                        new_lines.append("{}channel: {}\n".format(
                            indent, _channel))
                indent = None
                current_charm = None
        match = CHARM_MATCH.match(line)
        any_charm_match = ANY_CHARM_MATCH.match(line)
        if match:
            logger.debug("Matched charm %s on line\n%s", match[3], line)
            if match[3] in valid_charms:
                # store the indent of the yaml dict, so that the channel: can
                # be either replaced or inserted in the same dict.
                current_charm = match[3]
                logger.debug("Matched charm %s valid", match[3])
                indent = match[1]
                charm_prefix = match[2]
                if ensure_charmhub_prefix and charm_prefix != 'ch:':
                    logger.debug("Replacing '%s' with 'ch:'", charm_prefix)
                    line = line.replace(charm_prefix, 'ch:')
        elif any_charm_match and ensure_charmhub_prefix:
            logger.debug("Matched charm %s on line\n%s\n - rewriting for ch:",
                         any_charm_match[3], line)
            line = line.replace(any_charm_match[2], 'ch:')
        elif set_local_charm is not None:
            local_match = LOCAL_CHARM_MATCH.match(line)  # type: ignore
            if local_match:
                print("matched!")
                prefix = \
                    '../../../' \
                    if bundle_filename.parent.parent.parent.stem == 'src' \
                    else '../../'
                line = (f"{local_match[1]}charm: "
                        f"{prefix}{set_local_charm}.charm\n")

        new_lines.append(line)
    # if indent is still set, the charm block was at the end of the file then
    # add the channel at the indent for the charm block if the specified
    # channel is not None:
    if indent is not None and (channel is not None or branches):
        _channel = _get_channel(current_charm)
        if _channel is not None:
            new_lines.append("{}channel: {}\n".format(indent, _channel))

    # finally, see if we should ensure that the bundle has the local overlay
    # disabled, but only for overlays
    if (disable_local_overlay and
            bundle_filename.suffix == '.yaml' and
            bundle_filename.parent.name != 'overlays'):
        new_lines = ensure_local_overlay_disabled(new_lines)

    with open(new_file_name, "wt") as f:
        f.writelines(new_lines)
    # now overwrite the file
    os.rename(new_file_name, bundle_filename)


def ensure_local_overlay_disabled(lines: List[str]) -> List[str]:
    """Ensure that the line 'local_overlay_enabled: False' is in the bundle."""
    for i in range(len(lines)):
        if lines[i].startswith('local_overlay_enabled:'):
            lines[i] = "local_overlay_enabled: False\n"
            return lines
    # insert local_overlay_enabled at the beginning of the file
    lines.insert(0, "\n")
    lines.insert(0, "local_overlay_enabled: False\n")
    return lines


def get_charms_list(*charms_files: Path) -> List[str]:
    """Get the list of charms from the charms files.

    Filters out comment lines (#) and any empty lines.

    :param charms_file: the filename to read the list from.
    :returns: a list of charm names.
    """
    lines = []
    for charms_file in charms_files:
        with open(charms_file) as f:
            lines.extend(line.strip() for line in f.readlines() if line)
    return [line for line in lines if line and not(line.startswith('#'))]


def update_bundles(charms: List[str],
                   lp_config: LpConfig,
                   bundle_paths: List[Path],
                   channel: Optional[str],
                   branches: List[str],
                   ensure_charmhub_prefix: bool,
                   ignore_tracks: List[str],
                   disable_local_overlay: bool,
                   set_local_charm: Optional[str],
                   ) -> None:
    for path in bundle_paths:
        logger.debug("Doing path: %s", path)
        modify_channel(
            charms, lp_config, path, channel, branches, ensure_charmhub_prefix,
            ignore_tracks, set_local_charm, disable_local_overlay)


def check_charm_dir_exists(charm_dir: Path) -> None:
    """Validate that the channel is valid.

    :param charm_dir: the dir to check.
    :raises: AssertionError if not valid
    """
    assert charm_dir.is_dir()


def determine_charm(charm_dir: Path) -> Optional[str]:
    """Workout what the charm is from the osci.yaml in the charm_dir."""
    osci_file = charm_dir / 'osci.yaml'
    if osci_file.is_file():
        with osci_file.open() as f:
            for line in f.readlines():
                if "charm_build_name" in line:
                    return line.split()[-1]
    return None


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse command line arguments.

    :param argv: List of configure functions functions
    :returns: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description=('Change or add the juju channel to the bundles '
                     'for the charm.'),
        epilog=("Either pass the directory of the charm, or be in that "
                "directory when the script is called."))
    parser.add_argument('dir', nargs='?',
                        help="Optional directory argument")
    group = parser.add_mutually_exclusive_group(required=True)
    parser.add_argument('--bundle',
                        dest='bundles',
                        action='append',
                        type=Path,
                        metavar='FILE',
                        help=('Path to a bundle file to update. '
                              'May be repeated for multiple files to update'))
    group.add_argument('--channel', '-c',
                       dest='channel',
                       type=str.lower,
                       metavar='CHANNEL',
                       help=('If present, adds channel spec to openstack '
                             'charms. Must use --remove-channel if this is '
                             'not supplied.')),
    group.add_argument('--remove-channel',
                       dest="remove_channel",
                       help=("Remove the channel specifier.  Don't use with "
                             "--channel."),
                       action='store_true')
    group.add_argument('--branch', '-b',
                       dest='branches',
                       action='append',
                       metavar='BRANCH',
                       type=str.lower,
                       help=('If present, adds a channel spec to known charms '
                             'in the lp-builder-config/*.yaml files using the '
                             'branch to map to the charmhub spec. If the '
                             'branch is not found, then the charm is ignored. '
                             'May be repeated for multiple branches to test '
                             'against.'))
    parser.add_argument('--ignore-track', '-i',
                        dest='ignore_tracks',
                        action='append',
                        metavar="IGNORE",
                        type=str.lower,
                        help=('Ignore this track.  e.g. if '
                              '"--ignore-track lastest" is used, then any '
                              'track/<channel> will be ignored if the track '
                              'is "latest".  This is only useful when used '
                              'with the "--branch" argument. Note that the '
                              'match is done via "starts_with" so that, for '
                              'example, any "latest" track can be matched '
                              'against.'))
    parser.add_argument('--ensure-charmhub',
                        dest='ensure_charmhub',
                        action='store_true',
                        default=False,
                        help=('If set to True, then cs:~.../ prefixes of '
                              'charms will be switched to ch:<charm>'))
    parser.add_argument('--disable-local-overlay',
                        dest='disable_local_overlay',
                        action='store_true',
                        default=False,
                        help=('If set to True, then ensure that '
                              '"local_overlay_enabled: False" are in the '
                              'bundles.'))
    parser.add_argument('--set-local-charm',
                        dest='set_local_charm',
                        action='store_true',
                        default=False,
                        help=('If set to True, then the local charm, as '
                              'determined by the charmcraft.yaml file is set '
                              'to the ../../(../)<charm>.charm'))
    parser.add_argument('--log', dest='loglevel',
                        type=str.upper,
                        default='INFO',
                        choices=('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'),
                        help='Loglevel')
    parser.set_defaults(channel=None,
                        remove_channel=False,
                        loglevel='INFO')
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    logger.setLevel(getattr(logging, args.loglevel, 'INFO'))

    if args.channel:
        channel = args.channel
    elif args.remove_channel or args.branches:
        channel = None
    else:
        logger.error("Something went drastically wrong!")
        sys.exit(1)

    if args.dir:
        charm_dir = Path(os.fspath(args.dir)).resolve()
    else:
        charm_dir = Path(os.getcwd())

    try:
        check_charm_dir_exists(charm_dir)
    except AssertionError:
        print("\n!!! Charm dir {} doesn't exist".format(charm_dir))
        sys.exit(1)

    if channel is not None:
        logger.info("Charm dir: %s, adding/changing channel to %s",
                    charm_dir, channel)
    elif args.branches:
        logger.info("Charm dir: %s, adding/changing channel via lp_config"
                    " git brances: %s", charm_dir, ", ".join(args.branches))
    else:
        logger.info("Charm dir: %s, removing the channel spec.", charm_dir)

    dirs = find_bundles_dirs(charm_dir)
    if args.bundles:
        bundles = args.bundles
    else:
        bundles = find_bundles_in_dirs(dirs)
    config = get_lp_builder_config()
    charms = list(config.keys())
    print(dirs, bundles, charms)
    local_charm = determine_charm(charm_dir) if args.set_local_charm \
        else None
    update_bundles(
        charms, config, bundles, channel, args.branches, args.ensure_charmhub,
        args.ignore_tracks or [],
        args.disable_local_overlay,
        local_charm,
    )
    logging.info("done.")


if __name__ == '__main__':
    logging.basicConfig()
    main()
