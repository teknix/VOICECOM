import os
import pytest
import mongomock

os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "devsecret0000000000000000000000000000000000")
os.environ.setdefault("LIVEKIT_HOST", "ws://localhost:7880")
os.environ.setdefault("LIVEKIT_INTERNAL_URL", "http://localhost:7880")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/voicesystem_test")
os.environ.setdefault("ACCESS_PASSPHRASE", "testpass")


@pytest.fixture(autouse=True)
def mock_mongo(monkeypatch):
    """Replace pymongo MongoClient with mongomock for all tests.

    Each app module does `from .models import db` at load time, giving it a
    local reference to the original real-MongoDB object. Patching app.models.db
    alone doesn't reach those copies — patch every module that holds one.
    """
    client = mongomock.MongoClient()
    db = client["voicesystem_test"]
    for target in [
        "app.models._client",
        "app.models._db",
        "app.models.db",
        "app.tokens.db",
        "app.rooms.db",
        "app.recordings.db",
        "app.webhook.db",
        "app.admin.db",
    ]:
        monkeypatch.setattr(target, db)
    yield db


@pytest.fixture
def app():
    from app import create_app
    application = create_app()
    application.config["TESTING"] = True
    application.config["WTF_CSRF_ENABLED"] = False
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def authed_client(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "user-001"
        sess["display_name"] = "TestUser"
        sess["role"] = "member"
    return client


@pytest.fixture
def mod_client(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "mod-001"
        sess["display_name"] = "TestMod"
        sess["role"] = "moderator"
    return client


@pytest.fixture
def admin_client(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "admin-001"
        sess["display_name"] = "TestAdmin"
        sess["role"] = "admin"
    return client


@pytest.fixture
def sample_room(mock_mongo):
    mock_mongo.rooms.insert_one({
        "_id": "sector-test",
        "display_name": "Test Sector",
        "mode": "discussion",
        "active": True,
        "presenter_ids": [],
    })
    return "sector-test"
