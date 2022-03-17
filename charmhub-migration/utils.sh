# Utils refactored out of the individual scripts for convenience



# run in the charm directory
# relies on openstack_release being passed as var 1
function ensure_git_branch {
    local openstack_release=$1
    local branch=$(git branch --show-current | tr -d '\n')
    if [[ "$branch" != "charmhub-migration-$openstack_release" ]];
    then
        git checkout -b "charmhub-migration-$openstack_release"
    fi
}


# run in the charm directory
# relies on $openstack_release being passed in var 1
function ensure_git_review {
    local openstack_release=$1
    # if it doesn't exist, add something to it.
    grep -q defaultbranch .gitreview || {
        echo -e "\ndefaultbranch=" >> .gitreview
    }
    # now ensure it is the correct release
    sed -i "s'defaultbranch=.*$'defaultbranch=stable/$openstack_release'g" .gitreview
    git add .gitreview
}


# run in the charm directory
function ensure_gitignore_charm {
    grep -q '*.charm' .gitignore || {
        echo -e "*.charm" >> .gitignore
    }
}



# ensure that if cffi is in a requirements file, that pyparsing pin is
# inserted.
function ensure_pyparsing_pin {
    for filename in requirements.txt test-requirements.txt requirements-dev.txt src/test-requirements; do
        if [ -e $filename ]; then
            grep -q pyparsing $filename || {
                pyparsing="pyparsing<3.0.0  # cffi needs pyparsing < 3.0.0."
                sed -i "/^cffi==.*/i $pyparsing" $filename
            }
        fi
    done
}


# update charmcraft
# worktree branch is in param 1
function charmcraft_classic {
    local worktree_branch=$1
    if [ -e "__worktrees/$worktree_branch/charmcraft.yaml" ];
    then
        cp __worktrees/$worktree_branch/charmcraft.yaml .
    else
        cp $script_dir/global/classic-zaza/charmcraft.yaml .
    fi
}

function charmcraft_source {
# worktree branch is in param 1
    local worktree_branch=$1
    if [ -e "__worktrees/$worktree_branch/charmcraft.yaml" ];
    then
        cp __worktrees/$worktree_branch/charmcraft.yaml .
    else
        cp $repo_dir/global/source-zaza/charmcraft.yaml .
    fi
}

function add_rename {
# worktree branch is in param 1
    local worktree_branch=$1
    if [ -e "__worktrees/$worktree_branch/rename.sh" ];
    then
        cp __worktrees/$worktree_branch/rename.sh .
    else
        cp $repo_dir/global/source-zaza/rename.sh .
    fi
}


function add_build_requirements {
# worktree branch is in param 1
    local worktree_branch=$1
    if [ -e "__worktrees/$worktree_branch/build-requirements.txt" ];
    then
        cp __worktrees/$worktree_branch/build-requirements.txt .
    else
        cp $repo_dir/global/source-zaza/build-requirements.txt .
    fi
}


function ensure_tox_classic {
# worktree branch is in param 1
    local worktree_branch=$1
    if [ -e "__worktrees/$worktree_branch/tox.ini" ];
    then
        cp __worktrees/$worktree_branch/tox.ini .
    else
        cp $repo_dir/global/classic-zaza/tox.ini .
    fi
}

function ensure_tox_source {
# worktree branch is in param 1
    local worktree_branch=$1
    if [ -e "__worktrees/$worktree_branch/tox.ini" ];
    then
        cp __worktrees/$worktree_branch/tox.ini .
    else
        cp $repo_dir/global/source-zaza/tox.ini .
    fi
}


# run in the charm directory
function ensure_libs_classic {
    local openstack_release=$1
    local ceph_release=$2
    # switch classic charms libs
    for ch in charm-helpers-hooks.yaml charm-helpers-tests.yaml; do
        if [ -f $ch ]; then
            echo
            sed -i "s'https://github.com/juju/charm-helpers.*$'https://github.com/juju/charm-helpers@stable/${openstack_release}'g" $ch
        fi
    done

    echo "Updating test-requirements.txt in repository with stable Zaza"
    for file in requirements.txt test-requirements.txt; do
        if [ -e "$file" ]; then
            set +e
            sed -i "s'openstack-charmers/zaza.git.*$'openstack-charmers/zaza.git@stable/$openstack_release#egg=zaza'g" $file
            sed -i "s'openstack-charmers/zaza-openstack-tests.git.*$'openstack-charmers/zaza-openstack-tests.git@stable/$openstack_release#egg=zaza.openstack'g" $file
            sed -i "s'github.com/juju/charm-helpers.*$'github.com/juju/charm-helpers@stable/$openstack_release#egg=charmhelper'g" $file
            sed -i "s'github.com/openstack/charms.ceph.git.*$'github.com/openstack/charms.ceph.git@stable/$ceph_release#egg=charms.ceph'g" $file
            set -e
        fi
    done

}

# run in the charm directory
function ensure_libs_source {
    local openstack_release=$1
    local ceph_release=$2
    echo "Updating test-requirements.txt in repository with stable Zaza"
    for file in requirements.txt test-requirements.txt src/test-requirements src/wheelhouse.txt; do
        if [ -e "$file" ]; then
            set +e
            sed -i "s'openstack-charmers/zaza.git.*$'openstack-charmers/zaza.git@stable/$openstack_release#egg=zaza'g" $file
            sed -i "s'openstack-charmers/zaza-openstack-tests.git.*$'openstack-charmers/zaza-openstack-tests.git@stable/$openstack_release#egg=zaza.openstack'g" $file
            sed -i "s'github.com/juju/charm-helpers.*$'github.com/juju/charm-helpers@stable/$openstack_release#egg=charmhelpers'g" $file
            sed -i "s'github.com/openstack/charms.ceph.git.*$'github.com/openstack/charms.ceph.git@stable/$ceph_release#egg=charms.ceph'g" $file
            sed -i "s'github.com/openstack/charms.openstack.git.*$'github.com/openstack/charms.openstack.git@stable/$openstack_release#egg=charms.openstack'g" $file
            set -e
        fi
    done
}


# run in the charm directory
function ensure_libs_ops {
    local openstack_release=$1
    local ceph_release=$2
    echo "Updating test-requirements.txt in repository with stable Zaza"
    for file in requirements.txt test-requirements.txt requirements-dev.txt src/test-requirements; do
        if [ -e "$file" ]; then
            set +e
            sed -i "s'openstack-charmers/zaza.git.*$'openstack-charmers/zaza.git@stable/$openstack_release#egg=zaza'g" $file
            sed -i "s'openstack-charmers/zaza-openstack-tests.git.*$'openstack-charmers/zaza-openstack-tests.git@stable/$openstack_release#egg=zaza.openstack'g" $file
            sed -i "s'github.com/juju/charm-helpers.*$'github.com/juju/charm-helpers@stable/$openstack_release#egg=charmhelpers'g" $file
            sed -i "s'github.com/openstack/charms.ceph.git.*$'github.com/openstack/charms.ceph.git@stable/$ceph_release#egg=charms.ceph'g" $file
            set -e
        fi
    done
}
