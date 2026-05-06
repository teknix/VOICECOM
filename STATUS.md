# Project Status — NextGen Voice System (LiveKit)

**Current Version:** 0.1.0.3 (Alpha Hardened)  
**Target:** 2,000 Concurrent User Scalability  
**Platform:** Docker-managed (7 Services)

---

## ✅ Current Implementation Status

### 1. Core Architecture
- **SFU Backbone:** LiveKit server integrated with `coturn` for mandatory TURN relay.
- **Backend:** Flask/gevent orchestration with MongoDB for state and audit logging.
- **Signaling Efficiency:** O(1) room mode signaling via LiveKit metadata (avoids O(N) loops).

### 2. High-Scale Hardening (v0.1.0.2)
- **Hybrid Security Enforcement:** Switching to "Broadcast Mode" triggers instant UI lock (O(1)) and background server-side permission revocation (O(N)).
- **DOM Element Pooling:** Refactored virtualized floor rendering to recycle DOM nodes, eliminating layout thrashing during active speaker changes.
- **Persistent Hand Queue:** Hand-raise queue is synchronized via Room Metadata; survives page refreshes and moderator handoffs.

### 3. Identity & Permissions (v0.1.0.3)
- **Hierarchical RBAC:** Admin > Moderator > Operator > Member.
- **Room-Aware Operators:** Admins can now set per-room operator passphrases via the Admin Dashboard. Operators are strictly scoped to their assigned rooms.
- **Configurable PTT:** Users can rebind their Push-to-Talk key via a persistent Settings (⚙️) modal.

---

## 🛠 Active Technical Debt & TODOs

### P1 — Operational Stability
- [ ] **Recording Disk Management:** Implement a cleanup policy for `/recordings`. 500 active users will exhaust disk space rapidly without retention logic.
- [ ] **Egress Health Checks:** Add Prometheus metrics or periodic heartbeat checks for the `livekit-egress` service to detect SEGFAULTS.

### P2 — UI/UX Refinement
- [ ] **Speaking-First Floor Sort:** Bubble active speakers to the top of their sector or a global "Active" section to prevent unnecessary scrolling.
- [ ] **Mobile Bottom Sheet:** Refine the Mobile Drawer into a standard Bottom Sheet pattern for better thumb-reachability on iOS/Android.

### P3 — Security & Scale
- [ ] **OIDC Integration:** Move away from passphrase-based auth to a provider like Authentik/Keycloak (Deferred to v2.0).
- [ ] **Zulip Bridge:** Enable the commented-out bridge logic in `app/rooms.py` once Zulip API tokens are available.

---

## 🧪 Verification State
- **Unit/Integration Tests:** 45 tests passing (`docker-compose exec flask pytest tests/`).
- **E2E Browser Tests:** Verified via `gstack browse` for Mobile Drawer and PTT logic.
- **Scale Simulation:** Mini-load test (50 users) verified against deployed SFU.

---
*Last Updated: 2026-05-03*
