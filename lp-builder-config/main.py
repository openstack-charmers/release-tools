#
# Copyright 2021, Canonical
#

"""Tools to configure and manage repositories and launchpad builders.

This file contains a command that provides the ability to configure and manage
the launchpad builders, repositories and branches in repositories.

The commands are:
   show -> display the current config.
   list -> show a list of the charms configured in the supplied config.
   diff -> show the current config and a diff to what is asked for.
   config -> show the asked for config
   sync -> sync the asked for config to the charm in the form of recipes.

Note that 'update' requires the --i-really-mean-this flag as it is potentially
destructive.  'update' also has other flags.

As always, use the -h|--help on the command to discover what the options are
and how to manage it.

"""

import argparse
import collections
import logging
import os
import io
import pathlib
import pprint
import sys
from typing import (Any, Dict, Iterator, List, Tuple, Optional)
import yaml

from launchpadtools import (
    LaunchpadTools,
    TypeLPObject,
    setup_logging as lpt_setup_logging,
)
from charm_project import (
    CharmProject,
    setup_logging as cp_setup_logging,
)


logger = logging.getLogger(__name__)

CWD = os.path.dirname(os.path.realpath(__file__))


def check_config_dir_exists(dir_: pathlib.Path) -> None:
    """Validate that the config dir_ exists.

    Raises FileNotFoundError if it doesn't.

    :param dir_: the config path that needs to exist.
    :raises: FileNotFoundError if the configuration directory doesn't exist.
    """
    if not dir_.exists():
        raise FileNotFoundError(
            f'Configuration directory "{dir_}" does not exist')
    return dir_


def get_group_config_filenames(config_dir: pathlib.Path,
                               project_group_names: Optional[List[str]] = None,
                               extension: str = ".yaml",
                               ) -> List[pathlib.Path]:
    """Fetch the list of files for the group config.

    Depending on whether :param:`project_group_names` is passed, get the list
    of files that contain the projects that need configuring.

    :param config_dir: the directory to look in
    :param project_group_names: Optional list of names to filter on.
    :param extension: the extension (default '.yaml') to use for the
        project_group_names
    :returns: the list of paths corresponding to the files.
    :raises: FileNotFoundError if a name.extension in the config_dir doesn't
        exist.
    """
    # Load the various project group configurations
    if not project_group_names:
        files = list(config_dir.glob('*.yaml'))
    else:
        files = [config_dir / f'{group}.yaml' for group in project_group_names]
        # validate that the files actually exist
        for file in files:
            if not(file.exists()):
                raise FileNotFoundError(
                    f"The group config file '{file}' wasn't found")
    return files


class GroupConfig:
    """Collect together all the config files and build CharmProject objects.

    This collects together the files passed (which define a charm projects
    config and creates CharmProject objects to ensure git repositories and
    ensure that the charm builder recipes in launchpad exist with the correct
    settings.
    """

    def __init__(self,
                 lpt: 'LaunchpadTools',
                 files: List[pathlib.Path] = None) -> None:
        """Configure the GroupConfig object.

        :param files: the list of files to load config from.
        """
        self.lpt = lpt
        self.charm_projects: Dict[str, 'CharmProject'] = (
            collections.OrderedDict())
        if files is not None:
            self.load_files(files)

    def load_files(self, files: List[pathlib.Path] = None) -> None:
        """Load the files into the object.

        This loads the files, and configures the projects and then creates
        CharmProject objects.

        :param files: the list of files to load config from.
        """
        assert not(isinstance(files, str)), "param files must not be str"
        assert isinstance(files, collections.abc.Sequence), \
            "Must pass a list or tuple."
        for file in files:
            with open(file, 'r') as f:
                group_config = yaml.safe_load(f)
            logger.debug('group_config is: \n%s', pprint.pformat(group_config))
            project_defaults = group_config.get('defaults', {})
            for project in group_config.get('projects', []):
                for key, value in project_defaults.items():
                    project.setdefault(key, value)
                logger.debug('Loaded project %s', project.get('name'))
                self.add_charm_project(project)

    def add_charm_project(self,
                          project_config: Dict[str, Any],
                          merge: bool = False,
                          ) -> None:
        """Add a CharmProject object from the project specification dict.

        :param project: the project to add.
        :param merge: if merge is True, merge/overwrite the existing object.
        :raises: ValueError if merge is false and the charm project already
            exists.
        """
        name = project_config.get('name')
        if name in self.charm_projects:
            if merge:
                self.charm_projects[name].merge(project_config)
            else:
                raise ValueError(
                    f"Project config for '{name}' already exists.")
        else:
            self.charm_projects[name] = CharmProject(project_config, self.lpt)

    def projects(self, select: Optional[List[str]]) -> Iterator[CharmProject]:
        """Generator returns a list of projects."""
        if not(select):
            select = None
        for project in self.charm_projects.values():
            if select is None or project.name in select:
                yield project


def parse_args() -> argparse.Namespace:
    """Parse the arguments and return the parsed args.

    Work out what command is being run and collect the arguments
    associated with it.

    :param pargs: the sys.argv set.
    :returns: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Configure launchpad projects for charms'
    )
    default_config_dir = os.path.abspath(os.path.join(CWD, './config'))
    parser.add_argument('--config-dir',
                        type=str, default=default_config_dir,
                        help='directory containing configuration files')
    parser.add_argument('--log', dest='loglevel',
                        type=str.upper,
                        default='ERROR',
                        choices=('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'),
                        help='Loglevel')
    parser.add_argument('-p', '--group',
                        dest='project_groups',
                        action='append',
                        metavar='PROJECT-GROUP',
                        # type=str, nargs='*',
                        type=str,
                        help='Project group configurations to process. If no '
                             'project groups are specified, all project '
                             'groups found in the config-dir will be loaded '
                             'and processed.')
    parser.add_argument('-c', '--charm',
                        dest='charms',
                        action='append',
                        metavar='CHARM',
                        type=str,
                        help=('Choose a specific charm name from the '
                              'configured set. May be repeated for multiple '
                              'charms.'))

    subparser = parser.add_subparsers(required=True, dest='cmd')
    show_command = subparser.add_parser(
        'show',
        help=('The "show" command shows the current configuration for the '
              'charm recipes as defined in launchpad.'))
    show_command.set_defaults(func=show_main)
    list_command = subparser.add_parser(
        'list',
        help='List the charms defined in the configuration passed.')
    list_command.set_defaults(func=list_main)
    diff_command = subparser.add_parser(
        'diff',
        help=('Diff the declared config with the actual config in launchpad. '
              'This shows the config and high-lights missing or extra '
              'configuration that is in launchpad. Note that git repositories '
              'can have extra branches and these are not seen in the diff. '
              'Missing branches that are in the config are highlighted.'))
    diff_command.set_defaults(func=diff_main)
    diff_command.add_argument('--detail',
                              action='store_true',
                              default=False,
                              help="Add detail to the output.")
    sync_command = subparser.add_parser(
        'sync',
        help=('Sync the config to launchpad. Effectively, this takes the diff '
              'and applies it to the projects, creating or updating recipes '
              'as required.'))
    sync_command.add_argument(
        '--i-really-mean-it',
        dest='confirmed',
        action='store_true',
        default=False,
        help=('This flag must be supplied to indicate that the sync/apply '
              'command really should be used.'))
    sync_command.set_defaults(func=sync_main)

    args = parser.parse_args()
    return args


def show_main(args: argparse.Namespace,
              gc: GroupConfig,
              ) -> None:
    """Show a the charm config in launchpad, if any for the group config.

    :param args: the arguments parsed from the command line.
    :para gc: The GroupConfig; i.e. all the charms and their config.
    """
    for cp in gc.projects(select=args.charms):
        cp.show_lauchpad_config()


def list_main(args: argparse.Namespace,
              gc: GroupConfig,
              ) -> None:
    """List the charm projects (and repos) that are in the configuration.

    This simply lists the charm projects in the GlobalConfig.

    :param args: the arguments parsed from the command line.
    :para gc: The GroupConfig; i.e. all the charms and their config.
    """
    def _heading():
        print(f"{'-'*20} {'-'*30} {'-'*40} {'-'*len('Repository')}")
        print(f"{'Team':20} {'Charmhub name':30} {'LP Project Name':40} "
              f"{'Repository'}")
        print(f"{'-'*20} {'-'*30} {'-'*40} {'-'*len('Repository')}")

    for i, cp in enumerate(gc.projects(select=args.charms)):
        if i % 30 == 0:
            _heading()
        print(f"{cp.team:20} {cp.charmhub_name[:30]:30} "
              f"{cp.launchpad_project[:40]:40} {cp.repository}")


def diff_main(args: argparse.Namespace,
              gc: GroupConfig,
              ) -> None:
    """Show a diff between the requested LP config and current config.

    :param args: the arguments parsed from the command line.
    :para gc: The GroupConfig; i.e. all the charms and their config.
    """
    for cp in gc.projects(select=args.charms):
        cp.print_diff(args.detail)


def sync_main(args: argparse.Namespace,
              gc: GroupConfig,
              ) -> None:
    """Do the sync from the config to the projects defined in config.

    This takes the GroupConfig and then ensures that the git repository is set
    up in launchpad for each project, and then ensures that the required charm
    recipes are sdet up for that project in launchpad.

    :param args: the arguments parsed from the command line.
    :para gc: The GroupConfig; i.e. all the charms and their config.
    """
    if not args.confirmed:
        raise AssertionError(
            "'sync' command issues, but --i-really-mean-it flag not used. "
            "Abandoning.")
    for charm_project in gc.projects(select=args.charms):
        charm_project.ensure_git_repository()
        charm_project.ensure_charm_recipes()


def setup_logging(loglevel: str) -> None:
    """Sets up some basic logging."""
    logging.basicConfig()
    logger.setLevel(getattr(logging, loglevel, 'ERROR'))
    cp_setup_logging(loglevel)
    lpt_setup_logging(loglevel)


def main():
    """Main entry point."""
    args = parse_args()
    setup_logging(args.loglevel)

    logging.info('Using config dir %s', args.config_dir)

    config_dir = check_config_dir_exists(
        pathlib.Path(os.fspath(args.config_dir)))

    # # Load the various project group configurations
    files = get_group_config_filenames(config_dir,
                                       args.project_groups)

    lpt = LaunchpadTools()

    gc = GroupConfig(lpt)
    gc.load_files(files)

    # Call the function associated with the sub-command.
    args.func(args, gc)


if __name__ == '__main__':
    try:
        main()
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except AssertionError as e:
        logger.error(str(e))
        sys.exit(1)
