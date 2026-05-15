#!/usr/bin/env python3
"""Quick connectivity test for Zulip auth. Usage: python3 test_zulip_auth.py"""
import sys
import requests
from requests.auth import HTTPBasicAuth

ZULIP_URL = "https://wtp.bringitdown.com"

def test_reachability():
    print(f"[1] Checking {ZULIP_URL} is reachable...")
    try:
        resp = requests.get(ZULIP_URL, timeout=5)
        print(f"    HTTP {resp.status_code} — OK")
    except Exception as e:
        print(f"    FAIL: {e}")
        sys.exit(1)

def test_api_endpoint():
    print(f"[2] Checking /api/v1/server_settings...")
    try:
        resp = requests.get(f"{ZULIP_URL}/api/v1/server_settings", timeout=5)
        data = resp.json()
        print(f"    realm: {data.get('realm_name', '?')}  version: {data.get('zulip_version', '?')}")
    except Exception as e:
        print(f"    FAIL: {e}")
        sys.exit(1)

def test_credentials(email, password):
    print(f"[3] Testing fetch_api_key for {email}...")
    resp = requests.post(
        f"{ZULIP_URL}/api/v1/fetch_api_key",
        data={"username": email, "password": password},
        timeout=5
    )
    if resp.status_code != 200:
        print(f"    FAIL: HTTP {resp.status_code}  {resp.text[:200]}")
        return
    data = resp.json()
    if data.get("result") != "success":
        print(f"    FAIL: {data}")
        return
    api_key = data["api_key"]
    user_id = data["user_id"]
    print(f"    OK — user_id={user_id}")

    print(f"[4] Fetching profile with API key...")
    resp2 = requests.get(
        f"{ZULIP_URL}/api/v1/users/me",
        auth=HTTPBasicAuth(email, api_key),
        timeout=5
    )
    if resp2.status_code == 200:
        p = resp2.json()
        print(f"    full_name={p.get('full_name')}  is_admin={p.get('is_admin')}  is_owner={p.get('is_owner')}")
    else:
        print(f"    Profile fetch HTTP {resp2.status_code}")

if __name__ == "__main__":
    test_reachability()
    test_api_endpoint()
    if len(sys.argv) == 3:
        test_credentials(sys.argv[1], sys.argv[2])
    else:
        print("[3] Skipped credential test — run as: python3 test_zulip_auth.py email@example.com password")
