#!/bin/bash -e
# Helpers for functionality that can be shared within release-tools

function retry() {
  n=0
  base_delay=3
  delay=$base_delay
  until [ $n -ge 3 ]
  do
    $@ && break
    n=$[$n+1]
    echo "Going to try again in ${delay} seconds"
    sleep $delay
    delay=$(( $base_delay**($n+1) ))
  done
}
