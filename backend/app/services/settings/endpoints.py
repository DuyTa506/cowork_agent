"""Is an endpoint inside the private network? Used to keep document text from being sent to the Internet by accident."""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

_PRIVATE_SUFFIXES = (".local", ".lan", ".internal", ".intranet", ".localdomain")


def host_of(url: str) -> str:
    """Lower-case host part of `url` ("" when there is none)."""
    return (urlparse(url).hostname or "").lower()


def is_private_host(host: str) -> bool:
    """True for private/loopback/link-local IP addresses and for names that are clearly internal (no dot, or a ``.lan`` style
    suffix, as docker service names are). Any other name counts as external: resolving DNS here would make the answer depend
    on the network at save time."""
    if not host:
        return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_private or address.is_loopback or address.is_link_local
    except ValueError:
        return "." not in host or host.endswith(_PRIVATE_SUFFIXES)
