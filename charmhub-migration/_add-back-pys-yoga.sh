#!/bin/bash

# Add py39 back into the tox.ini

# update tox.ini to include python3.9
function add_python39_to_tox {
    local tox_file=$1
    grep -q testenv:py39 $tox_file || {
        block="[testenv:py39]\nbasepython = python3.9\ndeps = -r{toxinidir}/test-requirements.txt\ncommands = stestr run --slowest {posargs}\n"
        sed -i "/^\[testenv:py310\]/i $block" $tox_file
    }
}

# update tox.ini to include python3.6
function add_python36_to_tox {
    local tox_file=$1
    grep -q testenv:py36 $tox_file || {
        block="[testenv:py36]\nbasepython = python3.9\ndeps = -r{toxinidir}/test-requirements.txt\ncommands = stestr run --slowest {posargs}\n"
        sed -i "/^\[testenv:py38\]/i $block" $tox_file
    }
}


add_python36_to_tox tox.ini
add_python39_to_tox tox.ini
