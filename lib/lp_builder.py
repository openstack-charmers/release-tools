import glob
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import yaml

try:
    from importlib_resources import files, as_file  # type: ignore
except ImportError:
    from importlib.resources import files, as_file  # type: ignore


"""Understanding the various configs.

The directory ../lp-builder-config/ contains `.yaml` files that describe
projects.  Each YAML file is a 'section' (e.g. openstack.yaml) that describes a
common set of charms that have the same kinds of branches - although this isn't
enforced.

A typical file looks like:

    # Miscellaneous Charms used for OpenStack
    defaults:
      team: openstack-charmers

    projects:
      - name: HA Cluster Charm
        charmhub: hacluster
        launchpad: charm-hacluster
        repository: https://opendev.org/openstack/charm-hacluster.git
        branches:
          master:
            channels:
              - latest/edge
          stable/focal:
            channels:
              - 2.0.3/edge
          stable/bionic:
            channels:
              - 1.1.18/edge

and:

    # OVN Charms
    defaults:
      team: openstack-charmers
      branches:
        master:
          channels:
            - latest/edge
        stable/20.03:
          channels:
            - openstack-ussuri/edge
            - openstack-victoria/edge
            - 20.03/edge
        stable/20.12:
          channels:
            - openstack-wallaby/edge
            - 20.12/edge
        stable/21.09:
          channels:
            - openstack-xena/edge
            - 21.09/edge

    projects:
      - name: OVN Central
        charmhub: ovn-central
        launchpad: charm-ovn-central
        repository: https://opendev.org/x/charm-ovn-central.git

The 'raw' configs pulled from the files are cached in the module global
_YAML_SECTIONS which is a `Dict[str, Any]`


This module also provides a class, called `Charm` that provides the data.  It
is a 'thin' wrapper, in that it has a "name", and then all the other 'fields'
just read into the _YAML_SECTIONS.  To get a charm definition, use `get_charm`
if the name is already known.  `get_charms` gets all the charms, or those by a
section.
"""

# type Alias for LpConfig struture.
# {<charm-name>: {<branch-name>: [track/channel, ...]}}
LpConfig = Dict[str, Dict[str, List[str]]]
# a mapping of the name "openstack" -> openstack config
YamlConfig = Dict[str, LpConfig]
# a mapping of section -> the raw config
RawConfig = Dict[str, Dict[str, Any]]

logger = logging.getLogger(__name__)


# cache the LP config as it's not going to change
_LP_CONFIG: Optional[LpConfig] = None
_YAML_CONFIG: YamlConfig = {}
_RAW_CONFIG: Optional[RawConfig] = None


class Charm:
    """Class to provide data for the charm.

    Provides convenient (and potentially type-safe) methods and properties for
    a charm.

    Note, causes parsing of the yaml files in the `LP_DIR` on first use.
    """

    def __init__(self, charmhub: str):
        """Initialise a charm config.

        :raises: Exception if couldn't find the charm or a config error occurs.
        """
        self._charmhub = charmhub
        self._config = find_config_for(charmhub)

    @property
    def charmhub(self) -> str:
        """Returns the charmhub name of the charm.

        This is the 'name' parameter in the config for the charm.

        :returns: the name of the charm.
        """
        return self._charmhub

    @property
    def name(self) -> str:
        """Returns the name of the charm as a friendly name.

        This is the 'name' parameter in the config for the charm.

        :returns: the name of the charm.
        """
        return self._config['name']

    @property
    def section(self) -> str:
        """Returns the section of the charm.

        This is the stem of the yaml file name, excluding the .yaml suffix.

        :returns: the section of the charm.
        """
        return self._config['section']

    @property
    def launchpad(self) -> str:
        """Returns the launchpad name of the charm.

        :returns: the launchpad name of the charm.
        """
        return self._config['launchpad']

    @property
    def repository(self) -> str:
        """Returns the repository of the charm.

        :returns: the repository URL of the charm.
        """
        return self._config['repository']

    @property
    def raw_branches(self) -> Dict[str, Dict[str, Dict[str, List[str]]]]:
        """Returns the raw branches for the charm.

        e.g.

          branches:
            master:
              channels:
                - latest/edge
            stable/20.03:
              channels:
                - openstack-ussuri/edge
                - openstack-victoria/edge
                - 20.03/edge

        :returns: the repository URL of the charm.
        """
        return self._config['branches'].copy()

    @property
    def branches(self) -> List[str]:
        """Get the list of branches for the charm."""
        try:
            return list(self._config['branches'].keys())
        except KeyError:
            return []

    def channels_for(self, branch: str) -> List[str]:
        """Get the tracks/channels for a particular branch."""
        try:
            channels = self.branches[branch]
            return channels['channels']
        except KeyError:
            return []


def find_config_for(charmhub: str) -> Dict[str, Any]:
    """Find the :param:`charmhub` name in the raw configs.

    It returns the config for that charm, including the default branches.  The
    format is:

        name: OVN Central
        charmhub: ovn-central
        launchpad: charm-ovn-central
        repository: https://opendev.org/x/charm-ovn-central.git
          branches:
            master:
              channels:
                - latest/edge
            stable/20.03:
              channels:
                - openstack-ussuri/edge
                - openstack-victoria/edge
                - 20.03/edge

    as a Python dictionary.

    :returns: Project config
    :raises: KeyError if the charm couldn't be found.
    :raises: Exception if the config couldn't be read.
    """
    raw_config = get_yaml_config()
    for section, section_config in raw_config.items():
        for project in section_config['projects']:
            if project['charmhub'] == charmhub:
                # we've found the charm; now get the correct branches onto it.
                project_config = project.copy()
                if 'branches' not in project:
                    try:
                        project_config['branches'] = \
                            section_config['defaults']['branches']
                    except KeyError:
                        logging.warning(f"No branches or default branches for "
                                        f"charmhub: {charmhub}")
                if 'team' not in project:
                    try:
                        project_config['team'] = \
                            section_config['defaults']['team']
                    except KeyError:
                        logging.warning(f"No team or default team for "
                                        f"charmhub: {charmhub}")
                project_config['section'] = section
                return project_config
    raise KeyError(f"Couldn't find {charmhub} in the config.")


def get_charms(section: str) -> List[Charm]:
    """Get all the charm names, optionally restricting to a section.

    :returns: the list of charm names.
    :raises: Exception if couldn't read the config.
    """
    assert section is not None
    raw_config = get_yaml_config()
    charms: List[Charm] = []
    for _section, section_config in raw_config.items():
        if section != ":all:" and _section != section:
            continue
        for project in section_config['projects']:
            charms.append(Charm(project['charmhub']))
    return charms


### TODO: OLD - needs refactoring into using new config


def get_lp_builder_config() -> LpConfig:
    """Fetch the lp builder configs for branch <-> channel maps.

    The lp-build-config/*.yaml files provide a mapping between a git branch and
    the resultant track/channel in the charmstore.  The return value is
    effectvely:

    {<charm-name>: {<branch-name>: [track/channel, ...]}}

    :returns: The charm <-> branch <-> track/channel mapping.
    """
    global _LP_CONFIG
    if _LP_CONFIG is not None:
        return _LP_CONFIG.copy()
    lp_config = {}
    config_dir = files('charmed_openstack_info.data.lp-builder-config')
    with as_file(config_dir) as cfg_dir:
        for config_file in glob.glob(f'{cfg_dir}/*.yaml'):
            lp_config.update(parse_lp_builder_config_file(Path(config_file)))
    _LP_CONFIG = lp_config
    return lp_config.copy()


def sections() -> List[str]:
    """Return the section names available.

    :returns: List of section names.
    """
    config_dir = files('charmed_openstack_info.data.lp-builder-config')
    with as_file(config_dir) as cfg_dir:
        return list(Path(name).stem for name in glob.glob(f'{cfg_dir}/*.yaml'))


def get_lp_builder_config_for(name: str) -> LpConfig:
    """Fetch the lp config fo a specific name.

    :returns: The cham <-> branch <-> track/channel mapping.
    """
    global _YAML_CONFIG
    try:
        return _YAML_CONFIG[name]
    except KeyError:
        pass
    get_lp_builder_config()
    return _YAML_CONFIG[name]


def get_yaml_config() -> RawConfig:
    """Get the yaml config.

    Reads the entire config from the .yaml files on first use.

    :returns: the entire config for all of the files, split by section.
    :raises: Exception if the config file couldn't be read.
    """
    global _RAW_CONFIG
    if _RAW_CONFIG is not None:
        return _RAW_CONFIG.copy()
    _RAW_CONFIG = {}
    config_dir = files('charmed_openstack_info.data.lp-builder-config')
    with as_file(config_dir) as cfg_dir:
        for config_file in glob.glob(f'{cfg_dir}/*.yaml'):
            name = Path(config_file).stem
            try:
                with open(config_file) as f:
                    raw_config = yaml.safe_load(f)
            except Exception as e:
                logging.error("Couldn't read config_file: %s due to: %s",
                              config_file, str(e))
                raise
            _RAW_CONFIG[name] = raw_config
    return _RAW_CONFIG.copy()


def parse_lp_builder_config_file(config_file: Path) -> LpConfig:
    """Parse an lp builder config file into an LpConfig structure.

    :param config_file: the file to read.
    """
    global _YAML_CONFIG
    name: str = config_file.stem
    try:
        return _YAML_CONFIG[name]
    except KeyError:
        pass
    try:
        with open(config_file) as f:
            raw_config = yaml.safe_load(f)
    except Exception as e:
        logging.error("Couldn't read config_file: %s due to: %s",
                      config_file, str(e))
        raise
    # load defaults if they exist
    try:
        default_branches = {
            k: v['channels']
            for k, v in raw_config['defaults']['branches'].items()}
    except KeyError:
        default_branches = {}
    # Now iterate through the config and add default branches if now branches
    # are specificed.
    lp_config: LpConfig = {}
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
    _YAML_CONFIG[name] = lp_config
    return lp_config
