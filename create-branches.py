#!/usr/bin/env python3

import yaml

PORT="22"
HOST="gerrit-host"

def create_branch(project, name, revision):
    print(f"ssh -p {PORT} {HOST} gerrit create-branch {project} {name} {revision}")

def url2project(url):
    project = url.split('/')[-1].split('.')[0]
    return f"openstack/{project}"

def create_ceph_branches():
    with open("lp-builder-config/ceph.yaml", "r") as f:
        contents = yaml.load(f, Loader=yaml.FullLoader)
    branches = list(contents['defaults']['branches'].keys())
    branches.remove('master')
    for charm in contents['projects']:
        for branch in branches:
            create_branch(
                url2project(
                    charm['repository']),
                    branch,
                    "HEAD")

def create_misc_branches():
    with open("lp-builder-config/misc.yaml", "r") as f:
        contents = yaml.load(f, Loader=yaml.FullLoader)
    for charm in contents['projects']:
        print(charm)
        branches = list(charm['branches'].keys())
        branches.remove('master')
        for branch in branches:
            create_branch(
                url2project(
                    charm['repository']),
                    branch,
                    "HEAD")
            
# create_ceph_branches()
create_misc_branches()
