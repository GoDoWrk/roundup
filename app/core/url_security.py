from __future__ import annotations

from functools import lru_cache
from ipaddress import ip_address
import socket
from urllib.parse import parse_qsl, urlparse, urlunparse

SECRET_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "auth_token",
    "key",
    "password",
    "secret",
    "token",
}


def _is_public_address(value: str) -> bool:
    address = ip_address(value)
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


@lru_cache(maxsize=1024)
def _resolved_addresses(hostname: str) -> tuple[str, ...]:
    try:
        results = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError:
        return ()

    addresses: set[str] = set()
    for result in results:
        sockaddr = result[4]
        if sockaddr:
            addresses.add(str(sockaddr[0]))
    return tuple(sorted(addresses))


def _is_public_hostname(hostname: str) -> bool:
    normalized = hostname.strip().lower().rstrip(".")
    if not normalized or normalized == "localhost" or normalized.endswith(".localhost"):
        return False

    try:
        return _is_public_address(normalized)
    except ValueError:
        pass

    addresses = _resolved_addresses(normalized)
    if not addresses:
        return False

    try:
        return all(_is_public_address(address) for address in addresses)
    except ValueError:
        return False


def safe_feed_url(value: object, *, allow_private_network: bool = False) -> str | None:
    if not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate:
        return None

    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None

    if parsed.username or parsed.password:
        return None

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if any(key.strip().lower() in SECRET_QUERY_KEYS for key, _ in query_pairs):
        return None

    hostname = parsed.hostname or ""
    if not allow_private_network and not _is_public_hostname(hostname):
        return None
    if allow_private_network and not hostname.strip():
        return None

    return urlunparse(parsed._replace(fragment=""))
