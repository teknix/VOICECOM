#!/bin/bash
# Mumble NextGen: Load Test Spike
# This script uses the official LiveKit load-tester to simulate 2,000 subscribers.

set -e

# Load environment variables
if [ -f .env ]; then
  # Source .env safely
  set -a
  source .env
  set +a
else
  echo "Error: .env file not found. Run scripts/setup_dev.sh first."
  exit 1
fi

ROOM_ID=${1:-sector-northwest}
NUM_USERS=${2:-2000}

# Calculate subscribers manually to avoid command substitution in the shell tool if possible, 
# though inside the script it should be fine.
SUB_COUNT=$((NUM_USERS - 1))

echo "--- Mumble NextGen: Load Test Spike ---"
echo "Target Room: $ROOM_ID"
echo "Simulating $NUM_USERS users..."

# Note: We simulate 1 publisher and N-1 subscribers to test the SFU load.
# We use the internal Docker network 'voice_voice' created by docker-compose.

docker run --rm \
  --network voicecom_voice \
  livekit/load-tester \
  -url http://livekit:7880 \
  -api-key "$LIVEKIT_API_KEY" \
  -api-secret "$LIVEKIT_API_SECRET" \
  -room "$ROOM_ID" \
  -publishers 1 \
  -subscribers "$SUB_COUNT" \
  -duration 5m \
  -video-resolution vga

echo "--- Load Test Finished ---"
