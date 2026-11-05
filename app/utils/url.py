"""URL 规范化与 SSRF 防护。DNS 在线程中解析，并按主机短缓存。"""
import asyncio
import ipaddress
import socket
import time
from urllib.parse import urldefrag, urljoin, urlparse

from app.core.config import settings


class UnsafeURLError(ValueError):
    pass


_dns_cache: dict[str, tuple[float, bool]] = {}
_dns_lock = asyncio.Lock()


def normalize_url(url: str, base: str | None = None) -> str:
    if base:
        url = urljoin(base, url)
    url, _ = urldefrag(url)
    return url.strip()


def _addr_blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None and _addr_blocked(mapped):
        return True
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _resolve_blocked(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"无法解析主机: {host}") from exc
    saw_address = False
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        saw_address = True
        if _addr_blocked(addr):
            return True
    if not saw_address:
        raise UnsafeURLError(f"无法解析主机: {host}")
    return False


def _prune_dns_cache(now: float) -> None:
    if len(_dns_cache) <= 1024:
        return
    expired = [host for host, (until, _) in _dns_cache.items() if until < now]
    for host in expired:
        _dns_cache.pop(host, None)


def clear_dns_cache() -> None:
    _dns_cache.clear()


async def host_is_blocked(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is not None:
        return _addr_blocked(addr)

    now = time.monotonic()
    async with _dns_lock:
        hit = _dns_cache.get(host)
        if hit is not None and hit[0] > now:
            return hit[1]

    blocked = await asyncio.to_thread(_resolve_blocked, host)
    async with _dns_lock:
        _dns_cache[host] = (time.monotonic() + settings.DNS_CACHE_SECONDS, blocked)
        _prune_dns_cache(time.monotonic())
    return blocked


async def assert_safe_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"不支持的协议: {parsed.scheme or '空'}")
    if not parsed.hostname:
        raise UnsafeURLError("缺少主机名")
    if settings.ALLOW_PRIVATE_IP:
        return
    if await host_is_blocked(parsed.hostname):
        raise UnsafeURLError(f"禁止访问内网地址: {parsed.hostname}")
