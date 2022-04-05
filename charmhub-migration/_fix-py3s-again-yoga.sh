#!/bin/bash

# Fix py36 back into the tox.ini

# delete py36 section
function delete_python36_in_tox {
    local tox_file=$1
    sed -i "/^\[testenv:py36\]/,+4d" $tox_file
}

# Add correct py36 back
function add_python36_to_tox {
    local tox_file=$1
    grep -q testenv:py36 $tox_file || {
        block="[testenv:py36]\nbasepython = python3.6\ndeps = -r{toxinidir}/requirements.txt\n       -r{toxinidir}/test-requirements.txt\ncommands = stestr run --slowest {posargs}\n"
        sed -i "/^\[testenv:py38\]/i $block" $tox_file
    }
}

# delete py38 section
function delete_python38_in_tox {
    local tox_file=$1
    sed -i "/^\[testenv:py38\]/,+4d" $tox_file
}

# Add correct py36 back
function add_python38_to_tox {
    local tox_file=$1
    grep -q testenv:py38 $tox_file || {
        block="[testenv:py38]\nbasepython = python3.8\ndeps = -r{toxinidir}/requirements.txt\n       -r{toxinidir}/test-requirements.txt\ncommands = stestr run --slowest {posargs}\n"
        sed -i "/^\[testenv:py310\]/i $block" $tox_file
    }
}

# delete py310 section
function delete_python310_in_tox {
    local tox_file=$1
    sed -i "/^\[testenv:py310\]/,+4d" $tox_file
}

# Add correct py36 back
function add_python310_to_tox {
    local tox_file=$1
    grep -q testenv:py310 $tox_file || {
        block="[testenv:py310]\nbasepython = python3.10\ndeps = -r{toxinidir}/requirements.txt\n       -r{toxinidir}/test-requirements.txt\ncommands = stestr run --slowest {posargs}\n"
        sed -i "/^\[testenv:pep8\]/i $block" $tox_file
    }
}

delete_python36_in_tox tox.ini
add_python36_to_tox tox.ini
delete_python38_in_tox tox.ini
add_python38_to_tox tox.ini
delete_python310_in_tox tox.ini
add_python310_to_tox tox.ini

