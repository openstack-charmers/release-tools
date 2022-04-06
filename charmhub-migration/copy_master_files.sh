#!/bin/bash

charms=$(cd ../charms && ls -d1 *)

files="charmcraft.yaml tox.ini src/tox.ini requirements.txt src/requirements.txt test-requirements.txt src/test-requirements.txt"
for charm in $charms; do
    # copy various files.
    for file in $files; do
        if [[ -e "../charms/$charm/__worktrees/master/$file" ]]; then
            echo "For $charm, copying master $file"
            cp "../charms/$charm/__worktrees/master/$file" "../charms/$charm/$file"
        else
            echo "No $file for $charm"
        fi
    done
done
