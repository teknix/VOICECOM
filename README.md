# VoiceCom

Secure, open-source, and self-hosted voice communication system. Zero install, zero configuration for your users—it all runs in the browser.

## 🚀 Basic Setup for Laymen

### 1. Requirements
*   A Linux server (Ubuntu 22.04 or 24.04 recommended).
*   **Docker** and **Docker Compose** installed.
*   **Apache** web server (for exposing it to the internet).
*   A domain name (e.g., `voicecom.example.com`).
*   SSL certificates (e.g., from Let's Encrypt).

### 2. Getting Started
1.  **Clone the code:**
    ```bash
    git clone https://github.com/teknix/VOICECOM.git
    cd VOICECOM
    ```

2.  **Run the automatic setup:**
    ```bash
    ./scripts/setup_dev.sh
    ```

3.  **Configure your settings:**
    Open the `.env` file with a text editor (`nano .env`):
    *   **`DEV_MODE`**: Set to `false` for production.
    *   **`LIVEKIT_HOST`**: Set to your domain (e.g., `wss://voicecom.example.com/rtc`).
    *   **`ACCESS_PASSPHRASE`**: Choose a secret password for your users.

### 3. Port Forwarding / Firewall
You **MUST** open these ports for the system to work:
*   **7882 (UDP)**: Essential for audio traffic.
*   **443 (TCP)**: Web traffic (handled by Apache).
*   **3478 (UDP & TCP)**: Network helper (coturn).

### 4. Apache Web Server Setup
Use the provided `voicecom.apache.conf` as a template for your site.
1.  Copy it to Apache: `sudo cp voicecom.apache.conf /etc/apache2/sites-available/voicecom.conf`
2.  Enable the modules: `sudo a2enmod proxy proxy_http proxy_wstunnel rewrite headers ssl`
3.  Edit the file to update your **ServerName** and **SSL certificate paths**.
4.  Enable the site: `sudo a2ensite voicecom.conf`
5.  Reload Apache: `sudo systemctl reload apache2`

### 5. Launch the System
Start the services in the background:
```bash
docker-compose up -d
```

---

## 🛠 Features
*   **Push-to-Talk**: Hold `Caps Lock` (or click the button) to speak.
*   **Echo Test**: Join the "Echo Test" room to hear yourself and check audio quality.
*   **Low Latency**: Built on LiveKit (WebRTC) for sub-50ms voice transmission.
*   **Privacy First**: You own the server, you own the data.
