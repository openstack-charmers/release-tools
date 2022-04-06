#!/bin/bash -e
#
# Does a batch with a particular migration script.
# looks at all the charms, cds into that directory and then runs the script

script_dir="$( cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"

_dir=$(pwd)
# verify that the branch isn't master
branch=$(git branch --show-current | tr -d '\n')
if [[ "$branch" == "master" ]];
then
    echo "Branch is ${_dir}"
    echo "Branch is master - not updating."
    exit 0
fi

git_status="$(git status -s)"
if [[ -n "$git_status" ]]; then
    echo "Updating, no-edit-amend and git review with topic for ${_dir}"
    git add .
    git commit --amend --no-edit
    git review -t charmhub-migration-yoga
else
    echo "Nothing to do."
fi
