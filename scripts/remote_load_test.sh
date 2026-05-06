#!/bin/bash
LK_URL=$1
NUM_USERS=$2
TOKEN=$3
for i in $(seq 1 $NUM_USERS); do
  docker run -d -e LIVEKIT_URL="$LK_URL" -e TOKEN="$TOKEN" loadtest-client
done
