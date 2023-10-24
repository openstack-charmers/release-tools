#!/usr/bin/env bash
#

script_dir="$( cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"

# get most of the charms
${script_dir}/update-channel-single --log DEBUG \
            --enforce-edge \
            --branch stable/23.09 \
            --branch stable/1.8 \
            --branch stable/jammy

${script_dir}/update-channel-single --log DEBUG \
            --enforce-edge \
            --channel reef/edge \
            --section ceph

${script_dir}/update-channel-single --log DEBUG \
            --enforce-edge \
            --channel 23.09/edge \
            --section ovn

${script_dir}/update-channel-single --log DEBUG \
            --enforce-edge \
            --channel 2023.2/edge \
            --section openstack
