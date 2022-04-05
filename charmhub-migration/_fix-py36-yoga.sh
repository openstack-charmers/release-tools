#!/bin/bash

# Add py39 back into the tox.ini

# delete py36 section
function delete_python36_in_tox {
    local tox_file=$1
    sed -i "/^\[testenv:py36\]/,+4d" $tox_file
}

# Add correct py36 back
function add_python36_to_tox {
    local tox_file=$1
    grep -q testenv:py36 $tox_file || {
        block="[testenv:py36]\nbasepython = python3.6\ndeps = -r{toxinidir}/test-requirements.txt\ncommands = stestr run --slowest {posargs}\n"
        sed -i "/^\[testenv:py38\]/i $block" $tox_file
    }
}


delete_python36_in_tox tox.ini
add_python36_to_tox tox.ini

