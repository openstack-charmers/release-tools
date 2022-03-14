#!/usr/bin/env python3

import requests
import json
import yaml

PORT="29418"
HOST="ajkavanagh@review.opendev.org"

def branch_exists(project, branch):
    branch = branch.replace('/', '%2F')
    project = project.replace('/', '%2F')
    url = f'https://review.opendev.org/projects/{project}/branches?m={branch}'
    r = requests.get(url)
    if r.status_code != 200:
        return False
    branches = json.loads(r.text.split('\n')[1])
    return len(branches) > 0

def create_branch(project, name, revision):
    if branch_exists(project, revision):
        print(f'echo "Creating branch for {project} {name} {revision}"')
        print(f"ssh -p {PORT} {HOST} gerrit create-branch {project} {name} {revision}")
    else:
        print(f"# Cannot create branch {name} for {project} source branch {revision} does not exist")

def url2project(url):
    project = url.split('/')[-1].split('.')[0]
    return f"{project}"

def create_branches(source_file, prefix='openstack'):
    with open(source_file, "r") as f:
        contents = yaml.load(f, Loader=yaml.FullLoader)
    default_branches = []
    if contents.get('defaults', {}).get('branches'):
        default_branches = list(contents['defaults']['branches'].keys())
        default_branches.remove('master')
    for charm in contents['projects']:
        if charm.get('branches'):
            branches = list(charm['branches'].keys())
            branches.remove('master')
        else:
            branches = default_branches[:]
        for branch in branches:
            project = f"{prefix}/" + url2project(charm['repository'])
            create_branch(
                    project,
                    branch,
                    "stable/21.10")

print("# Openstack")
create_branches("lp-builder-config/openstack.yaml", prefix='openstack')
print("# Ceph")
create_branches("lp-builder-config/ceph.yaml")
print("# OVN")
create_branches("lp-builder-config/ovn.yaml", prefix='x')
print("# Misc")
create_branches("lp-builder-config/misc.yaml")
