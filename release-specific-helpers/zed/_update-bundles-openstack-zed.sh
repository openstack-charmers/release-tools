#!/bin/bash

# Note that this needs to be run in the root for the charm directory

# run this script in the root of the charm directory

script_dir="$( cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
repo_dir="$script_dir/../.."
ceph_branch="quincy"
openstack_branch="zed"
ovn_branch="22.03"
mysql_branch="jammy"
hacluster_branch="jammy"
rabbitmq_server_branch="jammy"
vault_branch="1.8"



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
            --branch stable/$openstack_branch \
            --branch stable/$ovn_branch \
            --branch stable/$mysql_branch   \
            --branch stable/$hacluster_branch \
            --branch stable/$vault_branch \
            --branch stable/$rabbitmq_server_branch \
            --branch stable/$ceph_branch \
            --set-local-charm \
            --enforce-edge
    )
}

update_bundles .
