#!/usr/bin/env bash

script_dir="$( cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"

charm="${1}"

if [ -z "${charm}" ]; then
    echo "usage: ${0} {charm-name}"
    exit 1
fi

# get the charmhub token
source ${script_dir}/export-token.sh

API="https://api.charmhub.io/v1/charm/${charm}"

CURL=`which curl`

if [ -z "$CURL" ]; then
    echo "curl is needed for this script."
    exit 1
fi
 
result=$(curl $API -s -H'Content-type: application/json' -H "$CHARMHUB_MACAROON_HEADER")

tracks=$(echo $result | jq -r '.metadata.tracks[] | .name')
echo "Tracks that exist for $charm are:"
echo "$tracks"


