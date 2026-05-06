# TODOS — LiveKit Voice System

Deferred items from the CEO/Engineering review (2026-04-30). Not blocking v1 launch.

---

## P2 — Recording Cleanup / Disk Management

**Current:** Egress writes `.mp4` files to `/recordings` volume with no cleanup policy.
**Gap:** 200–500 active users generating recordings will fill disk. No retention policy, no size alerts.
**Resolution:**
- Add a `max_recording_age_days` config value (default 30)
- Cron job or startup check: delete recordings older than threshold, update MongoDB status to `"purged"`
- Expose current disk usage on admin dashboard
- Alert in admin dashboard when `/recordings` volume is >80% full

---

## Polish — Voice Activity Indicator

**Deferred from CP4 (plan-ceo-review).**
Use LiveKit's `activeSpeakersChanged` event to highlight the speaking participant in the participant list (e.g. green border or animated mic icon). No server-side changes needed — purely client-side.

```javascript
room.on(LivekitClient.RoomEvent.ActiveSpeakersChanged, (speakers) => {
  // speakers: Participant[]
  highlightSpeakers(speakers.map(s => s.identity));
});
```

---

## Production — Authentik OIDC Integration

**Explicitly out of scope for v1.** Session keys (`user_id`, `display_name`, `role`) are already named to match the OIDC flow. Replace `Phase 2` entirely; no other code changes required.

## Completed
- [x] **E2E/Integration Hardening**: Verified role hierarchy, shadow speaker enforcement, persistent hand queue, and DOM pooling. (v0.1.0.2, 2026-05-03)
- [x] **Push-to-Talk Key Configuration**: Added keyboard shortcut settings panel with localStorage persistence. (v0.1.0.2, 2026-05-03)
- [x] **Hand Raise Extended Schema**: Added `raised_at` timestamps, moderator queue, and dismissal logic. (v0.1.0.2, 2026-05-03)
- [x] **Sector Grouping**: Organized 2,000-user floor list into 16 US sectors. (v0.1.0.1, 2026-05-01)

---

## P2 — Speaking-First Floor Sort
**Current:** Floor is grouped by sector and sorted alphabetically.
**Gap:** In a 2,000-user room, finding active speakers on the floor requires scrolling.
**Resolution:** Implement a priority sort for the virtualized list. Participants with `isSpeaking: true` should bubble to the top of their sector (or a global "Speaking Now" section).
- [x] **IRC Density Mode**: High-density 24px layout for large-scale monitoring. (v0.1.0.1, 2026-05-01)
- [x] **Moderator Sync**: Force-broadcast state reconciliation via O(1) metadata. (v0.1.0.1, 2026-05-01)
- [x] **XSS/Security Audit**: Secured chat, identity rendering, and hardened access control. (v0.1.0.1, 2026-05-01)
- [x] **Voice Activity Indicator**: Real-time speaker highlighting on Stage and Floor. (v0.1.0.1, 2026-05-01)
