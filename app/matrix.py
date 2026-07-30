"""Federated Matrix login: '@user:homeserver' + password, verified against that homeserver.

Mirrors the contract of zulip.py — verify_*_credentials(login, password) -> (ok, profile).
"""
import ipaddress
import socket
from urllib.parse import quote, urlparse

import requests

from .config import MATRIX_ALLOWED_HOMESERVERS

TIMEOUT = 8


def _split_mxid(login: str):
    """'@user:server' or 'user:server' -> ('@user:server', 'server'). (None, None) if not an MXID."""
    s = login.strip().lstrip("@")
    localpart, sep, server = s.partition(":")
    if not sep or not localpart or not server:
        return None, None
    return f"@{localpart}:{server.lower()}", server.lower()


def _is_safe_url(url: str) -> bool:
    """Reject non-HTTPS and anything resolving to a non-public address.

    The homeserver name is user-supplied and .well-known is served by that host, so both
    are attacker-influenced — without this a crafted well-known could point us at the
    droplet's own 10.124.0.2, at synapse, or at localhost.
    ponytail: resolve-then-fetch is TOCTOU-racy against DNS rebinding; the allowlist is the
    real control here. Pin to resolved IPs only if the allowlist ever opens up to '*'.
    """
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname:
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def _discover(server_name: str):
    """Resolve a Matrix server_name to its client API base URL, or None if unusable."""
    direct = f"https://{server_name}"
    try:
        resp = requests.get(f"{direct}/.well-known/matrix/client", timeout=TIMEOUT)
        if resp.status_code == 200:
            base = resp.json()["m.homeserver"]["base_url"].rstrip("/")
            return base if _is_safe_url(base) else None
    except Exception:
        pass
    # No well-known (or malformed) — the spec says fall back to the server name itself.
    return direct if _is_safe_url(direct) else None


def verify_matrix_credentials(login: str, password: str):
    """Verify a full Matrix ID + password against its own homeserver.

    Returns (success, profile_dict). On failure the dict may carry a 'hint' for the UI.
    """
    if not MATRIX_ALLOWED_HOMESERVERS:
        # Fail closed: no allowlist configured means federated login is off, not open.
        return False, None

    mxid, server_name = _split_mxid(login)
    if not mxid:
        return False, {"hint": "mxid_required"}

    if "*" not in MATRIX_ALLOWED_HOMESERVERS and server_name not in MATRIX_ALLOWED_HOMESERVERS:
        return False, {"hint": "homeserver_not_allowed", "server": server_name}

    base = _discover(server_name)
    if not base:
        return False, None

    try:
        resp = requests.post(
            f"{base}/_matrix/client/v3/login",
            json={
                "type": "m.login.password",
                "identifier": {"type": "m.id.user", "user": mxid},
                "password": password,
                "initial_device_display_name": "VoiceCom",
            },
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return False, None
        data = resp.json()
        user_id = data.get("user_id") or mxid
        token = data.get("access_token")
    except Exception:
        return False, None

    # ponytail: avatar left None — mxc:// needs authenticated media (matrix.org enforces it),
    # so a browser-usable URL means proxying media through flask. Cosmetic; add if asked.
    profile = {"user_id": user_id, "full_name": user_id, "avatar_url": None}

    try:
        resp = requests.get(
            f"{base}/_matrix/client/v3/profile/{quote(user_id)}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            profile["full_name"] = resp.json().get("displayname") or user_id
    except Exception:
        pass

    # Log the token out — otherwise every sign-in leaves a device on the user's account.
    try:
        requests.post(
            f"{base}/_matrix/client/v3/logout",
            headers={"Authorization": f"Bearer {token}"},
            json={},
            timeout=TIMEOUT,
        )
    except Exception:
        pass

    return True, profile
