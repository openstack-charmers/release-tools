#
# Copyright 2021, Canonical
#

import argparse
import collections
import logging
import os
import pathlib
import pprint
import sys
from typing import (Any, Dict, Iterator, List, Tuple, Optional)
import yaml

from launchpadlib.uris import lookup_service_root
from launchpadlib.launchpad import Launchpad


logger = logging.getLogger(__name__)

CWD = os.path.dirname(os.path.realpath(__file__))


class CharmProject:
    """Represents a CharmProject.

    The CharmProject is defined in a yaml file and has the following form:

    name: the human friendly name of the project
    charmhub: the charmhub store name
    launchpad: the launchpad project name
    team: the team who should own the branches and charm recipes
    repo: a URL to the upstream repository to be mirrored in
          launchpad
    branches: a list of branch -> recipe_info mappings for charm recipes on
            launchpad.

    The branch_info dictionary consists of the following keys:

      * channels (optional) - a list of fully qualified channel names to
          publish the charm to after building.
      * build-path (optional) - subdirectory within the branch containing
          metadata.yaml
      * recipe-name (optional) - A string used to format the name of the
          recipe. The project name will be passed as 'project', the branch
          name will be passed as 'branch', and the track name will be passed
          as 'track'. The default recipe-name is '{project}.{branch}.{track}'.
      * auto-build (optional) - a boolean indicating whether to automatically
          build the charm when the branch changes. Default value is True.
      * upload (optional) - a boolean indicating whether to upload to the store
          after a charm is built. Default value is True.
      * build-channels (optional) - a dictionary indicating which channels
          should be used by the launchpad builder for building charms. The
          key is the name of the snap or base and the value is the full
          channel identifier (e.g. latest/edge). Currently, Launchpad accepts
          the following keys: charmcraft, core, core18, core20 and core22.

    The following examples provide information for various scenarios.

    The following example uses all launchpad builder charm_recipe defaults
    publishes the main branch to the latest/edge channel and the stable
    branch to the latest/stable channel:

    name: Awesome Charm
    charmhub: awesome
    launchpad: charm-awesome
    team: awesome-charmers
    repo: https://github.com/canonical/charm-awesome-operator
    branches:
      main:
        channels: latest/edge
      stable:
        channels: latest/stable

    The following example builds a charm using the latest/edge channel of
    charmcraft, and does not upload the results to the store

    name: Awesome Charm
    charmhub: awesome
    launchpad: charm-awesome
    team: awesome-charmers
    repo: https://github.com/canonical/charm-awesome-operator
    branches:
      main:
        store-upload: False
        build-channels:
          charmcraft: latest/edge

    The following example builds a charm on the main branch of the git
    repository and publishes the results to the yoga/edge and latest/edge
    channels and builds a charm on the stable/xena branch of the git
    repository and publishes the results to xena/edge.

    name: Awesome Charm
    charmhub: awesome
    launchpad: charm-awesome
    team: awesome-charmers
    repo: https://github.com/canonical/charm-awesome-operator
    branches:
      main:
        channels:
          - yoga/edge
          - latest/edge
      stable/xena:
        channels:
          - xena/edge
    """

    def __init__(self, config):
        self.name: str = config.get('name')
        self.team: str = config.get('team')
        self.charmhub_name: str = config.get('charmhub')
        self.launchpad_project: str = config.get('launchpad')
        self.repository: str = config.get('repository')

        self.branches: Dict[str, str] = {}

        self._add_branches(config.get('branches', {}))

    def _add_branches(self, branches_spec: Dict[str, str]) -> None:
        default_branch_info = {
            'auto-build': True,
            'upload': True,
            'recipe-name': '{project}.{branch}.{track}'
        }
        for branch, branch_info in branches_spec.items():
            ref = f'refs/heads/{branch}'
            if ref not in self.branches:
                self.branches[ref] = dict(default_branch_info)
            if type(branch_info) != dict:
                raise ValueError('Expected a dict for key branches, '
                                 f' instead got {type(branch_info)}')

            self.branches[ref].update(branch_info)

    def merge(self, config: Dict[str, Any]) -> None:
        """Merge config, by overwriting."""
        self.name = config.get('name', self.name)
        self.team = config.get('team', self.team)
        self.charmhub_name = config.get('charmhub', self.charmhub_name)
        self.launchpad_project = config.get('launchpad',
                                            self.launchpad_project)
        self.repository = config.get('repository', self.repository)
        self._add_branches(config.get('branches', {}))

    def __repr__(self):
        return (f"CharmProject(name={self.name}, team={self.team}, "
                f"charmhub_name={self.charmhub_name}, "
                f"launchpad_project={self.launchpad_project},"
                f"repository={self.repository}, "
                f"branches={self.branches})")

    def __str__(self):
        branches = []
        width = 20
        for branch, spec in self.branches.items():
            if branch.startswith("refs/heads/"):
                bname = branch[len("refs/heads/"):]
            else:
                bname = branch
            channels = ", ".join(spec['channels'])
            branches.append(f"{bname} -> {channels}")
        if branches:
            branches_str = f"{'branches':>{width}}: {branches[0]}"
            for br in branches[1:]:
                branches_str += f"\n{':':>{width+1}} {br}"

        return (f"CharmProject:\n"
                f"{'name':>{width}}: {self.name}\n"
                f"{'team':>{width}}: {self.team}\n"
                f"{'charmhub_name':>{width}}: {self.charmhub_name}\n"
                f"{'launchpad_project':>{width}}: {self.launchpad_project}\n"
                f"{'repository':>{width}}: {self.repository}\n"
                + branches_str)


class LaunchpadTools:

    def __init__(self):
        self.lp = Launchpad.login_with(
            'openstack-charm-tools',
            service_root=lookup_service_root('production'),
            version='devel',
            credential_save_failed=self.no_credential,
        )

    @staticmethod
    def no_credential():
        logging.error("Couldn't save/store the Launchpad credential")
        sys.exit(1)

    def get_git_repository(self, owner: 'team', project: 'project'):
        """Returns the reference to the Launchpad git repository by owner and
        project.

        Return the first reference to a Launchpad git repository which is
        owned by the specified owner for the given project. If multiple
        repositories are found, only the first repository will be returned.
        If no repositories are found, then None will be returned.

        :param owner: the team or person who owns the specified project
        :type owner: a launchpad team
        :param project: the launchpad project to get the git repository for
        :type project: a launchpad project
        :return: the Launchpad git repository for the project
        """
        logger.debug('Fetching git repositories for target=%s, owner: %s',
                     project.name, owner)
        return next(
            filter(lambda r: r.owner == owner,
                   self.lp.git_repositories.getRepositories(target=project)),
            None
        )

    def import_repository(self, owner: 'team', project: 'project',
                          url: str) -> 'repository':
        """Creates a repository in Launchpad imported from the specified url
        belonging to the specified owner and project.

        :param owner: the owner of the repository
        :type owner: a launchpad team
        :param project: the project for the repository
        :type project: a launchpad project
        :param url: the url to the repository to import from
        :type url: str
        :returns: the reference to the Launchpad git repository
        """
        logger.info('Importing git repository from %s into project '
                    '%s for user %s',
                    url, project.name, owner.name)
        code_import = project.newCodeImport(
            owner=owner, rcs_type='Git', target_rcs_type='Git',
            url=url, branch_name=project.name
        )
        return code_import.git_repository

    def ensure_git_repository(self, charm: CharmProject
                              ) -> 'git_repository':
        """Ensure that launchpad project git repositorie exists.

        Configures launchpad project repositories for the specified charm
        project. This function will validate that a git repository is
        configured in launchpad to import the git tree from the upstream
        project repository and that the git repository is set as the default
        code repository for the launchpad project.

        :param charm: the charm project
        :return: the configured git_repository for the project
        :rtype: launchpad git_repository object
        """
        logger.info('Checking Launchpad git repositories for %s.',
                    charm.name)
        team = self.lp.people[charm.team]
        project = self.lp.projects[charm.launchpad_project]

        if project.owner != team:
            logger.error('Project owner of project %s '
                         'does not match owner specified %s',
                         charm.launchpad_project, charm.team)
            raise ValueError('Unexpected project owner for '
                             f'{charm.launchpad_project}')

        repo = self.get_git_repository(team, project)

        if repo is None:
            logger.info('Git repository for project %s and '
                        '%s does not exist, importing now from %s',
                        project.name, team.name, charm.repository)
            repo = self.import_repository(team, project, charm.repository)
        else:
            logger.debug('Git repository for project %s and '
                         '%s already exists.', project.name, team.name)

        # Check whether the repository is the default repository for the
        # project or not.
        if not repo.target_default:
            logger.info('Setting default repository for %s to %s',
                        project.name, repo.git_https_url)
            try:
                self.lp.git_repositories.setDefaultRepository(target=project,
                                                              repository=repo)
                repo.lp_refresh()
            except:  # no-qa
                # Log the error, but don't fail if we couldn't set the
                # default repository. Typically means the team is not the
                # owner of the project.
                logger.error('Failed to set the default repository for '
                             '%s to %s', project.name, rep.git_https_url)

        if not project.vcs:
            logger.info('Setting project %s vcs to Git', project.name)
            project.vcs = 'Git'
            project.lp_save()

        return repo

    def get_charm_recipes(self, owner: 'team', project: 'project'
                          ) -> List['charm_recipes']:
        """Returns charm recipes for the specified owner in the specified
        project.

        Returns all charm recipes owned by the specified owner for the given
        project. Note, this is necessary as Launchpad does not have an API
        for filtering by owner and project.

        :param owner: the owner of the charm recipe
        :type owner: team
        :param project: the launchpad project the charm recipe
        :type project: project
        :return: list of the configured charm recipes
        :rtype: list
        """
        logger.info('Fetching charm recipes for target=%s', project.name)
        recipes = list(
            filter(lambda r: r.project == project,
                   self.lp.charm_recipes.findByOwner(owner=owner))
        )
        logger.debug(" -- found recipes:\n%s",
                     "\n".join(f"  - {r.name}" for r in recipes))
        return recipes

    def update_charm_recipe(self, recipe: 'charm_recipe', branch_info: dict
                            ) -> bool:
        """Updates the charm_recipe to match the requested configuration in
        the track_info.

        :param recipe: the charm recipe to update
        :param branch_info: the branch_info dictionary containing information
                           for the recipe
        :return: True if updated, False otherwise
        """
        logger.info('Recipe exists; checking to see if "%s" for '
                    '%s needs updating.',
                     recipe.name, recipe.project.name)
        changed = []

        # (recipe, (params for branch_info.get()))
        parts = (('auto_build', ('auto-build',)),
                 ('auto_build_channels', ('build-channels',)),
                 ('build_path', ('build_path', None)),
                 ('store_channels', ('tracks', [])),
                 ('store_upload', ('upload',)),
                 )

        for (rpart, bpart) in parts:
            battr = branch_info.get(*bpart)
            rattr = getattr(recipe, rpart)
            logger.debug("rpart: '%s', bpart: '%s', recipe.%s is %s, want %s",
                         rpart, bpart, rpart, rattr, battr)
            if rattr != battr:
                setattr(recipe, rpart, battr)
                changed.append(f"recipe.{rpart} = {battr}")

        if changed:
            logger.info('Charm recipe %s has changes. Saving.', recipe.name)
            logger.debug("Changes: {}".format(", ".join(changed)))
            recipe.lp_save()
        else:
            logger.info('No changes needed for charm recipe %s', recipe.name)

        return changed

    def create_charm_recipe(self,
                            recipe_name: str,
                            branch_info: dict,
                            lp_branch: str,
                            owner: str,
                            project: str,
                            store_name: str,
                            channels: List[str],
                            ) -> None:
        """Create a new charm recipe using the branch_info and channels.

        The channels are a grouping of same track, different risks.
        e.g.
        ['latest/edge', 'latest/stable']

        :param recipe: the name of the recipe to create
        :param branch_info: a dictionary of relevant parts to create the recipe
        :param channels: a list of channels to target in the charmhub
        """
        logger.info('Creating charm recipe for %s', recipe_name)
        logger.debug(f'branch_info: %s', branch_info)
        upload = branch_info.get('upload', True)
        recipe_args = {
            'auto_build': branch_info.get('auto-build', True),
            'git_ref': lp_branch,
            'name': recipe_name,
            'owner': owner,
            'project': project,
            'store_name': store_name,
            'store_upload': upload,
        }
        if upload and channels:
            recipe_args['store_channels'] = channels
        try:
            recipe_args['auto_build_channels'] = branch_info['build-channels']
        except KeyError:
            pass
        logger.debug("Creating recipe with the following args: %s",
                     recipe_args)
        recipe = self.lp.charm_recipes.new(**recipe_args)
        logger.info('Created charm recipe %s', recipe.name)

    @staticmethod
    def group_channels(channels: List[str]
                       ) -> List[Tuple[str, List[str]]]:
        """Group channels into compatible lists.

        The charmhub appears to only allow a recipe to target a single channel,
        but with multiple levels of risk and/or 'branches'.  The specs for
        channels are either 'latest' or 'latest/<risk>'.  In this case, the
        grouping would be
        [('latest', ['latest', 'latest/edge', 'latest/stable']),]

        :param channels: a list of channels to target in the charmhub
        :returns: the channels, grouped by track.
        """
        groups = collections.OrderedDict()
        for channel in channels:
            if '/' in channel:
                group, _ = channel.split('/', 1)
            else:
                group = channel
            try:
                groups[group].append(channel)
            except KeyError:
                groups[group] = [channel]
        return list(groups.items())

    def ensure_charm_recipes(self, charm: CharmProject) -> None:
        """Ensure charm recipes in Launchpad matches CharmProject's conf.

        :param charm: the charm project to create charm recipes for.
        """
        logger.info('Checking charm recipes for charm %s', charm.name)
        logger.debug(str(charm))
        team = self.lp.people[charm.team]
        project = self.lp.projects[charm.launchpad_project]

        repository = self.get_git_repository(team, project)
        if not repository:
            logger.error('Unable to find repository for team %s and '
                         'project %s', team.name, project.name)
            raise ValueError(f'Unable to find repository for team {team.name} '
                             f'and project {project.name}')

        lp_recipes = self.get_charm_recipes(team, project)
        charm_recipes = {recipe.name: recipe for recipe in lp_recipes}
        for lp_branch in repository.branches:
            branch_info = charm.branches.get(lp_branch.path, None)
            if not branch_info:
                logger.info('No tracks configured for branch %s, continuing.',
                            lp_branch.path)
                continue

            # Strip off refs/head/. And no / allowed, so we'll replace with _
            branch_name = lp_branch.path[len('refs/heads/'):].replace('/', '-')
            recipe_format = branch_info.get('recipe-name')
            upload = branch_info.get('upload', True)
            # Get the channels; we have to do a separate recipe for each
            # channel that doesn't share the same track.  Reminder: channels
            # are <track>/<risk>
            channels = branch_info.get('channels', None)
            if upload and channels:
                tracks = self.group_channels(channels)
            else:
                tracks = (("latest", []),)
            for track, track_channels in tracks:
                recipe_name = recipe_format.format(
                    project=project.name, branch=branch_name, track=track)

                recipe = charm_recipes.pop(recipe_name, None)
                if recipe:
                    binfo = branch_info.copy()
                    binfo['tracks'] = track_channels
                    self.update_charm_recipe(recipe, binfo)
                else:
                    self.create_charm_recipe(
                        recipe_name=recipe_name,
                        branch_info=branch_info,
                        lp_branch=lp_branch,
                        owner=team,
                        project=project,
                        store_name=charm.charmhub_name,
                        channels=track_channels)

        # TODO (wolsen) Check to see if there are any remaining charm_recipes
        #  configured in Launchpad and remove them (?). Remaining charm_recipes
        #  will be those left in the charm_recipes dict. Not doing this
        #  currently as its not clear that we want to remove them automatically
        #  (yet).


def setup_logging(loglevel: str) -> None:
    """Sets up some basic logging."""
    logging.basicConfig()
    logger.setLevel(getattr(logging, loglevel, 'INFO'))


def parse_args(pargs: sys.argv) -> argparse.Namespace:
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
    parser.add_argument('-c', '--config-dir',
                        type=str, default=default_config_dir,
                        help='directory containing configuration files')
    parser.add_argument('--log', dest='loglevel',
                        type=str.upper,
                        default='INFO',
                        choices=('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'),
                        help='Loglevel')
    parser.add_argument('project_groups', metavar='project_group',
                        type=str, nargs='*',
                        help='Project group configurations to process. If no '
                             'project groups are specified, all project '
                             'groups found in the config-dir will be loaded '
                             'and processed.')
    args = parser.parse_args(pargs[1:])
    return args


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
                               extension: str =".yaml",
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

    def __init__(self, files: List[pathlib.Path] = None) -> None:
        """Configure the GroupConfig object.

        :param files: the list of files to load config from.
        """
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
            self.charm_projects[name] = CharmProject(project_config)

    def projects(self) -> Iterator[CharmProject]:
        """Generator returns a list of projects."""
        for project in self.charm_projects.values():
            yield project


def main():
    """Main entry point."""
    args = parse_args(sys.argv)
    setup_logging(args.loglevel)

    logging.info('Using config dir %s', args.config_dir)

    config_dir = check_config_dir_exists(
        pathlib.Path(os.fspath(args.config_dir)))

    # # Load the various project group configurations
    files = get_group_config_filenames(config_dir,
                                       args.project_groups)

    lp = LaunchpadTools()

    gc = GroupConfig()
    gc.load_files(files)

    for charm_project in gc.projects():
        lp.ensure_git_repository(charm_project)
        lp.ensure_charm_recipes(charm_project)


if __name__ == '__main__':
    try:
        main()
    except FileNotFoundError as e:
        logging.error(str(e))
        sys.exit(1)
    except Exception as e:
        raise
