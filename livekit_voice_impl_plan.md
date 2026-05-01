# LiveKit Voice System — Implementation Plan
**Target:** Coding Agent Handoff  
**Project Type:** Greenfield — Browser-based Mumble replacement  
**Organization Scale:** 2000+ members, ~50 users/channel, 200–500 concurrent active users  
**Stack:** Flask · MongoDB · Docker · LiveKit · LiveKit Egress · coturn (TURN)  
**Auth:** Startup passphrase (test mode) — Authentik OIDC deferred to production integration  
**Python deps:** flask, livekit-server-sdk, pymongo, gunicorn, gevent, flask-limiter, flask-wtf  

---

## Architecture Overview

```
Browser Client (vanilla JS)
        │
        ▼
Flask App (token issuer + room manager)
        │
        ├──► Passphrase + display name entry (Flask session)
        │
        ├──► MongoDB (room records, recording metadata, audit log)
        │
        └──► LiveKit Server (SFU)
                    │
                    └──► LiveKit Egress (recording service)
```

> **Test mode note:** Authentik OIDC is intentionally omitted. Auth is a startup-defined passphrase. Role is selected by the user at login (member / moderator / admin) and stored in Flask session — no external identity provider required. Replace Phase 2 entirely when integrating into production.

---

## Phase 1 — Infrastructure Setup

### 1.1 Docker Compose Services

Define the following services in `docker-compose.yml`:

| Service | Image | Notes |
|---|---|---|
| `livekit` | `livekit/livekit-server` | SFU core — depends_on: redis |
| `livekit-egress` | `livekit/egress` | Recording service — depends_on: livekit |
| `redis` | `redis:7-alpine` | Required by LiveKit for room state |
| `flask` | Custom build | Token API + room management — depends_on: mongo |
| `mongo` | `mongo:7` | Room records + audit log |
| `coturn` | `coturn/coturn` | TURN relay for users behind restrictive firewalls |

LiveKit and Egress must share a Docker network. Redis is internal only.

**Flask container command:**
```
gunicorn --worker-class=gevent --workers=4 --worker-connections=100 --bind 0.0.0.0:5000 "app:create_app()"
```

**`depends_on` ordering is required** — LiveKit needs Redis running first; Egress needs LiveKit; Flask needs MongoDB.

### 1.2 LiveKit Server Config (`livekit.yaml`)

```yaml
port: 7880
rtc:
  tcp_port: 7881
  udp_port: 7882
  # REQUIRED: set node_ip to the server's LAN or public IP so WebRTC clients
  # can reach it. Without this, LiveKit advertises its internal Docker IP and
  # clients outside the Docker host get no audio.
  # Option A: use_external_ip: true  (if server has a routable public IP)
  # Option B: node_ip: <YOUR_SERVER_IP>  (explicit LAN/private IP)
  use_external_ip: false  # change to true OR set node_ip before first deploy
  # node_ip: 192.168.1.x
  turn_servers:
    - host: coturn
      port: 3478
      protocol: udp
      username: <coturn_user>
      credential: <coturn_pass>
redis:
  address: redis:6379
keys:
  API_KEY: <generated>  # store in .env
  API_SECRET: <generated>
room:
  max_participants: 55  # 50 members + 5 headroom
webhook:
  api_key: <same as above>
  urls:
    - http://flask:5000/livekit/webhook
```

### 1.3 Egress Config (`egress.yaml`)

```yaml
api_key: <same as livekit>
api_secret: <same as livekit>
ws_url: ws://livekit:7880
file_outputs:  # NOTE: plural — not file_output
  local:
    path: /recordings  # mount as Docker volume
```

Mount `/recordings` as a named volume accessible to Flask for serving files.

### 1.4 Environment Variables (`.env`)

```
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
LIVEKIT_HOST=ws://livekit:7880
LIVEKIT_INTERNAL_URL=http://livekit:7880
ACCESS_PASSPHRASE=           # set at server start — required, no default
MONGO_URI=mongodb://mongo:27017/voicesystem
FLASK_SECRET_KEY=
```

`ACCESS_PASSPHRASE` must be set as an environment variable before the Flask container starts. If absent, the app must refuse to start with a clear error. There is no fallback value.

---

## Phase 2 — Passphrase Authentication (Test Mode)

### 2.1 Login Flow

The login page presents **two fields** (no role dropdown — role is resolved server-side):
- **Display name** — free text, stored in session as `session["display_name"]`
- **Passphrase** — single shared secret set at server start

On POST `/auth/login`:
1. Compare submitted passphrase against `os.environ["ACCESS_PASSPHRASE"]` using `hmac.compare_digest` (timing-safe)
2. If match: populate session with `display_name`, `role`, `user_id` (generate a random UUID per session)
3. If no match: re-render login with generic error, no detail about why

### 2.2 Auth Implementation (`auth.py`)

```python
import os, hmac, uuid
from flask import Blueprint, request, session, redirect, render_template

auth_bp = Blueprint("auth", __name__)

PASSPHRASE = os.environ.get("ACCESS_PASSPHRASE")
if not PASSPHRASE or not PASSPHRASE.strip():
    raise RuntimeError("ACCESS_PASSPHRASE must be set to a non-empty value. Refusing to start.")

limiter = Limiter(get_remote_address, app=None)  # attach to app in create_app()

@auth_bp.route("/auth/login", methods=["GET", "POST"])
@limiter.limit("5/minute")
def login():
    if request.method == "POST":
        submitted = request.form.get("passphrase", "")
        if hmac.compare_digest(submitted, PASSPHRASE):
            display_name = request.form.get("display_name", "Anonymous").strip()
            session.clear()  # prevent session fixation
            session["user_id"] = str(uuid.uuid4())
            session["display_name"] = display_name
            session["role"] = resolve_role(display_name)  # exact match, no normalization
            return redirect("/")
        return render_template("login.html", error="Invalid passphrase.")
    return render_template("login.html")

@auth_bp.route("/auth/logout")
def logout():
    session.clear()
    return redirect("/auth/login")
```

### 2.3 Privileged Username Registry

Role is determined server-side by display name, not the role dropdown. The dropdown is ignored entirely — role is assigned at login based on this registry:

```python
# auth.py

PRIVILEGED_USERS = {
    "teknix": "admin",
    "co-pilot": "moderator",
}

def resolve_role(display_name: str) -> str:
    return PRIVILEGED_USERS.get(display_name, "member")
```

On successful passphrase validation, call `resolve_role(display_name)` and store the result in `session["role"]`. The role dropdown should be removed from the login form entirely — it is not used.

> **Exact match enforced.** `"Teknix"`, `"TEKNIX"`, `"Co-Pilot"` will all resolve to `"member"`. No normalization is applied.

---

### 2.5 Login Required Decorator (`middleware.py`)

```python
from functools import wraps
from flask import session, redirect

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/auth/login")
        return f(*args, **kwargs)
    return decorated

def mod_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/auth/login")
        if session.get("role") not in ("moderator", "admin"):
            return ("Forbidden", 403)
        return f(*args, **kwargs)
    return decorated
```

### 2.6 Role Behavior

| Role | Can publish audio | Can change room mode | Can record | Can mute others |
|---|---|---|---|---|
| member | Discussion only | No | No | No |
| moderator | Yes | Yes | Yes | Yes |
| admin | Yes | Yes | Yes | Yes |

> **Production swap:** Replace this entire phase with Authentik OIDC. Session keys (`user_id`, `display_name`, `role`) are intentionally named to match what the OIDC flow will populate — the rest of the app does not need to change.

---

## Phase 3 — Flask Backend

### 3.1 Project Structure

```
app/
├── __init__.py          # Flask app factory (init limiter, CSRFProtect, register blueprints)
├── auth.py              # Passphrase login/logout (test mode)
├── rooms.py             # Room listing, metadata, mode toggle, presenter management
├── tokens.py            # LiveKit token issuance
├── recordings.py        # Egress start/stop/list/download
├── webhook.py           # LiveKit webhook receiver (recording/room events)
├── admin.py             # Admin dashboard
├── models.py            # MongoDB document schemas + index creation
├── middleware.py        # Auth required decorator
├── config.py            # Shared env-var config (LIVEKIT_API_KEY, LIVEKIT_API_SECRET, etc.)
└── templates/
    └── voice.html       # Single-page client (includes {{ livekit_url }} Jinja var)
    └── admin.html       # Admin dashboard template
```

### 3.2 MongoDB Collections

**`rooms` collection:**
```json
{
  "_id": "sector-northwest",
  "display_name": "Northwest Sector",
  "mode": "discussion",          // "discussion" | "broadcast"
  "active": true,
  "created_at": "<timestamp>",
  "presenter_ids": []            // user_ids with explicit presenter grant (mod-assigned)
}
```

**`recordings` collection:**
```json
{
  "_id": "<egress_id>",
  "room_id": "sector-northwest",
  "started_by": "<user_id>",     // session["user_id"] — UUID, NOT display name
  "started_at": "<timestamp>",
  "stopped_at": null,
  "file_path": "/recordings/<filename>.mp4",  // sanitize before send_file(): basename only
  "status": "active"             // "active" | "complete" | "failed"
}
```

**Required MongoDB indexes** (create in `models.py` at startup):
```python
db.recordings.create_index([("room_id", 1)])
db.recordings.create_index([("started_by", 1)])
db.recordings.create_index([("status", 1)])
db.audit_log.create_index([("room_id", 1), ("timestamp", -1)])
```

**`audit_log` collection:**
```json
{
  "event": "recording_started",
  "room_id": "sector-northwest",
  "actor": "<user_sub>",
  "timestamp": "<timestamp>",
  "meta": {}
}
```

### 3.3 Token Issuance (`tokens.py`)

Use the `livekit-server-sdk` Python package.

```python
import os
from datetime import timedelta
from livekit import api
from .models import db

LIVEKIT_API_KEY = os.environ["LIVEKIT_API_KEY"]
LIVEKIT_API_SECRET = os.environ["LIVEKIT_API_SECRET"]
TOKEN_TTL = timedelta(hours=4)

def issue_token(user_id: str, display_name: str, room_id: str, role: str) -> str:
    # Always look up current room mode from DB — never trust client-supplied mode
    room = db.rooms.find_one({"_id": room_id})
    if not room:
        raise ValueError(f"Room {room_id!r} not found")
    mode = room["mode"]
    presenter_ids = room.get("presenter_ids", [])

    grants = api.VideoGrants(room_join=True, room=room_id)

    if mode == "broadcast":
        is_presenter = role in ("admin", "moderator") or user_id in presenter_ids
        if is_presenter:
            grants.can_publish = True
            grants.can_publish_data = True
        else:
            grants.can_publish = False
            grants.can_subscribe = True
    else:
        # Discussion mode — everyone can publish
        grants.can_publish = True
        grants.can_subscribe = True
        grants.can_publish_data = True

    token = api.AccessToken(
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET
    ).with_identity(user_id)\
     .with_name(display_name)\
     .with_grants(grants)\
     .with_ttl(TOKEN_TTL)\
     .to_jwt()

    return token
```

### 3.4 API Endpoints

| Method | Path | Auth Required | Description |
|---|---|---|---|
| GET | `/auth/login` | No | Render login form |
| POST | `/auth/login` | No | Validate passphrase, set session (rate-limited 5/min) |
| GET | `/auth/logout` | Yes | Clear session |
| GET | `/api/me` | Yes | Return `{user_id, display_name, role}` from session |
| GET | `/api/rooms` | Yes | List all rooms with current participant counts |
| POST | `/api/token` | Yes | Issue LiveKit JWT — fetches room.mode from DB |
| POST | `/api/rooms/<id>/mode` | Mod/Admin | Switch broadcast/discussion (LiveKit first, then DB) |
| POST | `/api/rooms/<id>/mute` | Mod/Admin | Server-side mute a participant via LiveKit API |
| POST | `/api/rooms/<id>/presenter` | Mod/Admin | Grant/revoke presenter status `{user_id, action: grant\|revoke}` |
| POST | `/api/recordings/start` | Mod/Admin | Start Egress recording |
| POST | `/api/recordings/stop` | Mod/Admin | Stop active recording |
| GET | `/api/recordings` | Mod/Admin | List recordings for a room |
| GET | `/api/recordings/<id>/download` | Mod/Admin | Signed download URL for a recording file |
| POST | `/livekit/webhook` | Internal | LiveKit event receiver (HMAC-verified) |
| GET | `/admin` | Admin | Ops dashboard: rooms, participants, recordings, health |
| GET | `/` | Yes | Serve voice.html |

### 3.5 Room Mode Toggle

When a moderator switches mode, **call LiveKit FIRST, then write MongoDB** to prevent inconsistent state on failure:

1. Fetch current participant list from LiveKit Server API (`list_participants`)
2. Call `update_participant` for all participants in **parallel** using `gevent.pool.Pool`:
   - Broadcast: revoke publish from all non-presenter, non-mod participants
   - Discussion: grant publish to all participants
   - Use `pool.map(update_fn, participants)` — do NOT call sequentially (50 calls × 100ms = 5s timeout)
3. If LiveKit calls succeed: update `rooms.mode` in MongoDB
4. If LiveKit calls fail: return 500, do NOT write MongoDB (state stays consistent)
5. Emit a LiveKit data message `{type: "mode_change", mode: <new_mode>}` to notify clients

The SDK call for step 2 is `RoomServiceClient.update_participant(room_name, identity, permission=ParticipantPermission(...))`.

**Presenter check in broadcast mode:** A participant can publish if `role in ("admin", "moderator")` OR `user_id in room.presenter_ids`.

### 3.6 Recording Endpoints (`recordings.py`)

**Start:**
```python
# POST /api/recordings/start
# Body: { "room_id": "sector-northwest" }
# 1. Check no active recording for this room (return 409 if exists)
# 2. Call EgressServiceClient.start_room_composite_egress() → get egress_id
# 3. Write recording doc to MongoDB
#    If MongoDB write fails: IMMEDIATELY call EgressServiceClient.stop_egress(egress_id)
#    as compensation to prevent orphaned recordings. Log both the failure and compensation.
# 4. Write to audit_log
```

**Stop:**
```python
# POST /api/recordings/stop
# Body: { "egress_id": "<id>" }
# 1. Fetch recording from MongoDB by _id=egress_id — return 404 if not found
# 2. Call EgressServiceClient.stop_egress(egress_id) — return 500 if fails
# 3. Update recordings: stopped_at, status="complete"
# 4. Write to audit_log
```

**Download:**
```python
# GET /api/recordings/<id>/download  (mod/admin only)
# 1. Fetch recording from MongoDB by _id
# 2. Sanitize file_path: use os.path.basename() only — NEVER pass raw DB value to send_file()
#    safe_name = os.path.basename(recording["file_path"])
#    full_path = os.path.join("/recordings", safe_name)
# 3. Return send_file(full_path, as_attachment=True)
```

Use `livekit-server-sdk` `EgressServiceClient` for all Egress calls.

### 3.7 LiveKit Webhook Handler (`webhook.py`)

LiveKit pushes events to `POST /livekit/webhook`. Verify the HMAC signature using `WebhookReceiver` from the SDK before processing.

```python
from livekit.api import WebhookReceiver

receiver = WebhookReceiver(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)

# POST /livekit/webhook  (no login_required — LiveKit internal call)
def livekit_webhook():
    try:
        event = receiver.receive(request.data, request.headers.get("Authorization"))
    except Exception:
        return "", 401  # bad signature — reject silently

    if event.event == "egress_ended":
        db.recordings.update_one(
            {"_id": event.egress_info.egress_id},
            {"$set": {"status": "complete", "stopped_at": now()}}
        )
    elif event.event == "egress_started":
        # Confirm egress is tracked — safety net if start endpoint missed it
        pass
    # Log all events to audit_log for debugging
    return "", 200
```

### 3.8 Presenter Management (`rooms.py`)

```python
# POST /api/rooms/<id>/presenter  (mod/admin only)
# Body: { "user_id": "<id>", "action": "grant" | "revoke" }
# 1. Update presenter_ids in MongoDB ($addToSet or $pull)
# 2. Call update_participant on the live room to update their grants immediately
# 3. Write to audit_log
```

### 3.9 Admin Dashboard (`admin.py`)

```python
# GET /admin  (admin only)
# Renders admin.html with:
#   - Active rooms (from MongoDB rooms where active=true) + participant counts (from LiveKit list_rooms API)
#   - Active recordings (from MongoDB recordings where status="active")
#   - LiveKit health: GET http://livekit:7880/  — 200 = healthy
#   - Recent audit log entries (last 20)
```

---

## Phase 4 — Browser Client

### 4.1 Dependencies (vendor into static/)

Do NOT load livekit-client from CDN — internal/offline deployments will fail. Vendor the UMD build:

```
static/
└── livekit-client.umd.min.js   # download from npm, commit to repo
```

Download once:
```bash
npm pack livekit-client --dry-run  # find latest version
curl -o static/livekit-client.umd.min.js \
  https://cdn.jsdelivr.net/npm/livekit-client/dist/livekit-client.umd.min.js
```

Reference in template:
```html
<script src="{{ url_for('static', filename='livekit-client.umd.min.js') }}"></script>
```

### 4.2 Client Flow

The Flask template must deliver the LiveKit WebSocket URL to the browser via a Jinja template variable — **do not hardcode** the URL in JS:

```html
<!-- voice.html — rendered by Flask -->
<script>
  const LIVEKIT_WS_URL = "{{ livekit_url }}";  // set from LIVEKIT_HOST env var in route handler
</script>
```

In `app/__init__.py` or the route handler:
```python
@app.route("/")
@login_required
def index():
    return render_template("voice.html", livekit_url=os.environ["LIVEKIT_HOST"])
```

Client flow:
1. Page load → check session via `/api/me` (Flask returns user info or 401)
2. If 401 → redirect to `/auth/login`
3. Display full room list from `/api/rooms`
4. User selects room → POST `/api/token` → receive `{ token }`
5. Connect to LiveKit: `room.connect(LIVEKIT_WS_URL, token)` — uses vendored `LivekitClient.Room`
6. Render participant list and audio elements
7. Handle LiveKit events: `participantConnected`, `participantDisconnected`, `trackSubscribed`, `dataReceived`

**Disconnection / reconnection handling:**
```javascript
room.on(LivekitClient.RoomEvent.Disconnected, async (reason) => {
  console.warn("Disconnected:", reason);
  let attempts = 0;
  const maxAttempts = 5;
  while (attempts < maxAttempts) {
    await new Promise(r => setTimeout(r, 2000 * Math.pow(2, attempts)));
    try {
      const resp = await fetch("/api/token", { method: "POST", ... });
      const { token } = await resp.json();
      await room.connect(LIVEKIT_WS_URL, token);
      return;
    } catch (e) { attempts++; }
  }
  showReconnectFailedBanner();
});
```

### 4.3 UI Modes

**Broadcast Mode:**
- Presenter controls visible only to presenters/mods/admins
- Members see muted mic indicator — no publish controls
- "Hand raise" button for members (sends data message to presenter)

**Discussion Mode:**
- All participants have mic toggle
- Push-to-talk keybinding: **Caps Lock** (hold to talk, release to mute) — default key, not configurable in v1
  - `keydown` on Caps Lock → `localParticipant.setMicrophoneEnabled(true)`
  - `keyup` on Caps Lock → `localParticipant.setMicrophoneEnabled(false)`
  - Provide a toggle-mode button as fallback for users who prefer click-to-talk

**Hand raise message schema** (data channel):
```json
{ "type": "hand_raise", "user_id": "<session user_id>", "display_name": "<name>", "raised": true }
```
- Sent via `room.localParticipant.publishData(encoded, { reliable: true })`
- Received on presenter/mod side via `RoomEvent.DataReceived`; display toast or badge

### 4.4 Mode Change Handling

Listen for LiveKit data messages:
```javascript
room.on(LivekitClient.RoomEvent.DataReceived, (payload) => {
  const msg = JSON.parse(new TextDecoder().decode(payload));
  if (msg.type === "mode_change") updateUIMode(msg.mode);
  if (msg.type === "hand_raise") showHandRaiseBadge(msg);
});
```

### 4.5 Moderator Controls (visible to mod/admin only)

- Toggle room mode (broadcast ↔ discussion)
- Mute participant (server-side via Flask → LiveKit API)
- Start/stop recording
- View active participant list with roles

---

## Phase 5 — Security Constraints

1. **Token issuance is server-side only.** The client never touches API keys.
2. **All rooms accessible to all authenticated users in test mode.** Sector gating deferred to Authentik integration.
3. **Recording access is mod/admin only.** Enforced at the Flask middleware layer, not client-side.
4. **All Flask routes behind `@login_required` decorator** except `/auth/login`.
5. **LiveKit API key/secret never exposed to client.**
6. **Passphrase comparison uses `hmac.compare_digest`.** No plain string equality.
7. **Audit log every sensitive action:** recording start/stop, mode change, forced mute.
8. **Rate limiting on `/auth/login`:** 5 requests/minute per IP via Flask-Limiter. Initialize in `create_app()`:
   ```python
   from flask_limiter import Limiter
   from flask_limiter.util import get_remote_address
   limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
   limiter.init_app(app)
   ```
9. **CSRF protection via Flask-WTF:** Apply `CSRFProtect(app)` in `create_app()` for form-based routes.
   **IMPORTANT:** JSON API routes (`/api/*`) do NOT send CSRF tokens by default. Exempt them explicitly:
   ```python
   from flask_wtf.csrf import CSRFProtect
   csrf = CSRFProtect()
   csrf.init_app(app)
   # Exempt all JSON API endpoints from CSRF — they are authenticated by session cookie
   @app.after_request
   def exempt_api_csrf(response):
       return response
   # OR: use @csrf.exempt on each blueprint:
   csrf.exempt(api_blueprint)
   ```
   Only the login form (`/auth/login` POST) actually needs CSRF. All `/api/*` fetch() calls must be exempted.
10. **Recording path traversal prevention:** `os.path.basename()` on all `file_path` values from MongoDB before calling `send_file()`. Never pass raw DB string to `send_file()`.

---

## Phase 6 — Deployment Checklist

**Configuration:**
- [ ] Generate LiveKit API key/secret, store in `.env`
- [ ] Set `ACCESS_PASSPHRASE` in `.env` before starting containers (app refuses to start if absent)
- [ ] Set `LIVEKIT_HOST` to the correct WebSocket URL in `.env` (used by Jinja template for client)
- [ ] Set `node_ip` in `livekit.yaml` to the server's LAN or public IP (or `use_external_ip: true`)
- [ ] Set coturn `username` and `credential` in `livekit.yaml` and coturn config — must match

**Networking:**
- [ ] Open UDP 7882 (LiveKit WebRTC media) for external clients
- [ ] Open TCP/UDP 7880–7881 (LiveKit signaling) on server firewall
- [ ] Open UDP 3478 (coturn TURN/STUN) — required for corporate firewall users
- [ ] Open TCP/UDP 5349 (coturn TURN over TLS) — for HTTPS-only restricted networks
- [ ] Configure reverse proxy (Nginx/Apache) with WebSocket upgrade support for `/` path (LiveKit ws://)

**Storage:**
- [ ] Create Docker named volume for `/recordings`
- [ ] Verify the `livekit-egress` container has write permission on the recordings volume
- [ ] Verify the `flask` container has read permission on the same recordings volume
- [ ] Test: start a recording, confirm `.mp4` file appears in mounted volume path

**Database:**
- [ ] Seed MongoDB `rooms` collection with sector room documents (one doc per sector, `_id` = sector slug)
- [ ] Confirm MongoDB indexes are created at startup (check `models.py` index creation runs on `create_app()`)

**Verification:**
- [ ] `docker compose up` — all 6 services start without errors
- [ ] `GET http://localhost:7880/` returns 200 (LiveKit health)
- [ ] Login with passphrase → session is set, redirect to room list
- [ ] Join a room → audio works (check browser console for LiveKit connection logs)
- [ ] Moderator can start/stop recording — `.mp4` appears in volume
- [ ] Webhook receives `egress_ended` event — recording status updates to `complete`
- [ ] Download endpoint returns file correctly (not path traversal)
- [ ] Mode toggle: broadcast → members cannot publish; discussion → all can publish
- [ ] TURN connectivity: test with a client that has UDP blocked (use browser devtools to simulate)
- [ ] Rate limit: 6 failed login attempts from same IP → 429 response on the 6th

---

## Phase 7 — Test Spec

### 7.1 Unit Tests (`tests/unit/`)

| Test | What to assert |
|---|---|
| `test_resolve_role` | Exact-match display names return correct role; unrecognised names return `"member"` |
| `test_empty_passphrase_startup` | `RuntimeError` raised when `ACCESS_PASSPHRASE` is empty string or whitespace |
| `test_hmac_timing_safe` | `hmac.compare_digest` is called — string equality (`==`) is NOT used |
| `test_issue_token_discussion` | Returns JWT; both `can_publish` and `can_subscribe` are True |
| `test_issue_token_broadcast_member` | Returns JWT; `can_publish` is False, `can_subscribe` is True |
| `test_issue_token_broadcast_presenter` | Returns JWT; `can_publish` is True when `user_id` in `presenter_ids` |
| `test_issue_token_room_not_found` | Raises `ValueError` when room not in DB |
| `test_path_sanitization` | `os.path.basename("../../etc/passwd")` → `"passwd"` (traversal blocked) |
| `test_webhook_bad_signature` | Returns 401 when HMAC verification fails |
| `test_webhook_egress_ended` | Updates recording status to `"complete"` in MongoDB |

### 7.2 Integration Tests (`tests/integration/`)

These require a running MongoDB instance (use `mongomock` or test container — **no mocks for the DB layer**).

| Test | What to assert |
|---|---|
| `test_login_rate_limit` | 6th POST to `/auth/login` from same IP returns 429 |
| `test_login_session_fixation` | After login, session ID is different from pre-login session ID |
| `test_token_fetches_mode_from_db` | POST `/api/token` reads `rooms.mode` from MongoDB — does NOT accept client-supplied mode |
| `test_recording_orphan_compensation` | If MongoDB write fails after Egress starts, `stop_egress()` is called |
| `test_mode_toggle_livekit_first` | If LiveKit `update_participant` fails, MongoDB is NOT updated |
| `test_recording_download_path_traversal` | `GET /api/recordings/<id>/download` with a `file_path` containing `../` returns the correct file, not a parent directory file |
| `test_presenter_grant_updates_live_permissions` | POST `/api/rooms/<id>/presenter` calls `update_participant` and writes `presenter_ids` to MongoDB |

### 7.3 Test Setup Notes

- Mock `livekit.api.RoomServiceClient` and `EgressServiceClient` at the boundary — test the Flask logic, not LiveKit internals
- Use a dedicated test MongoDB database (`voicesystem_test`) — never the production database
- Tests must not depend on ordering — each test creates its own fixtures
- Rate-limit tests must reset Flask-Limiter storage between runs

**Python packages (`requirements.txt`):**
```
flask
livekit-server-sdk
pymongo
gunicorn
gevent          # gevent worker for gunicorn; gevent.pool.Pool for parallel LiveKit calls
flask-limiter   # rate limiting on /auth/login
flask-wtf       # CSRF protection for form routes
```

**Docker images:**
```
livekit/livekit-server:latest
livekit/egress:latest
redis:7-alpine
mongo:7
coturn/coturn   # TURN relay for users behind restrictive corporate firewalls
```

**Client (vendored into `static/`):**
```
livekit-client UMD build  # download from npm; do NOT load from CDN
```

---

## Notes for Coding Agent

- Do not introduce JWT session handling — use Flask server-side sessions with `flask.session`
- Do not add React or any frontend build tooling — vanilla JS + Jinja2 templates only
- Do not use any third-party SaaS — all services must be Docker-hosted
- MongoDB document IDs for rooms should be the sector slug (e.g. `sector-northwest`) not ObjectId — makes room lookups by sector trivial
- LiveKit Egress requires the `DISPLAY` environment variable set in its container — use Xvfb virtual display, which the official image handles internally but confirm in compose
- `recordings/` volume is shared between Egress (write) and Flask (read). Flask serves downloads via `send_file()` with `os.path.basename()` sanitization — never pass raw DB `file_path` strings to `send_file()`
