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
import lazr
import logging
import os
import io
import pathlib
import pprint
import sys
from typing import (Any, Dict, Iterator, List, Tuple, Optional)
import yaml

from launchpadlib.uris import lookup_service_root
from launchpadlib.launchpad import Launchpad

# All objects returned by launchpadlib are lazr.restfulclient.resource.Entry
TypeLPObject = lazr.restfulclient.resource.Entry

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

    def __init__(self, config, lpt: 'LaunchpadTools'):
        self.lpt = lpt
        self.name: str = config.get('name')
        self.team: str = config.get('team')
        self._lp_team = None
        self.charmhub_name: str = config.get('charmhub')
        self.launchpad_project: str = config.get('launchpad')
        self._lp_project = None
        self.repository: str = config.get('repository')
        self._lp_repo = None

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

    @property
    def lp_team(self):
        if self._lp_team:
            return self._lp_team
        self._lp_team = self.lpt.get_lp_team_for(self.team)
        return self._lp_team

    @property
    def lp_project(self):
        if self._lp_project:
            return self._lp_project
        self._lp_project = self.lpt.get_lp_project_for(self.launchpad_project)
        return self._lp_project

    @property
    def lp_repo(self):
        if self._lp_repo:
            return self._lp_repo
        self._lp_repo = self.lpt.get_git_repository(
            self.lp_team, self.lp_project)
        return self._lp_repo

    def ensure_git_repository(self) -> None:
        """Ensure that launchpad project git repository exists.

        Configures launchpad project repositories for self (the charm)
        project. This function will validate that a git repository is
        configured in launchpad to import the git tree from the upstream
        project repository and that the git repository is set as the default
        code repository for the launchpad project.
        """
        logger.info('Checking Launchpad git repositories for %s.',
                    self.name)

        if self.lp_project.owner != self.lp_team:
            logger.error('Project owner of project %s '
                         'does not match owner specified %s',
                         self.launchpad_project, self.team)
            raise ValueError(
                f'Unexpected project owner for {self.launchpad_project}')

        if self.lp_repo is None:
            logger.info('Git repository for project %s and '
                        '%s does not exist, importing now from %s',
                        self.lp_project.name, self.lp_team.name,
                        self.repository)
            self._lp_repo = self.lpt.import_repository(
                self.lp_team, self.lp_project, self.repository)
        else:
            logger.debug('Git repository for project %s and '
                         '%s already exists.',
                         self.lp_project.name, self.lp_team.name)

        # Check whether the repository is the default repository for the
        # project or not.
        if not self.lp_repo.target_default:
            logger.info('Setting default repository for %s to %s',
                        self.lp_project.name, self.lp_repo.git_https_url)
            try:
                self.lpt.set_default_repository(self.lp_project, self.lp_repo)
                self.lp_repo.lp_refresh()
            except Exception:  # no-qa
                # Log the error, but don't fail if we couldn't set the
                # default repository. Typically means the team is not the
                # owner of the project.
                logger.error(
                    'Failed to set the default repository for %s to %s',
                    self.lp_project.name, self.lp_repo.git_https_url)

        if not self.lp_project.vcs:
            logger.info('Setting project %s vcs to Git', self.lp_project.name)
            self.lp_project.vcs = 'Git'
            self.lp_project.lp_save()

        return self.lp_repo

    @staticmethod
    def _get_git_repository(lpt: 'LaunchpadTools',
                            lp_team: TypeLPObject,
                            lp_project: TypeLPObject,
                            ) -> TypeLPObject:
        """Ensure charm recipes in Launchpad matches CharmProject's conf.

        :param lpt: the launchpad tools object to do things in launchpad.
        :param lp_team: the lp team object
        :param lp_project: the lp project object
        :returns: the lp repoistory object
        :raises ValueError: if the repository can't be found.
        """
        lp_repo = lpt.get_git_repository(lp_team, lp_project)
        if not lp_repo:
            raise ValueError(
                f'Unable to find repository for team {lp_team.name} '
                f'and project {lp_project.name}')
        return lp_repo

    def ensure_charm_recipes(self) -> None:
        """Ensure charm recipes in Launchpad matches CharmProject's conf.
        """
        logger.info('Checking charm recipes for charm %s', self.name)
        logger.debug(str(self))
        try:
            self.lp_project
        except KeyError:
            logger.error(
                "Can't continue; no project in Launchpad called '%s'",
                self.launchpad_project)
        try:
            self.lp_repo
        except ValueError:
            logger.error(
                "Can't continue; no repository defined for %s",
                self.launchpad_project)
            return

        current = self._calc_recipes_for_repo()
        if current['missing_branches_in_repo']:
            # This means that there are required channels, but no branches in
            # the repo; need to log this fact.
            logger.info(
                "The following branches are missing from the repository "
                "but are configured as branches for recipes.")
            for branch in current['missing_branches_in_repo']:
                logger.info(" - %s", branch)
        any_changes = (all(not(r['exists']) or r['changed']
                           for r in current['in_config_recipes'].values()))
        if not(any_changes):
            logger.info("No changes needed.")
            return

        # Create recipes that are missing and/o update recipes that have
        # changes.
        for recipe_name, state in current['in_config_recipes']:
            if state['exists'] and state['changed']:
                # it's an update
                lp_recipe = state['current_recipe']
                logger.info('Charm recipe %s has changes. Saving.',
                            lp_recipe.name)
                logger.debug("Changes: {}".format(", ".join(state['changes'])))
                for rpart, battr in state['updated_parts']:
                    setattr(lp_recipe, rpart, battr)
                lp_recipe.lp_save()
            elif not(state['exists']):
                logger.info('Creating charm recipe for %s', recipe_name)
                build_from = state['build_from']
                self.lpt.create_charm_recipe(
                    recipe_name=recipe_name,
                    # branch_info=branch_info,
                    branch_info=build_from['branch_info'],
                    lp_branch=build_from['lp_branch'],
                    owner=self.lp_team,
                    project=self.lp_project,
                    store_name=self.charmhub_name,
                    channels=build_from['channels'])
                logger.info('Created charm recipe %s', lp_recipe.name)

            else:
                logger.info('No changes needed for charm recipe %s',
                            recipe_name)

        # TODO (wolsen) Check to see if there are any remaining charm recipes
        #  configured in Launchpad and remove them (?). Remaining charm recipes
        #  will be those left in the charm_lp_recipe_map dict. Not doing this
        #  currently as its not clear that we want to remove them automatically
        #  (yet).

    def _calc_recipes_for_repo(self) -> Dict:
        """Calculate the set of recipes for a repo based on the config.

        Return a calculated set of repo branches, channels, recipe names and
        their configuration.

        The repo_branches is an OrderedDict of repo branch -> List[recipe_name]
        The channels ...
        """
        lp_recipes = self.lpt.get_charm_recipes(self.lp_team, self.lp_project)
        charm_lp_recipe_map = {recipe.name: recipe for recipe in lp_recipes}

        # a recipe_name: {info for recipe}  dictionary
        all_recipes: Dict[str, Dict] = collections.OrderedDict()
        no_recipe_branches: List[str] = []
        mentioned_branches: List[str] = []

        for lp_branch in self.lp_repo.branches:
            mentioned_branches.append(lp_branch.path)
            branch_info = self.branches.get(lp_branch.path, None)
            if not branch_info:
                logger.info('No tracks configured for branch %s, continuing.',
                            lp_branch.path)
                no_recipe_branches.append(lp_branch.path)
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
                tracks = self._group_channels(channels)
            else:
                tracks = (("latest", []),)
            for track, track_channels in tracks:
                recipe_name = recipe_format.format(
                    project=self.lp_project.name,
                    branch=branch_name,
                    track=track)

                lp_recipe = charm_lp_recipe_map.pop(recipe_name, None)
                if lp_recipe:
                    # calculate diff
                    changed, updated_dict, changes = (
                        self.lpt.diff_charm_recipe(
                            recipe=lp_recipe,
                            auto_build=branch_info.get('auto-build'),
                            auto_build_channels=branch_info.get(
                                'build-channels'),
                            build_path=branch_info.get('build-path', None),
                            store_channels=track_channels,
                            store_upload=branch_info.get('upload')))

                    all_recipes[recipe_name] = {
                        'exists': True,
                        'changed': changed,
                        'current_recipe': lp_recipe,
                        'updated_parts': updated_dict,
                        'changes': changes,
                    }
                else:
                    all_recipes[recipe_name] = {
                        'exists': False,
                        'changed': False,
                        'current_recipe': None,
                        'updated_recipe': None,
                        'changes': [],
                    }
                all_recipes[recipe_name].update({
                    'build_from': {
                        'recipe_name': recipe_name,
                        'branch_info': branch_info,
                        'lp_branch': lp_branch,
                        'lp_team': self.lp_team,
                        'lp_project': self.lp_project,
                        'store_name': self.charmhub_name,
                        'channels': track_channels
                    }
                })
        return {
            'lp_recipes': lp_recipes,
            'non_config_recipes': charm_lp_recipe_map,
            'in_config_recipes': all_recipes,
            'no_recipe_branches': no_recipe_branches,
            'missing_branches_in_repo': list(
                sorted(set(self.branches.keys() - set(mentioned_branches)))),
        }

    def print_diff(self,
                   detail: bool = False,
                   file: io.TextIOWrapper = sys.stdout) -> None:
        """Print a diff between desired config and actual config.

        :param detail: print detailed output if True
        :param file: where to send the output.
        """
        logger.info(f'Printing diff for: {self.name}')
        try:
            self.lp_project
        except KeyError:
            print(f"{self.name[:35]:35} -- Project doesn't exist!!: "
                  f"{self.launchpad_project}", file=file)
            return
        try:
            self.lp_repo
        except ValueError:
            print(f"{self.name[:35]:35} -- No repo configured!", file=file)
            return
        info = self._calc_recipes_for_repo()
        any_changes = (all(not(r['exists']) or r['changed']
                           for r in info['in_config_recipes'].values()))
        change_text = ("Changes required"
                       if any_changes or info['missing_branches_in_repo']
                       else "No changes needed")
        extra_recipes_text = (
            f" - {len(info['non_config_recipes'].keys())} extra config recipes"
            if info['non_config_recipes'] else "")
        print(
            f"{self.name[:35]:35} {change_text:20}{extra_recipes_text}",
            file=file)
        if detail:
            # Print detail from info.
            if info['non_config_recipes']:
                print(" * Recipes that have no corresponding config:",
                      file=file)
                for recipe_name in info['non_config_recipes'].keys():
                    print(f"   - {recipe_name}", file=file)
            if any_changes:
                print(" * recipes that require changes:", file=file)
                for recipe_name, detail in info['in_config_recipes'].items():
                    if not(detail['exists']):
                        print(f"    - {recipe_name:35} : Needs creating.",
                              file=file)
                    elif detail['changed']:
                        print(f"    - {recipe_name:35} : "
                              f"{','.join(detail['changes'])}", file=file)
            if info['missing_branches_in_repo']:
                print(" * missing branches in config but not in repo:",
                      file=file)
                for branch in info['missing_branches_in_repo']:
                    print(f'    - {branch[len("refs/heads/"):]}', file=file)
        # pprint.pprint(info)

    @staticmethod
    def _group_channels(channels: List[str],
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

    def get_lp_team_for(self, team_str: str) -> TypeLPObject:
        """Return the team object for a team str.

        :param team_str: the team to return the team object for.
        """
        return self.lp.people[team_str]

    def get_lp_project_for(self, charm_name: str) -> TypeLPObject:
        """Return the project object for a project name.

        :param charm_name: the project name to return the project object for.
        :raises KeyError: if the project doesn't exist.
        """
        return self.lp.projects[charm_name]

    def set_default_repository(self,
                               lp_project: TypeLPObject,
                               lp_repo: TypeLPObject,
                               ) -> None:
        """Set the default repository for a launchpad project.

        :param lp_project: the LP project object to configure.
        :param lp_repo: the LP repository object to use as a default.
        """
        self.lp.git_repositories.setDefaultRepository(
            target=lp_project, repository=lp_repo)

    def get_git_repository(self, owner: TypeLPObject, project: TypeLPObject):
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
            None)

    def import_repository(self,
                          owner: TypeLPObject,
                          project: TypeLPObject,
                          url: str
                          ) -> TypeLPObject:
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

    def get_charm_recipes(self,
                          owner: TypeLPObject,
                          project: TypeLPObject
                          ) -> List[TypeLPObject]:
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
                   self.lp.charm_recipes.findByOwner(owner=owner)))
        logger.debug(" -- found recipes:\n%s",
                     "\n".join(f"  - {r.name}" for r in recipes))
        return recipes

    def update_charm_recipe(self,
                            recipe: TypeLPObject,
                            auto_build: bool = False,
                            auto_build_channels: bool = False,
                            build_path: Optional[str] = None,
                            store_channels: Optional[List[str]] = None,
                            store_upload: bool = False,
                            ) -> bool:
        """Updates the charm_recipe to match the requested configuration in
        the track_info.

        :param recipe: the charm recipe to update
        :param branch_info: the branch_info dictionary containing information
                           for the recipe
        :return: True if updated, False otherwise
        """
        changed, updated_dict, changes = self.diff_charm_recipe(
            recipe=recipe,
            auto_build=auto_build,
            auto_build_channels=auto_build_channels,
            build_path=build_path,
            store_channels=store_channels,
            store_upload=store_upload)

        if changed:
            logger.info('Charm recipe %s has changes. Saving.', recipe.name)
            logger.debug("Changes: {}".format(", ".join(changes)))
            for rpart, battr in updated_dict.items():
                setattr(recipe, rpart, battr)
            recipe.lp_save()
        else:
            logger.info('No changes needed for charm recipe %s', recipe.name)

        return changed

    def diff_charm_recipe(self,
                          recipe: TypeLPObject,
                          auto_build: bool = False,
                          auto_build_channels: bool = False,
                          build_path: Optional[str] = None,
                          store_channels: Optional[List[str]] = None,
                          store_upload: bool = False,
                          ) -> (bool, Dict[str, Any], List[str]):
        """Returns Updates the charm_recipe to match the required config.

        :param recipe: the charm recipe to update
        :param branch_info: the branch_info dictionary containing information
                           for the recipe
        :return: Tuple of (changed_flag, parts-changed, List of changes)
        """
        changed = []

        parts = (('auto_build', auto_build),
                 ('auto_build_channels', auto_build_channels),
                 ('build_path', build_path),
                 ('store_channels', store_channels),
                 ('store_upload', store_upload),)

        changes = {}

        for (rpart, battr) in parts:
            rattr = getattr(recipe, rpart)
            logger.debug("rpart: '%s', recipe.%s is %s, want %s",
                         rpart, rpart, rattr, battr)
            if rattr != battr:
                changes[rpart] = battr
                changed.append(f"recipe.{rpart} = {battr}")

        return (bool(changed), changes, changed)

    def create_charm_recipe(self,
                            recipe_name: str,
                            branch_info: dict,
                            lp_branch: str,
                            owner: TypeLPObject,
                            project: TypeLPObject,
                            store_name: str,
                            channels: List[str],
                            ) -> TypeLPObject:
        """Create a new charm recipe using the branch_info and channels.

        The channels are a grouping of same track, different risks.
        e.g.
        ['latest/edge', 'latest/stable']

        :param recipe: the name of the recipe to create
        :param branch_info: a dictionary of relevant parts to create the recipe
        :param channels: a list of channels to target in the charmhub
        """
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
        self.lp.charm_recipes.new(**recipe_args)


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
        help=('The "show" commands shows the current configuration for the '
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
    config_command = subparser.add_parser(
        'config',
        help=("Show the config that would be applied."))
    config_command.set_defaults(func=config_main)
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


def show_main(args):
    raise NotImplementedError()


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


def config_main(args: argparse.Namespace,
                lpt: LaunchpadTools,
                gc: GroupConfig,
                ) -> None:
    raise NotImplementedError()
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
