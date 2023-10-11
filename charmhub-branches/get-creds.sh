#!/usr/bin/env bash
script_dir="$( cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"

charmcraft login --export ${script_dir}/charmhub-creds.dat
