"""Link previews for chat: title, description and site name for a pasted http(s) link.

The server fetches the page, so it only goes to public internet addresses on the
normal web ports: never LAN, loopback or cloud-metadata addresses (each redirect hop
is checked again). Pages are read up to 512 KB with short timeouts and the answer
is cached for an hour. Images are not proxied or hot-linked, so viewers' browsers
never contact third-party sites just because someone pasted a link.
"""
import html
import ipaddress
import re
import socket
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests
from flask import Blueprint, jsonify, request

from .middleware import login_required

unfurl_bp = Blueprint("unfurl", __name__)

MAX_BYTES = 512 * 1024
TIMEOUT = (3, 4)  # connect, read
CACHE_TTL = 3600
_cache = {}  # url -> (expires, payload)


def public_host(host, port):
    """True only if every address the name resolves to is a public internet address."""
    if port not in (80, 443):
        return False
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        return False
    addrs = {ipaddress.ip_address(i[4][0]) for i in infos}
    return bool(addrs) and all(a.is_global and not a.is_multicast for a in addrs)


class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta, self.title, self._in_title = {}, "", False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key in ("og:title", "og:description", "og:site_name", "description", "twitter:title", "twitter:description"):
                self.meta.setdefault(key, (a.get("content") or "").strip())
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and len(self.title) < 300:
            self.title += data


def fetch_preview(url):
    for _ in range(4):  # the first request plus up to 3 redirects, each re-checked
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return None
        if not public_host(u.hostname, u.port or (443 if u.scheme == "https" else 80)):
            return None
        r = requests.get(url, timeout=TIMEOUT, allow_redirects=False, stream=True,
                         headers={"User-Agent": "VoiceCom link preview", "Accept": "text/html"})
        if r.is_redirect:
            url = urljoin(url, r.headers.get("Location", ""))
            r.close()
            continue
        if r.status_code != 200 or "html" not in r.headers.get("Content-Type", ""):
            r.close()
            return None
        body = b""
        for chunk in r.iter_content(16384):
            body += chunk
            if len(body) >= MAX_BYTES:
                break
        r.close()
        p = MetaParser()
        try:
            p.feed(body.decode(r.encoding or "utf-8", errors="replace"))
        except Exception:
            pass
        m = p.meta
        clean = lambda s: re.sub(r"\s+", " ", html.unescape(s or "")).strip()
        title = clean(m.get("og:title") or m.get("twitter:title") or p.title)[:200]
        desc = clean(m.get("og:description") or m.get("twitter:description") or m.get("description"))[:300]
        if not title and not desc:
            return None
        return {"url": url, "site": clean(m.get("og:site_name"))[:80] or urlparse(url).hostname,
                "title": title, "description": desc}
    return None


@unfurl_bp.route("/api/unfurl")
@login_required
def unfurl():
    url = (request.args.get("url") or "").strip()[:2000]
    now = time.time()
    hit = _cache.get(url)
    if hit and hit[0] > now:
        return jsonify(hit[1])
    try:
        payload = fetch_preview(url) or {}
    except requests.RequestException:
        payload = {}
    if len(_cache) > 2000:
        _cache.clear()
    _cache[url] = (now + CACHE_TTL, payload)
    return jsonify(payload)
