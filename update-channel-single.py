#!/usr/bin/env python3

# Add a candidate channel to openstack-charmers/<charm> in bundles.
# Call as script-name.py charm

# It looks in ./charms/<name> and adds (or changes) the bundle to read from the
# candidate channel

import argparse
import itertools
import logging
import os
import pathlib
from typing import List, Optional
import re
import sys


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


CUR_DIR = pathlib.Path(__file__).parent.resolve()
CHARMS_FILE = os.path.join(CUR_DIR, 'charms.txt')
assert os.path.isfile(CHARMS_FILE), "{} doesn't exist?".format(CHARMS_FILE)

# This matches against a charm: <spec> where spec is either quoted or unquoted
# version of cs:~openstack-charmers/<name> or
# cs:~openstack-charmers-next/<name>
CHARM_MATCH = re.compile(
    r'^(\s*)charm:\s+(?:|' + r"'" + r'|")'
    r'cs:(?:~openstack-charmers/|~openstack-charmers-next/)'
    r'([a-zA-Z0-9-]+)(?:|' + r"'" + r'|")\s*(?:|#.*)$')
CHANNEL_MATCH = re.compile(r'^(\s*)channel:\s+(\S+)\s*(?:|#.*)$')


def find_bundles_dirs(charm_dir: str) -> List[str]:
    """Find the directory with bundles.

    :param charm_dir: the root dir of the charm
    :returns: the dir where the bundles are.
    """
    paths = (('tests', 'bundles'),
             ('tests', 'bundles', 'overlays'),
             ('src', 'tests', 'bundles'),
             ('src', 'tests', 'bundles', 'overlays'))

    found_list = []
    for path in paths:
        logging.debug("Searching: %s", path)
        dir_ = os.path.abspath(os.path.join(charm_dir, *path))
        if os.path.isdir(dir_):
            found_list.append(dir_)
    return found_list


def find_bundles(bundles_dir: str) -> List[str]:
    """Get a list of all bundles, including any overlays.

    :param bundles_dir: the directory with bundles (hopefully).
    :returns: List of filenames of bundles (yaml or yaml.j2)
    """
    logger.debug("scanning: %s", bundles_dir)
    bundles = []
    for file in os.listdir(bundles_dir):
        path = os.path.join(bundles_dir, file)
        if os.path.isfile(path) and not os.path.islink(path):
            if path.endswith(".yaml") or path.endswith(".yaml.j2"):
                bundles.append(path)
    return bundles


def find_bundles_in_dirs(bundles_dirs: List[str]) -> List[str]:
    """Get a list of all bundles, including any overlays in all dirs passed.

    :param bundles_dirs: the list of directories with bundles (hopefully).
    :returns: List of filenames of bundles (yaml or yaml.j2)
    """
    return list(set(itertools.chain(
        *(find_bundles(path) for path in bundles_dirs))))


def modify_channel(charms: List[str],
                   bundle_filename: str,
                   channel: Optional[str]
                   ) -> None:
    """Modify the candidate channel to the bundle as needed.

    If the :param:`channel` is not None, then it adds a "channel: <channel>" to
    the charms in the bundle that match one of the charms in the
    :param:`charms` for ~openstack-charmers or ~openstack-charmers-next.

    If the :param:`channel` is None, then the "channel:" specify is removed
    from the charm spec (as long as it matches one of the charms in
    :param:`charms`).

    :param charms: the list of charms that this will apply to.
    :param bundle_filename: the filename of the bundle to update.
    :param channel: the channel to add/modify or if None, remove.
    """
    new_file_name = "{}.new".format(bundle_filename)
    with open(bundle_filename) as f:
        file_lines = f.readlines()

    new_lines = []

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

    indent = None
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
                        if channel is not None:
                            new_lines.append(
                                "{}channel: {}\n".format(indent, channel))
                        indent = None
                        continue
            else:
                # reached the end of the yaml dict with the charm: key, so add
                # the channel: spec at the end of that dict, then go back to
                # searching for "charm:"
                # add the channel at the indent for the charm block
                # if the specified channel is not None:
                if channel is not None:
                    new_lines.append("{}channel: {}\n".format(indent, channel))
                indent = None
        match = CHARM_MATCH.match(line)
        if match:
            logger.debug("Matched charm %s on line\n%s", match[2], line)
            if match[2] in charms:
                # store the indent of the yaml dict, so that the channel: can
                # be either replaced or inserted in the same dict.
                logger.debug("Matched charm %s valid", match[2])
                indent = match[1]
        new_lines.append(line)
    # if indent is still set, the charm block was at the end of the file then
    # add the channel at the indent for the charm block if the specified
    # channel is not None:
    if indent is not None and channel is not None:
        new_lines.append("{}channel: {}\n".format(indent, channel))

    with open(new_file_name, "wt") as f:
        f.writelines(new_lines)
    # now overwrite the file
    os.rename(new_file_name, bundle_filename)


def get_charms_list(charms_file: str) -> List[str]:
    """Get the list of charms from the charms file.

    :param charms_file: the filename to read the list from.
    :returns: a list of charm names.
    """
    with open(charms_file) as f:
        return [line.strip() for line in f.readlines() if line]


def update_bundles(charms: List[str],
                   bundle_paths: List[str],
                   channel: Optional[str]) -> None:
    for path in bundle_paths:
        logger.debug("Doing path: %s", path)
        modify_channel(charms, path, channel)


def check_charm_dir_exists(charm_dir: str) -> None:
    """Validate that the channel is valid.

    :param charm_dir: the dir to check.
    :raises: AssertionError if not valid
    """
    assert os.path.isdir(charm_dir)


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
    group.add_argument('--channel',
                       dest='channel',
                       type=str.lower,
                       choices=('stable', 'candidate', 'beta', 'edge'),
                       help=('If present, adds channel spec to openstack '
                             'charms. Must use --remove-channel if this is '
                             'not supplied.')),
    group.add_argument('--remove-channel',
                       dest="remove_channel",
                       help=("Remove the channel specifier.  Don't use with "
                             "--channel."),
                       action='store_true')
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
    logger.setLevel(logging.INFO)
    logger.setLevel(getattr(logging, args.loglevel, 'INFO'))

    if args.channel:
        channel = args.channel
    elif args.remove_channel:
        channel = None
    else:
        logger.error("Something went drastically wrong!")
        sys.exit(1)

    if args.dir:
        charm_dir = os.path.abspath(args.dir)
    else:
        charm_dir = os.getcwd()

    try:
        check_charm_dir_exists(charm_dir)
    except AssertionError:
        print("\n!!! Charm dir {} doesn't exist".format(charm_dir))
        sys.exit(1)

    if channel is not None:
        logger.info("Charm dir: %s, adding/changing channel to %s",
                    charm_dir, channel)
    else:
        logger.info("Charm dir: %s, removing the channel spec.", charm_dir)

    dirs = find_bundles_dirs(charm_dir)
    bundles = find_bundles_in_dirs(dirs)
    charms = get_charms_list(CHARMS_FILE)
    update_bundles(charms, bundles, channel)
    logging.info("done.")


if __name__ == '__main__':
    main()
