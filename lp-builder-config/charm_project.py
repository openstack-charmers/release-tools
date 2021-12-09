#
# Copyright 2021, Canonical
#

import collections
import io
import logging
from typing import (Any, Dict, Iterator, List, Tuple, Optional)
import sys

from launchpadtools import LaunchpadTools, TypeLPObject


logger = logging.getLogger(__name__)


def setup_logging(loglevel: str) -> None:
    """Sets up some basic logging."""
    logger.setLevel(getattr(logging, loglevel, 'ERROR'))


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
    def lp_team(self) -> TypeLPObject:
        """Return the launchpadlib object for the team.

        This is cached as it's used several times and is quite expensive to
        produce.
        """
        if self._lp_team:
            return self._lp_team
        self._lp_team = self.lpt.get_lp_team_for(self.team)
        return self._lp_team

    @property
    def lp_project(self) -> TypeLPObject:
        """Return the launchpadlib object for the project."""
        if self._lp_project:
            return self._lp_project
        self._lp_project = self.lpt.get_lp_project_for(self.launchpad_project)
        return self._lp_project

    @property
    def lp_repo(self) -> TypeLPObject:
        """Return the launchpadlib object for the repository, if configured."""
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

    def show_lauchpad_config(self,
                             file: io.TextIOWrapper = sys.stdout
                             ) -> None:
        """Print out the launchpad config for the charms, if any.
        """
        logger.info(f'Printing launchpad info for: {self.name}')
        try:
            self.lp_project
        except KeyError:
            print(f"{self.name[:35]:35} -- Project doesn't exist!!: "
                  f"{self.launchpad_project}", file=file)
            return
        print(f"{self.name}:", file=file)
        print(f" * launchpad project: {self.launchpad_project}", file=file)
        try:
            self.lp_repo
        except ValueError:
            print(f"{self.name[:35]:35} -- No repo configured!", file=file)
            return
        print(f" * repo: {self.repository}")
        info = self._calc_recipes_for_repo()
        if info['in_config_recipes']:
            print(" * Recipes configured in launchpad matching channels:",
                  file=file)
            for name, detail in info['in_config_recipes'].items():
                branch = (
                    detail['current_recipe'].git_ref.path[len('refs/heads/'):])
                channels = ', '.join(detail['current_recipe'].store_channels)
                print(f"   - {name[:40]:40} - "
                      f"git branch: {branch[:20]:20} "
                      f"channels: {channels}",
                      file=file)

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
