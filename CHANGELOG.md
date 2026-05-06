# Changelog
All notable changes to this project will be documented in this file.

## [0.1.0.2] - 2026-05-03
### Added
- **PTT Key Configuration**: Added keyboard shortcut settings panel with localStorage persistence.
- **Hand Raise Queue**: Implemented timestamp-based queue and moderator dismissal interface.

## [0.1.0.1] - 2026-05-01
### Added
- **Alpha 0.001 Hardening**: Implemented core signaling and scaling fixes for 2000-user population.
- **IRC Density Mode**: High-density UI toggle (24px rows) for monitoring large sectors.
- **Moderator Sync State**: Force-broadcast room mode to all participants via O(1) metadata.
- **Sector Grouping**: 16-sector organizational hierarchy in the participant floor.
- **Audio Health Icons**: Real-time connectivity quality indicators (Green/Yellow/Red).
- **Persistent Signaling Loop**: Background thread for asyncio bridging to improve request latency.

### Fixed
- **XSS Vulnerabilities**: Secured chat and participant identity rendering.
- **CSRF Bypass**: Hardened blueprint exemptions.
- **Access Control**: Fixed moderator authorization for JSON-based requests.

### Removed
- **Zulip Bridge**: Deferred to v2.0 for Alpha stability.
