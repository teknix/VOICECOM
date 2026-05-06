import os

LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")
LIVEKIT_HOST = os.environ.get("LIVEKIT_HOST", "ws://localhost:7880")
LIVEKIT_INTERNAL_URL = os.environ.get("LIVEKIT_INTERNAL_URL", "http://localhost:7880")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/voicesystem")
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", "/recordings")

# Zulip Integration
ZULIP_URL = os.environ.get("ZULIP_URL", "")
ZULIP_EMAIL = os.environ.get("ZULIP_EMAIL", "")
ZULIP_API_KEY = os.environ.get("ZULIP_API_KEY", "")

# Super Admin (Recovery)
SUPER_ADMIN_EMAIL = os.environ.get("SUPER_ADMIN_EMAIL", "admin@voicecom.local")
SUPER_ADMIN_HASH = os.environ.get("SUPER_ADMIN_HASH", "") # bcrypt hash
