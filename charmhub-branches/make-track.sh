#!/usr/bin/env bash

#set -ex

script_dir="$( cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"

charm="${1}"
track="${2}"

if [ -z "${charm}" ]; then
    echo "usage: ${0} {charm-name} {track-name}"
    exit 1
fi

# get the charmhub token
source ${script_dir}/export-token.sh

API_LIST="https://api.charmhub.io/v1/charm/${charm}"
API_MAKE_TRACK="https://api.charmhub.io/v1/charm/${charm}/tracks"

CURL=`which curl`

if [ -z "$CURL" ]; then
    echo "curl is needed for this script."
    exit 1
fi

# get a list of the tracks
result=$(curl $API_LIST -s -H'Content-type: application/json' -H "$CHARMHUB_MACAROON_HEADER")

if [[ "$result" == *"error-list"* ]]; then
    echo "Error in result; perhaps the charm name is wrong?"
    echo "result is: '$result'"
    exit 1
fi

tracks=$(echo $result | jq -r '.metadata.tracks[] | .name')

readarray -t arr_tracks < <(echo "$tracks")

# check the new track doesn't exist
for i in "${arr_tracks[@]}"; do
    if [[ "$i" == "$track" ]]; then
        echo "track '$track' already exists."
        exit 1
    fi
done

# now make the track.
result=$(curl $API_MAKE_TRACK -s -H'Content-type: application/json' -H "$CHARMHUB_MACAROON_HEADER" -d '[{"name": "'$track'"}]')

# check if it worked
if [[ "$result" == *"error-list"* ]]; then
    echo "Error in result; perhaps the track is illegal?"
    echo "result is: '$result'"
    exit 1
fi

echo "$charm: $track - created."
