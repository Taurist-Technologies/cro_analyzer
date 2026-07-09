"""
URL normalization and SSRF protection for CRO Analyzer.

Every user-supplied URL passes through here before the browser touches it:
- normalize_url() canonicalizes URLs so cache keys don't fragment on
  tracking parameters or trivial formatting differences.
- validate_public_url() rejects URLs that resolve to private/internal
  address space, since the analyzer fetches arbitrary URLs on behalf of
  unauthenticated-ish chat users.
"""

import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


class UnsafeURLError(ValueError):
    """Raised when a URL fails SSRF validation."""


# Query parameters that never change page content — stripped for cache keys
TRACKING_PARAMS = {
    "gclid", "fbclid", "msclkid", "ttclid", "twclid", "dclid", "gbraid", "wbraid",
    "mc_cid", "mc_eid", "igshid", "srsltid", "yclid", "_ga", "_gl", "ref",
    "ref_src", "referrer", "spm", "affiliate_id", "irclickid", "sscid",
}


def normalize_url(url: str) -> str:
    """
    Canonicalize a URL for analysis and caching.

    - lowercases scheme and host
    - drops fragments
    - strips utm_* and known click-ID/tracking parameters
    - removes default ports and trailing slash on bare paths
    """
    parts = urlsplit(str(url).strip())

    scheme = parts.scheme.lower()
    host = parts.hostname.lower() if parts.hostname else ""
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"

    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(query_pairs)

    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit((scheme, host, path, query, ""))


def validate_public_url(url: str) -> None:
    """
    Raise UnsafeURLError unless the URL is http(s) and its host resolves
    exclusively to public IP addresses.

    Note: this validates the URL at submission time. The capture pipeline
    re-checks the final URL after navigation, since redirects can land
    somewhere else.
    """
    parts = urlsplit(str(url))

    if parts.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported URL scheme: {parts.scheme!r}")

    host = parts.hostname
    if not host:
        raise UnsafeURLError("URL has no hostname")

    # Literal IP in the URL — check directly without DNS
    try:
        _ensure_public_ip(ipaddress.ip_address(host), host)
        return
    except ValueError:
        pass  # not a literal IP; resolve below

    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local") or host.endswith(".internal"):
        raise UnsafeURLError(f"Host {host!r} points to internal address space")

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UnsafeURLError(f"Could not resolve host {host!r}: {e}") from e

    for info in infos:
        _ensure_public_ip(ipaddress.ip_address(info[4][0]), host)


def _ensure_public_ip(ip: ipaddress._BaseAddress, host: str) -> None:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise UnsafeURLError(f"Host {host!r} resolves to non-public address {ip}")
