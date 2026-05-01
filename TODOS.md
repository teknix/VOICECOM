# TODOS — LiveKit Voice System

Deferred items from the CEO/Engineering review (2026-04-30). Not blocking v1 launch.

---

## P1 — Push-to-Talk Key Configuration

**Current:** Caps Lock is hardcoded as the PTT key in the Phase 4 spec.
**Gap:** No UI to configure the key binding. Users who dislike Caps Lock have no alternative.
**Resolution:** Add a keyboard shortcut settings panel in voice.html. Persist preference to `localStorage`. Space bar is a common alternative — default to Caps Lock, allow override.

---

## P1 — Hand Raise Extended Schema

**Current:** Hand raise message schema defined in Phase 4 (§4.3): `{ type, user_id, display_name, raised }`.
**Gap:** No queue management — if 10 users raise hands simultaneously, presenter has no ordered list.
**Resolution:** Add `raised_at: <ISO timestamp>` to the message schema. Client-side queue on presenter view sorted by `raised_at`. Moderator can dismiss individual hands via `{ raised: false }` message.

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
