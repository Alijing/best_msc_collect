import socket

import pytest

from app.core.rate_limit import catalog_extra_wait
from app.utils.url import UnsafeURLError, assert_safe_url, clear_dns_cache


def test_catalog_extra_wait_does_not_stack_on_rate_limit():
    assert catalog_extra_wait(0.0, 2.0) == 0.0
    assert catalog_extra_wait(0.6, 2.0) == pytest.approx(0.1)
    assert catalog_extra_wait(2.0, 2.0) == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_literal_private_ip_is_rejected():
    with pytest.raises(UnsafeURLError):
        await assert_safe_url("http://127.0.0.1/admin")
    with pytest.raises(UnsafeURLError):
        await assert_safe_url("http://169.254.169.254/latest")


@pytest.mark.asyncio
async def test_dns_failure_is_rejected_and_success_is_cached(monkeypatch):
    clear_dns_cache()
    calls = {"n": 0}

    def fake_getaddrinfo(host, _port, *args, **kwargs):
        calls["n"] += 1
        if host == "missing.example":
            raise socket.gaierror("no such host")
        if host == "internal.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.0.5", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0))]

    monkeypatch.setattr("app.utils.url.socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(UnsafeURLError):
        await assert_safe_url("http://missing.example/a")
    with pytest.raises(UnsafeURLError):
        await assert_safe_url("http://internal.example/a")

    await assert_safe_url("http://public.example/a")
    await assert_safe_url("http://public.example/b")
    assert calls["n"] == 3
    clear_dns_cache()
