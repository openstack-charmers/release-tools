#!/usr/bin/env python3

# Add a candidate channel to openstack-charmers/<charm> in bundles.
# Call as script-name.py charm

# It looks in ./charms/<name> and adds (or changes) the bundle to read from the
# candidate channel

import itertools
import os
import pathlib
from typing import Optional, List
import re
import sys

CUR_DIR = pathlib.Path(__file__).parent.resolve()
CHARMS_FILE = os.path.join(CUR_DIR, 'charms.txt')
assert os.path.isfile(CHARMS_FILE), "{} doesn't exist?".format(CHARMS_FILE)

CHARM_MATCH = re.compile(
    r'^(\s*)charm:\s+cs:(?:~openstack-charmers/|~openstack-charmers-next/)'
    r'(\S+)\s*(?:|#.*)$')
CHANNEL_MATCH = re.compile(r'^(\s*)channel:\s+(\S+)\s*(?:|#.*)$')


def usage() -> None:
    """Print the usage for the script."""
    print("{} <charm-name> <channel>".format(sys.argv[0]))
    print("")
    print("Change or add the juju channel to the bundles for the charm.")


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
        print(path)
        dir_ = os.path.abspath(os.path.join(charm_dir, *path))
        if os.path.isdir(dir_):
            found_list.append(dir_)
    return found_list


def find_bundles(bundles_dir: str) -> List[str]:
    """Get a list of all bundles, including any overlays.

    :param bundles_dir: the directory with bundles (hopefully).
    :returns: List of filenames of bundles (yaml or yaml.j2)
    """
    print("scanning:", bundles_dir)
    bundles = []
    for file in os.listdir(bundles_dir):
        path = os.path.join(bundles_dir, file)
        if os.path.isfile(path):
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


def add_channel_to(charms: List[str],
                   bundle_filename: str,
                   channel: str
                   ) -> None:
    """Add the candidate channel to the bundle as needed.

    Adds a channel: candidate to the charms in the bundle that match one of the
    charms in the :param:`charms` for ~openstack-charmers or
    ~openstack-charmers-next.

    :param charms: the list of charms that this will apply to.
    :bundle_filename: the filename of the bundle to update.
    """
    new_file_name = "{}.new".format(bundle_filename)
    with open(bundle_filename) as f:
        file_lines = f.readlines()

    new_lines = []

    indent = None
    for line in file_lines:
        # line = line.rstrip()
        if indent is not None:
            if line.startswith(indent):
                channel_match = CHANNEL_MATCH.match(line)
                if channel_match:
                    if channel_match[1] == indent:
                        # replace the channel at the indent for the charm block
                        new_lines.append("{}channel: {}\n".format(indent, channel))
                        indent = None
                        continue
            else:
                new_lines.append("{}channel: {}\n".format(indent, channel))
                indent = None
        match = CHARM_MATCH.match(line)
        if match and match[2] in charms:
            indent = match[1]
        new_lines.append(line)
    # it's possible the charm block was at the end of the file
    if indent is not None:
        new_lines.append("{}channel: {}\n".format(indent, channel))

    print("file:\n{}".format("".join(new_lines)))

    with open(new_file_name, "wt") as f:
        # f.write("\n".join(new_lines))
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
                   channel: str) -> None:
    for path in bundle_paths:
        add_channel_to(charms, path, channel)


def validate_channel(channel: str) -> str:
    """Validate that the channel is valid.

    :param channel: the channel string to check.
    :returns: lowercased version of the channel
    :raises: AssertionError if not valid
    """
    channel = channel.lower()
    assert channel in ('stable', 'candidate', 'beta', 'edge')
    return channel


def check_charm_dir_exists(charm_dir: str) -> None:
    """Validate that the channel is valid.

    :param charm_dir: the dir to check.
    :raises: AssertionError if not valid
    """
    assert os.path.isdir(charm_dir)


def main() -> None:
    try:
        charm_name = sys.argv[1].lower()
        if charm_name in ('-h', '--help'):
            usage()
            sys.exit(0)
        channel = sys.argv[2].lower()
    except Exception:
        usage()
        print("\n !!! Must pass 'charm' and 'channel' to script.")
        sys.exit(1)
    try:
        channel = validate_channel(channel)
    except AssertionError:
        usage()
        print("Channel must be one of stable, candidate, beta or edge")
        sys.exit(1)
    charm_dir = os.path.abspath(os.path.join(CUR_DIR, 'charms', charm_name))
    try:
        check_charm_dir_exists(charm_dir)
    except AssertionError:
        usage()
        print("\n!!! Charm dir {} doesn't exist".format(charm_dir))
        sys.exit(1)
    print("Charm: {}, adding/changing channel to {}"
          .format(charm_name, channel))
    dirs = find_bundles_dirs(os.path.join(CUR_DIR, 'charms', charm_name))
    bundles = find_bundles_in_dirs(dirs)
    charms = get_charms_list(CHARMS_FILE)
    update_bundles(charms, bundles, channel)
    print("done.")


if __name__ == '__main__':
    main()
