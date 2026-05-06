#!/bin/bash
set -e

echo "--- Mumble NextGen: Dev Setup ---"

# 1. Check dependencies
command -v docker >/dev/null 2>&1 || { echo >&2 "Docker required but not found. Aborting."; exit 1; }
command -v docker-compose >/dev/null 2>&1 || docker compose version >/dev/null 2>&1 || { echo >&2 "Docker Compose required but not found. Aborting."; exit 1; }

# 2. Setup .env
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    
    # Generate random secrets
    GEN_LK_KEY=$(LC_ALL=C tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w 16 | head -n 1)
    GEN_LK_SEC=$(LC_ALL=C tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w 32 | head -n 1)
    GEN_FLASK=$(LC_ALL=C tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w 24 | head -n 1)
    GEN_PASS=$(LC_ALL=C tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w 12 | head -n 1)
    GEN_MOD_PASS=$(LC_ALL=C tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w 12 | head -n 1)

    sed -i "s/^LIVEKIT_API_KEY=.*/LIVEKIT_API_KEY=$GEN_LK_KEY/" .env
    sed -i "s/^LIVEKIT_API_SECRET=.*/LIVEKIT_API_SECRET=$GEN_LK_SEC/" .env
    sed -i "s/^FLASK_SECRET_KEY=.*/FLASK_SECRET_KEY=$GEN_FLASK/" .env
    sed -i "s/^ACCESS_PASSPHRASE=.*/ACCESS_PASSPHRASE=$GEN_PASS/" .env
    echo "MOD_PASSPHRASE=$GEN_MOD_PASS" >> .env
else
    echo ".env already exists, skipping generation."
fi

# 3. Download client JS
echo "Downloading LiveKit client..."
./static/download_livekit_client.sh

# 4. Pull/Build containers
echo "Building containers..."
docker compose build

# 5. Seed MongoDB (Room metadata)
echo "Seeding MongoDB..."
docker compose up -d mongo
# Wait for mongo
until docker compose exec mongo mongosh --eval "print('waited for connectivity')" > /dev/null 2>&1; do
  sleep 1
done

# Seed sectors
docker compose exec mongo mongosh voicesystem --eval '
db.rooms.deleteMany({});
db.rooms.insertMany([
  { "_id": "sector-northwest", "display_name": "Sector Northwest", "mode": "discussion", "active": true, "presenter_ids": [] },
  { "_id": "sector-north", "display_name": "Sector North", "mode": "discussion", "active": true, "presenter_ids": [] },
  { "_id": "ops-center", "display_name": "Operations Center", "mode": "broadcast", "active": true, "presenter_ids": [] }
]);
db.rooms.createIndex({ "active": 1 });
'

echo "--- Setup Complete ---"
echo "Run 'docker compose up' to start the system."
