#!/bin/bash

# Add py37 back into the tox.ini

# delete py37 section
function delete_python37_in_tox {
    local tox_file=$1
    sed -i "/^\[testenv:py37\]/,+4d" $tox_file
}

# Add correct py37 back
function add_python37_to_tox {
    local tox_file=$1
    grep -q testenv:py37 $tox_file || {
        block="[testenv:py37]\nbasepython = python3.7\ndeps = -r{toxinidir}/test-requirements.txt\ncommands = stestr run --slowest {posargs}\n"
        sed -i "/^\[testenv:py38\]/i $block" $tox_file
    }
}


delete_python37_in_tox tox.ini
add_python37_to_tox tox.ini

