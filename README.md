# VoiceCom: Tactical Command Center

VoiceCom is a professional, secure, and self-hosted voice communication system designed for high-concurrency advocacy and gaming operations. Built on LiveKit (WebRTC), it delivers sub-50ms latency for up to **2,000 concurrent users** per room with zero client-side installation.

---

## 🌟 Core Features

*   **⚡ Scale-First Architecture**: Virtualized participant lists ("The Floor") and SFU optimizations ensure stable performance for thousands of users.
*   **🎙️ Push-to-Talk (PTT)**: Hardware-accelerated PTT with `Caps Lock` support and "Hot Mic" visual feedback.
*   **🛡️ Hybrid Authentication**:
    *   **Internal DB**: Manage local accounts directly via the Admin Dashboard.
    *   **Zulip Proxy**: Optional SSO-like integration to verify credentials against your Zulip server.
    *   **Emergency Bypass**: Hardcoded Super-Admin defined in `.env` for recovery.
*   **👑 Pro-Admin Dashboard**:
    *   **God Mic**: Broadcast high-priority audio to ALL rooms simultaneously.
    *   **Room Controls**: Instantly lock rooms or "Kick All" participants.
    *   **User Management**: Create and delete internal users with hierarchical roles.
    *   **Audit Logging**: Track all administrative actions and logins in real-time.
*   **🔊 Echo Test Room**: Specialized loopback channel for users to calibrate their microphones.

---

## 🏗️ Architecture

VoiceCom consists of 7 Docker-managed services:
1.  **Flask**: The command & control backend (Identity, Tokens, API).
2.  **LiveKit SFU**: High-performance WebRTC Selective Forwarding Unit.
3.  **MongoDB**: Persistent storage for users, room state, and audit logs.
4.  **Redis**: Distributed state for LiveKit and Flask sessions.
5.  **coturn**: STUN/TURN server for NAT traversal.
6.  **LiveKit Egress**: Server-side recording and broadcasting engine.
7.  **Vanilla JS Client**: Ultra-lean, build-step-free browser interface.

---

## 🚀 Deployment Guide

### 1. Prerequisites
*   Ubuntu 22.04+ or Debian 12.
*   Public Static IP (or dynamic with DDNS).
*   Domain name pointing to your server.
*   Ports to open in Firewall/Router:
    *   **7882/UDP**: Media traffic (CRITICAL).
    *   **443/TCP**: HTTPS (Apache).
    *   **3478/UDP+TCP**: STUN/TURN signaling.

### 2. Quick Start
```bash
# 1. Clone
git clone https://github.com/teknix/VOICECOM.git
cd VOICECOM

# 2. Scaffolding
./scripts/setup_dev.sh

# 3. Configure (See Configuration section below)
nano .env

# 4. Launch
docker-compose up -d
```

### 3. Apache Reverse Proxy Setup
Use the included `voicecom.apache.conf` template.
1.  Enable modules: `sudo a2enmod proxy proxy_http proxy_wstunnel rewrite headers ssl`
2.  Copy config: `sudo cp voicecom.apache.conf /etc/apache2/sites-available/voicecom.conf`
3.  Edit `/etc/apache2/sites-available/voicecom.conf` to set your domain and SSL paths.
4.  Enable & Reload: `sudo a2ensite voicecom.conf && sudo systemctl reload apache2`

---

## ⚙️ Configuration (`.env`)

| Variable | Description |
| :--- | :--- |
| `DEV_MODE` | Set to `false` in production to enable public IP detection. |
| `ENABLE_ZULIP_AUTH` | Toggles Zulip credential proxy (`true`/`false`). |
| `SUPER_ADMIN_HASH` | Bcrypt hash for the emergency recovery user. |
| `LIVEKIT_HOST` | Public WebSocket URL (e.g., `wss://voicecom.net/rtc`). |
| `ACCESS_PASSPHRASE` | (Legacy) Password for the default 'Member' role. |

---

## 🛠 Usage Guide

### User Roles
*   **Admin**: Access to `/admin` dashboard, God Mic, and all moderation tools.
*   **Moderator**: Can toggle "Broadcast Mode" (silencing members) and mute individuals.
*   **Operator**: Moderator powers scoped to a specific sector/room.
*   **Member**: Basic join and talk capabilities.

### Admin Operations
*   **God Mic**: On the main voice interface, click **📢 God Mic**. Your audio will be injected into every active room. The button pulses red when active.
*   **Locking a Room**: In the Admin Dashboard, click **⚙️ Manage** on a room and toggle **Locked**. No one except Admins can join until unlocked.
*   **User Management**: Use the **Internal User Management** table to provision accounts without requiring Zulip.

### Hotkeys
*   **Hold Caps Lock**: Activate microphone (Push-to-Talk).
*   **M Button**: Toggle persistent mute (Desktop).

---

## 🛡️ Security & Integrity
*   Passwords are never stored in plain text (Bcrypt-hashed).
*   JWT-based session integrity via LiveKit Access Tokens.
*   Cross-Site Request Forgery (CSRF) protection enabled on all management endpoints.

---

## 👨‍💻 Development
To run in local development mode:
1.  Set `DEV_MODE=true` in `.env`.
2.  Run `docker-compose up`.
3.  Access via `http://localhost:5000`.

---
*Built for the next generation of privacy-conscious communicators.*
