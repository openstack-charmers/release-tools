#!/usr/bin/env python3

import argparse
import os
import glob
import sys

import git
import humanize
import yaml

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from launchpadlib.launchpad import Launchpad

try:
    from importlib_resources import files, as_file  # type: ignore
except ImportError:
    from importlib.resources import files, as_file  # type: ignore

__author__ = "Felipe Reyes <felipe.reyes@canonical.com>"
__copyright__ = "Copyright 2022, Canonical Ltd."
__description__ = 'Check the status of code imports in Launchpad.'

OKGREEN = '\033[92m'
WARNING = '\033[93m'
FAIL = '\033[91m'
ENDC = '\033[0m'

NOW = datetime.now(tz=ZoneInfo("UTC") )
MAX_IMPORT_AGE = timedelta(days=1)

CODE_IMPORT_ERROR_CODES = ['Failed', 'Suspended']
CODE_IMPORT_WARN_CODES = ['Pending Review', 'Invalid']
CODE_IMPORT_OK_CODES = ['Reviewed']

cachedir = os.path.expanduser("~/.release-tools/cache")
os.makedirs(cachedir, exist_ok=True)
launchpad = Launchpad.login_anonymously('charmed-openstack release-tools',
                                        'production', cachedir, version='devel')


def setup_options():
    """Setup command line options."""

    parser = argparse.ArgumentParser(description=__description__)
    parser.add_argument('-c', '--category', dest='category', metavar='CATEGORY',
                        help='Category of charms to check')
    parser.add_argument('--charm', dest='charms', action='append', metavar='CHARM',
                        help='Charm to check')
    parser.add_argument('-f', '--format', dest='format', default='human',
                        choices=['human', 'json'], metavar='FORMAT',
                        help='Output format')
    return parser.parse_args()


def get_lp_repo(project: str):
    repo = launchpad.git_repositories.getByPath(path=project)

    return repo


def get_repo(repo_dst, upstream_url, mirror_url):
    if os.path.isdir(repo_dst):
        git_repo = git.Repo(repo_dst)
        for remote in git_repo.remotes:
            remote.fetch()

        git_repo.remotes.origin.pull()
    else:
        git_repo = git.Repo.clone_from(upstream_url, repo_dst)
        mirror_remote = git_repo.create_remote('mirror', repo.git_https_url)
        mirror_remote.fetch()

    return git_repo


def find_missing_commits(git_repo):
    # discard HEAD since it's just an alias that only exists for git's
    # upstream.
    upstream_refs = [ref for ref in git_repo.remote().refs if ref.name != 'origin/HEAD']
    missing_commits = {}
    for upstream_ref in upstream_refs:
        branch_name = upstream_ref.name.split('/', maxsplit=1)[1]
        mirror_ref = git_repo.remotes.mirror.refs[branch_name]

        if mirror_ref.commit.hexsha != upstream_ref.commit.hexsha:
            git_log = git_repo.git.log(
                f'{mirror_ref.commit.hexsha}..{upstream_ref.commit.hexsha}',
                oneline=True
            )
            missing_commits[branch_name] = git_log

    return missing_commits


def print_report(output):

    for name, project in output.items():
        if not project['code_import_available']:
            print(name, f'{FAIL}no code import found{ENDC}')
            continue
        if project['code_import_review_status'] in CODE_IMPORT_ERROR_CODES:
            color = FAIL
        elif project['code_import_review_status'] in CODE_IMPORT_WARN_CODES:
            color = WARNING
        elif project['code_import_review_status'] in CODE_IMPORT_OK_CODES:
            color = OKGREEN
        else:
            color = ''

        print(name, f"{color}{project['code_import_review_status']}{ENDC}",
              end='')

        if NOW - project['code_import_last_successful'] > MAX_IMPORT_AGE:
            color = FAIL
        else:
            color = ''

        age = humanize.naturaltime(project['code_import_last_successful'], when=NOW)
        print(f' ({color}{age}{ENDC})', project['code_import_web_link'])

        if project['missing_commits']:
            for branch, log in project['missing_commits'].items():
                print(f'  {branch}:')
                for line in log.split('\n'):
                    print(f'    {line}')

def main(cfg_dir):
    opts = setup_options()

    if opts.category:
        fpath = os.path.join(cfg_dir, f'{opts.category}.yaml')
        assert os.path.isfile(fpath), f'No such file or directory: {fpath}'
        lp_builder_files = [fpath]
    else:
        lp_builder_files = glob.glob(f'{cfg_dir}/lp-builder-config/*.yaml')

    output = {}
    for fname in lp_builder_files:
        with open(fname, 'r') as f:
            lp_builder_config = yaml.safe_load(f)

        for project in lp_builder_config['projects']:
            if opts.charms and project['charmhub'] not in opts.charms:
                # skip if the charm's name is not the filter list.
                continue
            lp_prj_name = project['launchpad']

            repo = get_lp_repo(lp_prj_name)
            code_import = repo.code_import
            try:
                output[lp_prj_name] = {
                    'code_import_available': True,
                    'code_import_review_status': code_import.review_status,
                    'code_import_last_successful': code_import.date_last_successful,
                    'code_import_web_link': repo.web_link,
                }
            except AttributeError:
                output[lp_prj_name] = {'code_import_available': False}
                continue

            repo_dst = f'{cachedir}/git_repos/{lp_prj_name}'

            git_repo = get_repo(repo_dst,
                                upstream_url=project['repository'],
                                mirror_url=repo.git_https_url)

            output[lp_prj_name]['missing_commits'] = find_missing_commits(git_repo)

    if opts.format == 'json':
        print(json.dumps(output))
    else:
        print_report(output)


if __name__ == '__main__':
    config_dir = files('charmed_openstack_info.data.lp-builder-config')
    with as_file(config_dir) as cfg_dir:
        main(cfg_dir)
