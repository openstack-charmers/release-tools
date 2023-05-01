#!/bin/bash

# Note that this needs to be run in the root for the charm directory

# run this script in the root of the charm directory

script_dir="$( cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
repo_dir="$script_dir/../.."
worktree_branch="stable/yoga"
ceph_release="octopus"
openstack_release="ussuri"

function update_bundles {
    local charm_dir=$1
    (
        cd $charm_dir
        # remove any existing channel specs
        $repo_dir/update-channel-single.py --log DEBUG \
            --remove-channel \
            --disable-local-overlay
        # set all the branches to latest/edge and ch: prefixes
        $repo_dir/update-channel-single.py --log DEBUG --branch master \
            --ensure-charmhub --enforce-edge
        # Then overwrite with branches appropirate to ceph-pacific
        $repo_dir/update-channel-single.py --log DEBUG \
            --branch stable/$openstack_release \
            --branch stable/20.03 \
            --branch stable/5.7   \
            --branch stable/focal \
            --branch stable/1.7 \
            --branch stable/jammy \
            --branch stable/$ceph_release \
            --set-local-charm \
            --enforce-edge
    )
}

update_bundles .
