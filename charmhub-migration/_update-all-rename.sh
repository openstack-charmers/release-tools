#!/bin/bash -e
charms=$(cd ../charms && ls -d1 *)

for charm in $charms; do
    echo "===== $charm ====="
    (
        cp ../global/source-zaza/rename.sh ../charms/$charm/rename.sh
    )
done
