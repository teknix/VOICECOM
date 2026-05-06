# LiveKit Voice System — Implementation Plan (FINAL)
**Target:** Coding Agent Handoff  
**Project Type:** Greenfield — Browser-based Mumble replacement (Pure Voice)  
**Organization Scale:** 2000+ members, 200–500 concurrent active users  
**Stack:** Flask · MongoDB · Docker · LiveKit · LiveKit Egress · coturn (TURN)  
**Auth:** Hierarchical Passphrase (admin/mod/op/member) — OIDC deferred to v2.0  

---

## 0. Key Strategy Decisions (CEO Review)
- **Pure Voice Only:** Video is completely removed to guarantee 2000-user performance.
- **Selective Subscriptions:** Clients only subscribe to audio for active speakers/stage.
- **State Lock Atomicity:** Mode switches (Broadcast/Discussion) use a "Pending" lock + retry loop.
- **Mobile Virtualization:** The "Floor" (participant list) is fully virtualized in the JS layer.
- **Red Pulse PTT:** Inset red glow on viewport edge during active transmission.
- **Self-Healing:** `/api/rooms/<id>/sync` endpoint for manual moderator reset of room state.
- **Zulip Bridge:** Deferred to v2.0 for MVP stability.

---

## 1. Infrastructure Setup

### 1.1 Docker Compose Services
- `livekit`: SFU core.
- `livekit-egress`: Audio recording service.
- `redis`: Room state.
- `flask`: Token API + orchestration.
- `mongo`: State + Audit.
- `coturn`: Mandatory TURN relay (verified in setup).

### 1.2 Environment Variables (`.env`)
```
ACCESS_PASSPHRASE=       # Member
MOD_PASSPHRASE=          # Moderator
ADMIN_PASSPHRASE=        # Admin
OPERATOR_PASSPHRASE=     # Operator
LIVEKIT_HOST=            # WebSocket URL
```

---

## 2. Backend Orchestration (Flask)

### 2.1 Hierarchical Auth
- Role determined by passphrase submitted at login.
- `admin > moderator > operator > member`.

### 2.2 Room Mode Toggle (Atomic)
1. Set `mode_status = "pending"` in MongoDB.
2. Parallel update via `gevent.pool.Pool` of all live participants in LiveKit.
3. On 100% success: Set `mode_status = "complete"`, `mode = <new_mode>`.
4. On failure: Trigger retry loop; expose "Sync/Reset" button to moderator.

### 2.3 Security Boundaries
- Operators are strictly scoped to their assigned `room_id`.
- Every mute/presenter action validates that the target `user_id` is currently in the operator's room.

---

## 3. Browser Client (Pure Voice)

### 3.1 UI Architecture: "The Stage"
- **Visual Hierarchy:**
  1. **Stage (Primary):** Top 10 active speakers with 64px avatars. Prominent names and "Speaking" ring animation.
  2. **Floor (Secondary):** Scrollable list of 1,990+ participants. Sorted by "Speaking" state (Active first), then Sector, then Alphabetical.
  3. **Sidebar (Tertiary):** Room navigation and User status. Adapts to Bottom Sheet on Mobile (<768px).
- **PTT Feedback:** Inset red glow (#d32f2f, rgba(211, 47, 47, 0.4)) on viewport edge during active transmission. 1.5s pulse animation.
- **Visual Tokens:**
  - Background: #1a1a2e (Deep Navy)
  - Surface: #16213e (Secondary Navy)
  - Border: #2a4a7f (Azure Border)
  - Accent: #4361ee (NextGen Blue)

### 3.2 Interaction States
| FEATURE | LOADING | EMPTY | ERROR | SUCCESS | PARTIAL |
|---|---|---|---|---|---|
| **Room Join** | Pulse Spinner + "Handshaking..." | - | "Link Failure" + Reconnect Btn | Entry into Room view | - |
| **Stage** | - | "Stage is quiet." | - | Large avatar grid | - |
| **Floor** | Virtualized Skeleton | "No one else here." | - | Density-aware list | O(1) Virtual Scroll |
| **PTT** | - | - | Red pulse failure (Glow) | Red viewport pulse | - |

### 3.3 User Journey & Confidence
- **Orientation:** First entry highlights the "Stage" to orient the user to current activity.
- **Confidence:** "Red Pulse" provides sub-50ms feedback for transmission, solving the "Am I muted?" anxiety.
- **Awareness:** Connection quality dots (Green/Yellow/Red) next to each participant in the Floor.

---

## 4. Testing & Verification

### 4.1 Load Test Spike
- New script: `scripts/load_test_voice.sh`.
- Parameters: `-video-resolution 0` (Audio only), 2000 subscribers.

### 4.2 Verification Checklist
- [ ] TURN connectivity verified via `scripts/setup_dev.sh`.
- [ ] Mode switch atomicity (test via simulated network drop).
- [ ] Mobile Bottom Sheet virtualization (2000 users at 60fps).
- [ ] Red Pulse PTT visual confirmation.

## Phase 4 — Pro Admin & Zulip Identity

### 4.1 Hybrid Auth Backend
- **Super-Admin (Recovery)**: Defined via \`SUPER_ADMIN_EMAIL\` and \`SUPER_ADMIN_HASH\` in \`.env\`. Bypass Zulip check.
- **Zulip Proxy**: Login via Email/Pass; app makes a standard REST call to Zulip to verify.
- **Profile Sync**: Fetch \`full_name\`, \`avatar_url\`, and role (\`is_admin\`, \`is_moderator\`) from Zulip.
- **Role Mapping**: Direct mapping of Zulip Admin/Mod to VoiceCom Admin/Mod.

### 4.2 Pro-Admin Dashboard
- **Room Controls**: Global Room Lockdown (Kicks all, prevents join).
- **God-Mic**: Admin can broadcast audio to ALL active rooms via a server-side bot/relay.
- **Global Audit**: View all logins and administrative actions with Zulip display names.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | /plan-ceo-review | Scope & strategy | 3 | **CLEAR** | Zulip Identity Proxy + God Mic accepted |
| Eng Review | /plan-eng-review | Architecture & tests | 1 | **CLEAR** | (Stale — re-run needed for Auth/Admin) |
| Design Review | /plan-design-review | UI/UX gaps | 0 | — | Recommended for Admin Dashboard |

**VERDICT: CEO CLEARED — Ready to implement Zulip & Pro-Admin Expansion.**
