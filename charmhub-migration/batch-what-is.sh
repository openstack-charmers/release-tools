#!/bin/bash -e
#
# prints a list of a charm type in the charms directory.
# pass the type as param1 - classic-zaza or source-zaza

target_type=$1

charms=$(cd ../charms && ls -d1 *)

echo "Looking at $target_type:"

for charm in $charms; do
    charm_type="$(../what-is ../charms/$charm)"
    if [[ "$charm_type" == "$target_type" ]];
    then
        echo "- [ ] $charm"
    fi
done

