#!/bin/bash

# Update the .zuul.yaml to have
# s/openstack-python3-ussuri-jobs/openstack-python3-charm-yoga-jobs/

sed -i s/openstack-python3-ussuri-jobs/openstack-python3-charm-yoga-jobs/ .zuul.yaml
