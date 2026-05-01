#!/bin/sh
# Run once to vendor the livekit-client UMD build into static/
# Requires curl and node/npm OR just curl if using the CDN URL directly.
set -e
VERSION=$(npm show livekit-client version 2>/dev/null || echo "2.5.7")
curl -fsSL "https://cdn.jsdelivr.net/npm/livekit-client@${VERSION}/dist/livekit-client.umd.min.js" \
  -o "$(dirname "$0")/livekit-client.umd.min.js"
echo "Downloaded livekit-client@${VERSION} -> static/livekit-client.umd.min.js"
