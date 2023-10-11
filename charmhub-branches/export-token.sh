#!/usr/bin/env bash
# this file is designed to be sourced.

if [ ! -f ./charmhub-creds.dat ]; then
    echo "Missing charmhub-creds.dat in this file.  Use get-creds.sh"
    exit 1
fi

BASE64=`which base64`
JQ=`which jq`

if [ -z "$BASE64" ]; then
    echo "No base64 executable."
    exit 1
fi

if [ -z "$JQ" ]; then
    echo "No jq executable."
    exit 1
fi


export CHARMHUB_MACAROON_HEADER="Authorization: Macaroon $(cat charmhub-creds.dat | base64 -d | jq -r .v)"
