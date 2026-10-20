"""Link previews never reach private addresses."""
from app import unfurl


def test_private_and_odd_ports_refused():
    for host in ("127.0.0.1", "localhost", "192.168.1.91", "10.0.0.1", "169.254.169.254", "[::1]"):
        assert unfurl.public_host(host.strip("[]"), 443) is False, host
    assert unfurl.public_host("8.8.8.8", 22) is False


def test_non_http_schemes_refused():
    assert unfurl.fetch_preview("file:///etc/passwd") is None
    assert unfurl.fetch_preview("http://127.0.0.1/") is None
    assert unfurl.fetch_preview("http://192.168.1.91:5010/") is None


def test_parser_reads_og_tags():
    p = unfurl.MetaParser()
    p.feed('<html><head><title> T </title><meta property="og:title" content="Hello &amp; bye">'
           '<meta name="description" content="Desc"></head></html>')
    assert p.meta["og:title"] == "Hello &amp; bye" or p.meta["og:title"] == "Hello & bye"
    assert p.meta["description"] == "Desc"
