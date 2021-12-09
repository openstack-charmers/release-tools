#
# Copyright 2021, Canonical
#
import logging
from typing import (Any, Dict, Iterator, List, Tuple, Optional)
import sys

import lazr

from launchpadlib.uris import lookup_service_root
from launchpadlib.launchpad import Launchpad

# All objects returned by launchpadlib are lazr.restfulclient.resource.Entry
TypeLPObject = lazr.restfulclient.resource.Entry

logger = logging.getLogger(__name__)


def setup_logging(loglevel: str) -> None:
    """Sets up some basic logging."""
    logger.setLevel(getattr(logging, loglevel, 'ERROR'))


class LaunchpadTools:
    """LaunchpadTools - a helper class to work with launchpadlib."""

    def __init__(self) -> None:
        """Create a LaunchpadTools object, and login to launchpad."""
        self.lp = Launchpad.login_with(
            'openstack-charm-tools',
            service_root=lookup_service_root('production'),
            version='devel',
            credential_save_failed=self.no_credential,
        )

    @staticmethod
    def no_credential() -> None:
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
