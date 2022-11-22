#!/bin/bash -u

function print_usage {
  echo "Usage example:"
  echo "    ${0} "
}


#set -e     # Enabling this can break the script for any newly introduced charms
CLEAN=0
LAST_REF=master
BASE_DIR=
declare -A BASELINE_BRANCHES
# parse cli arguments
while (($# > 0))
do
  case "$1" in
    --clean)
      CLEAN=1
      ;;
    --os-baseline)
      BASELINE_BRANCHES["openstack"]=$2
      shift
      ;;
    --ovn-baseline)
      BASELINE_BRANCHES["ovn"]=$2
      shift
      ;;
    --ceph-baseline)
      BASELINE_BRANCHES["ceph"]=$2
      shift
      ;;
    --libs-dir)
      BASE_DIR=$2
      shift
      ;;
    *)
      echo "ERROR: invalid input '$1'"
      print_usage
      exit 1
      ;;
  esac
  shift
done

if [ -z $BASE_DIR ] || [ "${#BASELINE_BRANCHES[@]}" -eq 0 ]; then
  print_usage
fi

function log {
  echo "$(date '+%H:%M:%S') $@" >&2
}


RELEASE_TOOLS_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
# directory where there are git clones of the repositories
CHARMS_DIR=$RELEASE_TOOLS_DIR/charms

EXTRA_DIRS=("${BASE_DIR}/release-tools"
           "${BASE_DIR}/charms.openstack"
           "${BASE_DIR}/charms.ceph"
           "${BASE_DIR}/charm-guide"
           "${BASE_DIR}/charm-deployment-guide")

# Update each repository (needed?)
for DIR in ${EXTRA_DIRS[@]}; do
  log "updating repository ${DIR}"
  git -C $DIR pull --ff-only origin master
done

ALL_CONTRIBUTORS_FILE=$(mktemp -t "users_tmp.XXXX")
SUMMARY_FILE=$(mktemp -t "users-summary.XXXX")

# Clean up before collecting stats.
rm $ALL_CONTRIBUTORS_FILE
if [ $CLEAN == 1 ]; then
  rm -rf $CHARMS_DIR
fi

pushd $RELEASE_TOOLS_DIR

for GROUP in "${!BASELINE_BRANCHES[@]}"; do
  ./fetch-charms.py -s "${GROUP}" -d $CHARMS_DIR/${GROUP}/

  for DIR in ${CHARMS_DIR}/${GROUP}/*/; do
    log "Processing charm ${DIR}..."
    git -C $DIR log --format="%an" origin/stable/"${BASELINE_BRANCHES[$GROUP]}"..${LAST_REF} 2>/dev/null >> $ALL_CONTRIBUTORS_FILE
  done
done

# Libraries
for DIR in ${EXTRA_DIRS[@]}; do
  log "Processing repository ${DIR}"
  git -C $DIR log --format="%an" origin/stable/"${BASELINE_BRANCHES[openstack]}"..master 2>/dev/null >> $ALL_CONTRIBUTORS_FILE
done

# Collate the results
cat $ALL_CONTRIBUTORS_FILE | grep -v Zuul | sort | uniq > "${SUMMARY_FILE}"
CONTRIB_NUMBER=$(wc -l $SUMMARY_FILE | awk '{print $1}')

echo -e "\n${CONTRIB_NUMBER} different people contributed since release ${BASELINE_BRANCHES[@]}."
echo ""
cat ${SUMMARY_FILE}
