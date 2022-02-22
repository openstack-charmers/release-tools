#!/usr/bin/env python3

import logging
from pathlib import Path
import requests
import sys
from typing import List, Optional, Dict
import yaml

# from https://api.snapcraft.io/docs/charms.html
CHARMHUB_BASE = "https://api.charmhub.io/v2/charms"
INFO_URL = CHARMHUB_BASE + "/info/{charm}?fields=channel-map"


CUR_DIR = Path(__file__).parent.resolve()
CHARMS_FILE = CUR_DIR / 'charms.txt'
assert CHARMS_FILE.is_file(), f"{CHARMS_FILE} doesn't exist?"
OPERATOR_CHARMS_FILE = CUR_DIR / 'operator-charms.txt'
assert OPERATOR_CHARMS_FILE.is_file(), f"{OPERATOR_CHARMS_FILE} doesn't exist?"
LP_DIR = CUR_DIR / 'lp-builder-config'
assert LP_DIR.is_dir(), f"{LP_DIR} doesn't seem to exist?"


# type Alias for LpConfig struture.
LpConfig = Dict[str, Dict[str, List[str]]]


logger = logging.getLogger(__name__)


def get_lp_builder_config() -> LpConfig:
    """Fetch the lp builder configs for branch <-> channel maps.

    The lp-build-config/*.yaml files provide a mapping between a git branch and
    the resultant track/channel in the charmstore.  The return value is
    effectvely:

    {<charm-name>: {<branch-name>: [track/channel, ...]}}

    :returns: The charm <-> branch <-> track/channel mapping.
    """
    lp_config = {}
    for config_file in LP_DIR.glob('*.yaml'):
        lp_config.update(parse_lp_builder_config_file(config_file))
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
    """Decode the channel."""
    track = channel
    risk = 'stable'
    if '/' in channel:
        track, risk = channel.split('/', 2)
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


def main() -> None:
    config = get_lp_builder_config()
    print("charms", config.keys())
    print(f"Number of charms: {len(config.keys())}")
    for charm in config.keys():
        cr = INFO_URL.format(charm=charm)
        r = requests.get(cr)
        latest_stable = decode_channel_map(charm, r, 'latest/stable', '21.10')
        print(f"{charm} latest/stable revision: {latest_stable}")
        xena_edge = decode_channel_map(charm, r, 'xena/edge', None)
        print(f"{charm} xena/edge     revision: {xena_edge}")

if __name__ == '__main__':
    logging.basicConfig()
    main()
