import os

LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")
LIVEKIT_HOST = os.environ.get("LIVEKIT_HOST", "ws://localhost:7880")
LIVEKIT_INTERNAL_URL = os.environ.get("LIVEKIT_INTERNAL_URL", "http://localhost:7880")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/voicesystem")
