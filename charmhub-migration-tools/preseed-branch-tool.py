#!/usr/bin/env python3

import argparse
import logging
from pathlib import (Path)
import requests
import subprocess
import sys
from typing import List, Optional, Dict
import yaml

# from https://api.snapcraft.io/docs/charms.html
CHARMHUB_BASE = "https://api.charmhub.io/v2/charms"
INFO_URL = CHARMHUB_BASE + "/info/{charm}?fields=channel-map"


CUR_DIR = Path(__file__).parent.resolve()
LP_DIR = CUR_DIR.parent / 'lp-builder-config'
assert LP_DIR.is_dir(), f"{LP_DIR} doesn't seem to exist?"


# type Alias for LpConfig struture.
LpConfig = Dict[str, Dict[str, List[str]]]


logger = logging.getLogger(__name__)


def get_lp_builder_config(file: Optional[Path] = None) -> LpConfig:
    """Fetch the lp builder configs for branch <-> channel maps.

    The lp-build-config/*.yaml files provide a mapping between a git branch and
    the resultant track/channel in the charmstore.  The return value is
    effectvely:

    {<charm-name>: {<branch-name>: [track/channel, ...]}}

    :param file: an optional file to only load specific charms
    :returns: The charm <-> branch <-> track/channel mapping.
    """
    lp_config = {}
    if file is None:
        for config_file in LP_DIR.glob('*.yaml'):
            lp_config.update(parse_lp_builder_config_file(config_file))
    else:
        lp_config.update(parse_lp_builder_config_file(file))
    return lp_config


def parse_lp_builder_config_file(config_file: Path) -> LpConfig:
    """Parse an lp builder config file into an LpConfig structure.

    :param config_file: the file to read.
    """
    try:
        with open(config_file) as f:
            raw_config = yaml.safe_load(f)
    except Exception as e:
        logging.error("Couldn't read config_file: %s due to: %s",
                      config_file, str(e))
        sys.exit(1)
    # load defaults if they exist
    try:
        default_branches = {
            k: v['channels']
            for k, v in raw_config['defaults']['branches'].items()}
    except KeyError:
        default_branches = {}
    # Now iterate through the config and add default branches if now branches
    # are specificed.
    lp_config: Dict[str, Dict[str, List[str]]] = {}
    try:
        for project in raw_config['projects']:
            try:
                branches = {
                    k: v['channels']
                    for k, v in project['branches'].items()}
            except KeyError:
                branches = default_branches.copy()
            lp_config[project['charmhub']] = branches
    except KeyError:
        # just ignore the file if there are no projects
        logging.warning('File %s contains no projects key?', config_file)
    return lp_config


def decode_channel_map(charm: str,
                       result: requests.Response,
                       channel: str,
                       version: Optional[str],
                       ) -> Optional[int]:
    """Decode the channel.

    """
    track = channel
    risk = 'stable'
    if '/' in channel:
        track, risk = channel.split('/', 2)
    # print(f"dump of result:\n{result.json()}")
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

        if ((version is None or base_channel == version) and
                (channel_track, channel_risk) == (track, risk)):
            print(f"{charm:<30} ({i:2}) -> {base_arch:6} {base_channel} "
                  f"r:{revision_num:3} "
                  f"{channel_track:>10}/{channel_risk:<10} -> [{arches_str}]")
            return revision_num

    return None


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse command line arguments.

    :param argv: List of configure functions functions
    :returns: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description=('Preseed a charm or charms.  Note that it takes the '
                     'latest version on 21.01 and preseeds to the tracks '
                     'specified for the charm is the revision is missing or '
                     'less than the preseed revision.'))
    parser.add_argument('--log', dest='loglevel',
                        type=str.upper,
                        default='INFO',
                        choices=('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'),
                        help='Loglevel')
    parser.add_argument('--charm', '-c',
                       dest='charms',
                       action='append',
                       metavar='CHARM',
                       type=str.lower,
                       help=('If present, adds a specific charm to fetch.  If '
                             'not present, then the section is used. If '
                             'neither the section nor charm(s) are available '
                             'then all the charms are fetched'))

    return parser.parse_args(argv)


def main() -> None:
    """Do the stuff.

    Note that this ignores resources; they'll need to be manually patched up.
    """
    args = parse_args(sys.argv[1:])
    logger.setLevel(getattr(logging, args.loglevel, 'INFO'))
    print(args)
    # config = get_lp_builder_config(LP_DIR / 'misc.yaml')
    config = get_lp_builder_config()
    charms = args.charms or []
    print("charms", charms)
    print(f"Number of charms: {len(charms)}")
    failures = []
    for charm, charm_config in config.items():
        if charm not in charms:
            continue
        print(f"{charm} - {charm_config}")
        cr = INFO_URL.format(charm=charm)
        r = requests.get(cr)
        latest_stable = decode_channel_map(charm, r, 'latest/stable', '21.10')
        print(f"{charm} latest/stable revision: {latest_stable}")
        if latest_stable is None:
            print(f"For '{charm}' there is not latest stable, skipping.")
            continue
        for branch, tracks in charm_config.items():
            if branch == 'master':
                print("Skipping master branch")
                continue
            for track in tracks:
                # latest_stable = decode_channel_map(charm, r, 'latest/stable', '21.10')
                # print(f"{charm} latest/stable revision: {latest_stable}")
                # xena_edge = decode_channel_map(charm, r, 'xena/edge', None)
                # print(f"{charm} xena/edge     revision: {xena_edge}")
                revision = decode_channel_map(charm, r, track, None)
                print(f"{charm}  {track}    current revision: {revision}")
                if revision != latest_stable:
                    print(f" -- Needs changing from {revision} -> "
                          f"{latest_stable}")
                    print(f"  -- Running: "
                          f" charmcraft release {charm} "
                          f"--revision={latest_stable} "
                          f"--channel={track}")
                    cmd = (f"charmcraft release {charm} "
                           f"--revision={latest_stable} "
                           f"--channel={track}")
                    try:
                        subprocess.check_call(cmd.split(' '))
                    except Exception as e:
                        print(f"Couldn't update {charm}, {track} to revision: "
                              f"{latest_stable}")
                        failures.append({'charm': charm,
                                         'track': track,
                                         'current_revision': revision,
                                         'target_revision': latest_stable})
                else:
                    print(" -- doesn't need changing.:")

    if failures:
        print("The following failed")
        for failure in failures:
            print(f"{failure['charm']} - {failure['track']}")


if __name__ == '__main__':
    logging.basicConfig()
    main()
