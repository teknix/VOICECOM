"""Self-check for federated Matrix login. Run: python3 test_matrix_auth.py

Covers the security-critical pure logic only — MXID parsing, the homeserver allowlist,
and the SSRF guard. All three reject before any network call, so no mocking needed.
"""
import os

os.environ["MATRIX_ALLOWED_HOMESERVERS"] = "turbulent.net, matrix.org"

from app.matrix import _split_mxid, _is_safe_url, verify_matrix_credentials


def test_split_mxid():
    assert _split_mxid("@ingo:turbulent.net") == ("@ingo:turbulent.net", "turbulent.net")
    assert _split_mxid("ingo:turbulent.net") == ("@ingo:turbulent.net", "turbulent.net")
    assert _split_mxid("@Ingo:Turbulent.NET") == ("@Ingo:turbulent.net", "turbulent.net")
    # not MXIDs — must not reach the network path
    assert _split_mxid("ingo") == (None, None)
    assert _split_mxid("ingo@example.com") == (None, None)
    assert _split_mxid("@ingo:") == (None, None)
    assert _split_mxid(":turbulent.net") == (None, None)


def test_ssrf_guard():
    assert _is_safe_url("https://matrix.org")
    # scheme
    assert not _is_safe_url("http://matrix.org")
    assert not _is_safe_url("file:///etc/passwd")
    # private / loopback / link-local / unspecified targets
    assert not _is_safe_url("https://127.0.0.1")
    assert not _is_safe_url("https://10.124.0.2")        # the droplet's own private iface
    assert not _is_safe_url("https://192.168.1.91")      # lake
    assert not _is_safe_url("https://169.254.169.254")   # cloud metadata
    assert not _is_safe_url("https://0.0.0.0")
    assert not _is_safe_url("https://[::1]")
    # unresolvable
    assert not _is_safe_url("https://no-such-host.invalid")


def test_allowlist():
    # rejected before any network call
    ok, info = verify_matrix_credentials("@someone:evil.example", "pw")
    assert ok is False and info["hint"] == "homeserver_not_allowed", info
    assert info["server"] == "evil.example"

    ok, info = verify_matrix_credentials("plainuser", "pw")
    assert ok is False and info["hint"] == "mxid_required", info


def test_fails_closed_without_allowlist():
    import app.matrix as m
    saved = m.MATRIX_ALLOWED_HOMESERVERS
    m.MATRIX_ALLOWED_HOMESERVERS = set()
    try:
        assert m.verify_matrix_credentials("@ingo:turbulent.net", "pw") == (False, None)
    finally:
        m.MATRIX_ALLOWED_HOMESERVERS = saved


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
