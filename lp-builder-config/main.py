#
# Copyright 2021, Canonical
#

import argparse
import logging
import os
import pathlib
import sys
import typing
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
          as 'track'. The default recipe-name is '{project}-{branch}-{track}'.
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
        self.name = config.get('name')
        self.team = config.get('team')
        self.charmhub_name = config.get('charmhub')
        self.launchpad_project = config.get('launchpad')
        self.repository = config.get('repository')

        self.branches = {}
        default_branch_info = {
            'auto-build': True,
            'upload': True,
            'recipe-name': '{project}-{branch}'
        }
        for branch, branch_info in config.get('branches', {}).items():
            ref = f'refs/head/{branch}'
            self.branches[ref] = dict(default_branch_info)
            if type(branch_info) != dict:
                raise ValueError('Expected a dict for key branches, '
                                 f' instead got {type(branch_info)}')

            self.branches[ref].update(branch_info)


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
        logger.debug(f'Fetching git repositories for target={project.name}')
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
        logger.debug(f'Importing git repository from {url} into project '
                     f'{project.name} for user {owner.name}')
        code_import = project.newCodeImport(
            owner=owner, rcs_type='Git', target_rcs_type='Git',
            url=url, branch_name=project.name
        )
        return code_import.git_repository

    def configure_git_repository(self, charm: CharmProject) \
            -> 'git_repository':
        """Configures launchpad project git repositories.

        Configures launchpad project repositories for the specified charm
        project. This function will validate that a git repository is
        configured in launchpad to import the git tree from the upstream
        project repository and that the git repository is set as the default
        code repository for the launchpad project.

        :param charm: the charm project
        :return: the configured git_repository for the project
        :rtype: launchpad git_repository object
        """
        logger.debug(f'Configuring Launchpad git repositories for '
                     f'{charm.name}')
        team = self.lp.people[charm.team]
        project = self.lp.projects[charm.launchpad_project]

        if project.owner != team:
            logger.error(f'Project owner of project {charm.launchpad_project} '
                         f'does not match owner specified {charm.team}')
            raise ValueError('Unexpected project owner for '
                             f'{charm.launchpad_project}')

        repo = self.get_git_repository(team, project)

        if repo is None:
            logger.debug(f'Git repository for project {project.name} and '
                         f'{team.name} does not exist, importing now from '
                         f'{charm.repository}')
            repo = self.import_repository(team, project, charm.repository)
        else:
            logger.debug(f'Git repository for project {project.name} and '
                         f'{team.name} already exists.')

        # Check whether the repository is the default repository for the
        # project or not.
        if not repo.target_default:
            logger.debug(f'Setting default repository for {project.name} to '
                         f'{repo.git_https_url}')
            try:
                self.lp.git_repositories.setDefaultRepository(target=project,
                                                              repository=repo)
                repo.lp_refresh()
            except:  # no-qa
                # Log the error, but don't fail if we couldn't set the
                # default repository. Typically means the team is not the
                # owner of the project.
                logger.error('Failed to set the default repository for '
                             f'{project.name} to {repo.git_https_url}')

        if not project.vcs:
            logger.debug(f'Setting project {project.name} vcs to Git')
            project.vcs = 'Git'
            project.lp_save()

        return repo

    def get_charm_recipes(self, owner: 'team', project: 'project') \
            -> typing.List['charm_recipes']:
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
        logger.debug(f'Fetching git repositories for target={project.name}')
        return list(
            filter(lambda r: r.project == project,
                   self.lp.charm_recipes.findByOwner(owner=owner))
        )

    def update_charm_recipe(self, recipe: 'charm_recipe', branch_info: dict)\
            -> bool:
        """Updates the charm_recipe to match the requested configuration in
        the track_info.

        :param recipe: the charm recipe to update
        :param branch_info: the branch_info dictionary containing information
                           for the recipe
        :return: True if updated, False otherwise
        """
        # Yes, we could iterate the keys of the track_info here, but not all
        # the keys have the same name. As such, we'll go old-school and do
        # each attribute we know about.
        logger.debug(f'Updating charm recipe {recipe.name} for '
                     f'{recipe.project.name}')
        changed = False
        if recipe.auto_build != branch_info.get('auto-build'):
            recipe.auto_build = branch_info.get('auto-build')
            changed = True

        if recipe.auto_build_channels != branch_info.get('build-channels'):
            recipe.auto_build_channels = branch_info.get('build-channels')
            changed = True

        if recipe.build_path != branch_info.get('build-path', None):
            recipe.build_path = branch_info.get('build-path')
            changed = True

        if recipe.store_channels != branch_info.get('tracks', []):
            recipe.store_channels = branch_info.get('tracks', [])
            changed = True

        if recipe.store_upload != branch_info.get('upload'):
            recipe.store_upload = branch_info.get('upload')
            changed = True

        if changed:
            logger.debug(f'Charm recipe {recipe.name} has changes. Saving.')
            recipe.lp_save()
        else:
            logger.debug(f'No changes needed for charm recipe {recipe.name}')

        return changed

    def configure_charm_recipes(self, charm: CharmProject):
        """Configures charm recipes in Launchpad per the CharmProject's
        configuration.

        :param charm: the charm project to create charm recipes for.
        :return:
        """
        logger.debug(f'Configuring charm recipes for charm {charm.name}')
        team = self.lp.people[charm.team]
        project = self.lp.projects[charm.launchpad_project]

        repository = self.get_git_repository(team, project)
        if not repository:
            logger.error(f'Unable to find repository for team {team.name} and '
                         f'project {project.name}')
            raise ValueError(f'Unable to find repository for team {team.name} '
                             f'and project {project.name}')

        lp_recipes = self.get_charm_recipes(team, project)
        charm_recipes = {recipe.name: recipe for recipe in lp_recipes}
        for lp_branch in repository.branches:
            branch_info = charm.branches.get(lp_branch.path, None)
            if not branch_info:
                logger.debug('No tracks configured for branch '
                             f'{lp_branch.path}')
                continue

            # Strip off refs/head/. And no / allowed, so we'll replace with _
            branch_name = lp_branch.path[11:].replace('/', '_')
            recipe_format = branch_info.get('recipe-name')
            recipe_name = recipe_format.format(
                project=project.name, branch=branch_name
            )

            recipe = charm_recipes.pop(recipe_name, None)
            if recipe:
                logger.debug(f'Recipe already exists for {recipe_name}')
                self.update_charm_recipe(recipe, branch_info)
            else:
                logger.debug(f'Creating charm recipe for {recipe_name}')
                upload = branch_info.get('upload', True)
                recipe_args = {
                    'auto_build': branch_info.get('auto-build', True),
                    'git_ref': lp_branch,
                    'name': recipe_name,
                    'owner': team,
                    'project': project,
                    'store_name': charm.charmhub_name,
                    'store_upload': upload,
                }
                if upload and branch_info.get('tracks', None):
                    recipe_args.update({
                        'store_channels': branch_info.get('tracks')
                    })
                if 'build_channels' in branch_info:
                    recipe_args.update({
                        'auto_build_channels': branch_info['build-channels']
                    })
                recipe = self.lp.charm_recipes.new(**recipe_args)
                logger.debug(f'Created charm recipe {recipe.name}')

        # TODO (wolsen) Check to see if there are any remaining charm_recipes
        #  configured in Launchpad and remove them (?). Remaining charm_recipes
        #  will be those left in the charm_recipes dict. Not doing this
        #  currently as its not clear that we want to remove them automatically
        #  (yet).


def setup_logging():
    """Sets up some basic logging."""
    logging.basicConfig(level=logging.DEBUG)


def main():
    """Main entry point.

    :return:
    """
    parser = argparse.ArgumentParser(
        description='Configure launchpad projects for charms'
    )
    default_config_dir = os.path.abspath(os.path.join(CWD, './config'))
    parser.add_argument('-c', '--config-dir',
                        type=str, default=default_config_dir,
                        help='directory containing configuration files')
    parser.add_argument('project_groups', metavar='project_group',
                        type=str, nargs='*',
                        help='Project group configurations to process. If no '
                             'project groups are specified, all project '
                             'groups found in the config-dir will be loaded '
                             'and processed.')
    args = parser.parse_args()
    logging.debug(f'Using config dir {args.config_dir}')

    config_dir = pathlib.Path(os.fspath(args.config_dir))
    if not config_dir.exists():
        logger.error(f'Configuration directory {config_dir} does not exist')
        sys.exit(1)

    # Load the various project group configurations
    if not args.project_groups:
        files = list(config_dir.glob('*.yaml'))
    else:
        files = [config_dir / f'{group}.yaml' for group in args.project_groups]

    lp = LaunchpadTools()

    for file in files:
        with open(file, 'r') as f:
            group_config = yaml.safe_load(f)

        logger.debug(f'group_config is: {group_config}')
        project_defaults = group_config.get('defaults', {})
        for project in group_config.get('projects', []):
            for key, value in project_defaults.items():
                project.setdefault(key, value)
            logger.debug(f'Loaded project {project.get("name")}')
            charm_project = CharmProject(project)
            #lp.configure_git_repository(charm_project)

            # TODO(wolsen) Build the charm_recipes
            # lp.configure_charm_recipes(charm_project)

if __name__ == '__main__':
    setup_logging()
    main()
