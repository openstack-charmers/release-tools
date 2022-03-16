#!/bin/bash -e
#
# Does a batch with a particular migration script.
# looks at all the charms, cds into that directory and then runs the script

script_dir="$( cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
target_script="$script_dir/$1"

charms=$(cd ../charms && ls -d1 *)

echo "Running $target_script:"

for charm in $charms; do
    (
        cd ../charms/$charm
        $target_script
    )
done
