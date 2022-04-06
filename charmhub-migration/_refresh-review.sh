#!/bin/bash

# refresh the review using the change ID from the last commit.
# Only works if there are no changes
# run in the git repository

git_status="$(git status -s)"
if [[ -n "$git_status" ]]; then
    echo "Git repository is dirty; exiting."
    exit 1
fi

# find the commit id
change_id=$(git last | grep "Change-Id: " | awk '{print $2}')
echo "Change id is $change_id"
git review -d $change_id
