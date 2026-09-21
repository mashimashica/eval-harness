# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import io
import socket
import ssl
import threading
import time
from datetime import datetime
from typing import Any, Callable

import pytest

import eval_harness.capability_network as network
from eval_harness.capability_network import NetworkClient, NetworkError, _is_public_address, _parse_duckduckgo

PUBLIC_IP = "93.184.216.34"


def _resolver(host: str, port: int, *, type: int) -> list[tuple[Any, ...]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (PUBLIC_IP, port))]


class _Response:
    def __init__(self, status: int, body: bytes, **headers: str) -> None:
        self.status, self.headers, self.stream = status, headers, io.BytesIO(body)

    def getheader(self, name: str) -> str | None:
        return self.headers.get(name)

    def read1(self, amount: int) -> bytes:
        return self.stream.read(amount)

    def close(self) -> None:
        self.stream.close()


def _transport(monkeypatch: pytest.MonkeyPatch, respond: Callable[[str, str], _Response]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class Connection:
        sock = None

        def __init__(self, host: str, address: str, *, timeout: float, context: ssl.SSLContext) -> None:
            assert address == PUBLIC_IP
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
            self.host, self.target, self.timeout = host, "", timeout

        def request(self, method: str, target: str, *, headers: dict[str, str]) -> None:
            assert method == "GET"
            self.target = target
            calls.append({"host": self.host, "target": target, "headers": headers, "timeout": self.timeout})

        def getresponse(self) -> _Response:
            return respond(self.host, self.target)

        def abort(self) -> None:
            pass

    monkeypatch.setattr(network, "_PinnedHTTPSConnection", Connection)
    return calls


def test_legacy_policy_keeps_exact_allowlist_and_empty_list_denial() -> None:
    client = NetworkClient(["docs.example"], resolver=_resolver)
    assert client._validate_url("https://docs.example/guide?q=1")[0] == "https://docs.example/guide?q=1"
    for url, match in [
        ("http://docs.example/", "HTTPS"),
        ("https://other.example/", "allowlist"),
        ("https://sub.docs.example/", "allowlist"),
        ("https://user:secret@docs.example/", "credentials"),
    ]:
        with pytest.raises(NetworkError, match=match):
            client._validate_url(url)
    with pytest.raises(NetworkError, match="allowlist"):
        NetworkClient([])._validate_url("https://www.python.org/")


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://2130706433/",
        "https://0177.0.0.1/",
        "https://metadata.google.internal/",
        "https://localhost/",
        "https://a.local/",
        "https://a.home.arpa/",
        "https://a.test/",
        "https://example.org/",
        "https://a.example/",
        "https://a.onion/",
        "https://intranet/",
        "http://www.python.org/",
        "https://www.python.org:8443/",
        "https://a:b@www.python.org/",
        "https://www.py\nthon.org/",
        "https://www.python.org\x00/",
        "https://[malformed/",
    ],
)
def test_public_https_rejects_nonpublic_hosts_and_nonanonymous_urls(url: str) -> None:
    with pytest.raises(NetworkError):
        NetworkClient([], network_policy="public_https")._validate_url(url)


def test_public_https_accepts_unlisted_dns_hosts_and_keeps_backend_selection_separate() -> None:
    client = NetworkClient([], network_policy="public_https")
    assert client._validate_url("https://WWW.PYTHON.ORG.:443/doc/?q=a")[0] == "https://www.python.org/doc/?q=a"
    assert [name for name, _ in client._search_backends()] == ["duckduckgo-html", "bing-rss"]
    assert NetworkClient(["www.python.org"])._search_backends() == ()
    assert [name for name, _ in NetworkClient(["www.bing.com"])._search_backends()] == ["bing-rss"]
    with pytest.raises(NetworkError, match="network_policy"):
        NetworkClient([], network_policy="unrestricted")
    with pytest.raises(NetworkError, match="timeout"):
        NetworkClient([], timeout_seconds=float("nan"))


def test_private_dns_answers_fail_closed_even_among_public_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolver(host: str, port: int, *, type: int) -> list[tuple[Any, ...]]:
        return _resolver(host, port, type=type) + [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    calls = _transport(monkeypatch, lambda host, target: pytest.fail("unsafe DNS was contacted"))
    for policy in ("allowlist", "public_https"):
        client = NetworkClient(["www.python.org"], resolver=resolver, network_policy=policy)
        with pytest.raises(NetworkError, match="non-public"):
            client.fetch("https://www.python.org/")
    assert calls == []


def test_public_address_check_rejects_multicast_reserved_and_private_ranges() -> None:
    assert _is_public_address(PUBLIC_IP)
    for value in (
        "224.0.0.1",
        "240.0.0.1",
        "192.0.2.1",
        "10.0.0.1",
        "100.64.0.1",
        "169.254.169.254",
        "::1",
        "ff02::1",
        "::ffff:127.0.0.1",
        "2001:db8::1",
    ):
        assert not _is_public_address(value)


def test_redirects_use_fresh_public_dns_and_fixed_anonymous_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved: list[str] = []

    def resolver(host: str, port: int, *, type: int) -> list[tuple[Any, ...]]:
        resolved.append(host)
        return _resolver(host, port, type=type)

    def respond(host: str, target: str) -> _Response:
        if host == "www.python.org":
            return _Response(302, b"move", Location="https://docs.python.org/3/", **{"Set-Cookie": "session=secret"})
        return _Response(200, b"content", **{"Content-Type": "text/plain; charset=utf-8"})

    monkeypatch.setenv("HTTPS_PROXY", "http://secret:password@localhost:8888")
    monkeypatch.setenv("ALL_PROXY", "http://localhost:8888")
    monkeypatch.setenv("NETRC", "/nonexistent/credential-file")
    calls = _transport(monkeypatch, respond)
    client = NetworkClient([], resolver=resolver, network_policy="public_https", max_bytes=11)
    response = client.fetch("https://www.python.org/start")
    assert response.body == b"content" and response.content_type == "text/plain"
    assert response.redirects == ("https://docs.python.org/3/",)
    assert [exchange.body for exchange in response.exchanges] == [b"move", b"content"]
    assert resolved == ["www.python.org", "docs.python.org"]
    assert len(calls) == 2
    for call in calls:
        assert set(call["headers"]) == {"Accept", "Accept-Encoding", "Connection", "Host", "User-Agent"}
        assert call["headers"]["Host"] == call["host"]


def test_dns_rebinding_redirect_is_rejected_without_connecting_again(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved = 0

    def resolver(host: str, port: int, *, type: int) -> list[tuple[Any, ...]]:
        nonlocal resolved
        resolved += 1
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ((PUBLIC_IP if resolved == 1 else "169.254.169.254"), port))
        ]

    calls = _transport(monkeypatch, lambda host, target: _Response(302, b"redirect", Location="/next"))
    with pytest.raises(NetworkError, match="non-public") as failure:
        NetworkClient([], resolver=resolver, network_policy="public_https").fetch("https://www.python.org/start")
    assert len(calls) == 1 and resolved == 2
    assert failure.value.redirects == ("https://www.python.org/next",)
    assert failure.value.exchanges[0].body == b"redirect"


@pytest.mark.parametrize(
    "location", ["https://localhost/", "http://www.python.org/", "https://user:pw@www.python.org/"]
)
def test_forbidden_redirect_retains_received_body(monkeypatch: pytest.MonkeyPatch, location: str) -> None:
    calls = _transport(monkeypatch, lambda host, target: _Response(302, b"redirect evidence", Location=location))
    with pytest.raises(NetworkError) as failure:
        NetworkClient([], resolver=_resolver, network_policy="public_https").fetch("https://www.python.org/start")
    assert len(calls) == 1
    assert failure.value.exchanges[0].status == 302 and failure.value.exchanges[0].body == b"redirect evidence"
    assert failure.value.exchanges[0].location == location


def test_total_byte_budget_includes_redirect_bodies_and_retains_partial_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def respond(host: str, target: str) -> _Response:
        return _Response(302, b"123", Location="/next") if target == "/" else _Response(200, b"456")

    _transport(monkeypatch, respond)
    with pytest.raises(NetworkError, match="total limit") as failure:
        NetworkClient(["docs.example"], resolver=_resolver, max_bytes=5).fetch("https://docs.example/")
    assert [exchange.body for exchange in failure.value.exchanges] == [b"123", b"45"]
    assert failure.value.exchanges[-1].body_complete is False
    assert sum(len(exchange.body or b"") for exchange in failure.value.exchanges) == 5


def test_dns_resolution_has_a_deadline() -> None:
    release = threading.Event()

    def stalled(host: str, port: int, *, type: int) -> list[tuple[Any, ...]]:
        release.wait(2)
        return _resolver(host, port, type=type)

    started = time.monotonic()
    try:
        with pytest.raises(NetworkError, match="deadline"):
            NetworkClient(["docs.example"], resolver=stalled, timeout_seconds=0.03).fetch("https://docs.example/")
        assert time.monotonic() - started < 0.5
    finally:
        release.set()


def test_deadline_is_shared_across_address_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    calls: list[float] = []

    def resolver(host: str, port: int, *, type: int) -> list[tuple[Any, ...]]:
        return _resolver(host, port, type=type) + [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.35", port))
        ]

    class Connection:
        sock = None

        def __init__(self, host: str, address: str, *, timeout: float, context: ssl.SSLContext) -> None:
            calls.append(timeout)

        def request(self, method: str, target: str, *, headers: dict[str, str]) -> None:
            now[0] += 0.04
            raise TimeoutError("test connection unavailable")

        def abort(self) -> None:
            pass

    monkeypatch.setattr(network, "_PinnedHTTPSConnection", Connection)
    with pytest.raises(NetworkError, match="total deadline") as failure:
        NetworkClient(["docs.example"], resolver=resolver, timeout_seconds=0.06).fetch("https://docs.example/")
    assert calls == pytest.approx([0.06, 0.02])
    assert len(failure.value.exchanges) == 2


def test_deadline_is_shared_across_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])

    def respond(host: str, target: str) -> _Response:
        now[0] += 0.04
        return _Response(302, b"", Location="/next")

    calls = _transport(monkeypatch, respond)
    with pytest.raises(NetworkError, match="total deadline") as failure:
        NetworkClient(["docs.example"], resolver=_resolver, timeout_seconds=0.06).fetch("https://docs.example/")
    assert [call["timeout"] for call in calls] == pytest.approx([0.06, 0.02])
    assert len(failure.value.exchanges) == 2


def test_pinned_connection_uses_numeric_socket_and_original_tls_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[Any] = []

    class Socket:
        def settimeout(self, timeout: float) -> None:
            assert 0 < timeout <= 2

        def connect(self, address: tuple[str, int]) -> None:
            events.append(address)

        def do_handshake(self) -> None:
            events.append("handshake")

    sock = Socket()

    class Context:
        def wrap_socket(self, raw: Socket, *, server_hostname: str, do_handshake_on_connect: bool) -> Socket:
            assert raw is sock and not do_handshake_on_connect
            events.append(server_hostname)
            return sock

    monkeypatch.setattr(socket, "socket", lambda family, type: sock)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: pytest.fail("second DNS lookup"))
    connection = network._PinnedHTTPSConnection("www.python.org", PUBLIC_IP, timeout=2, context=Context())  # type: ignore[arg-type]
    connection.connect()
    assert events == [(PUBLIC_IP, 443), "www.python.org", "handshake"]


def test_search_retains_failed_backend_after_success_and_unlisted_result(monkeypatch: pytest.MonkeyPatch) -> None:
    def respond(host: str, target: str) -> _Response:
        if host == "html.duckduckgo.com":
            return _Response(403, b"backend blocked")
        return _Response(
            200,
            b"<rss><channel><item><title>Python</title><link>https://www.python.org/</link>"
            b"<description>Language docs</description></item></channel></rss>",
        )

    calls = _transport(monkeypatch, respond)
    result = NetworkClient(["html.duckduckgo.com", "www.bing.com"], resolver=_resolver).search("python docs")
    assert len(calls) == 2 and result.backend == "bing-rss"
    assert result.results[0]["url"] == "https://www.python.org/"
    assert [attempt.status for attempt in result.attempts] == [403, 200]
    assert result.attempts[0].exchanges[0].body == b"backend blocked"
    assert result.attempts[0].error and result.attempts[1].error is None
    for attempt in result.attempts:
        assert datetime.fromisoformat(attempt.retrieved_at).utcoffset().total_seconds() == 0  # type: ignore[union-attr]
        assert attempt.elapsed_seconds >= 0


def test_all_failed_search_attempts_keep_redirects_and_received_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    def respond(host: str, target: str) -> _Response:
        if target.startswith("/html/"):
            return _Response(302, b"redirect", Location="/challenge")
        return _Response(200, b"not search results")

    _transport(monkeypatch, respond)
    with pytest.raises(NetworkError, match="all configured search backends failed") as failure:
        NetworkClient([], resolver=_resolver, network_policy="public_https").search("python docs")
    attempts = failure.value.attempts
    assert len(attempts) == 2
    assert attempts[0].redirects == ("https://html.duckduckgo.com/challenge",)
    assert attempts[0].final_url == "https://html.duckduckgo.com/challenge"
    assert [exchange.body for exchange in attempts[0].exchanges] == [b"redirect", b"not search results"]
    assert attempts[0].status == 200 and attempts[1].status == 200
    assert all(attempt.error for attempt in attempts)


def test_duckduckgo_parser_returns_title_url_and_bounded_snippet() -> None:
    body = b"""
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.example%2Fpython">Python docs</a>
      <a class="result__snippet">A <b>useful</b> snippet.</a>
    </div>
    """
    assert _parse_duckduckgo(body) == [
        {"title": "Python docs", "url": "https://docs.example/python", "snippet": "A useful snippet."}
    ]


@pytest.mark.parametrize("stage", ["headers", "body"])
def test_total_deadline_interrupts_slow_stream_even_when_idle_timeout_would_not(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    # Local socket pair substitutes only the TCP/TLS connection; the production
    # HTTP parser, watchdog, response reader, and failure evidence run unchanged.
    client_socket, server_socket = socket.socketpair()
    stopped = threading.Event()

    def connect(connection: network._PinnedHTTPSConnection) -> None:
        connection.sock = client_socket
        connection._capability_socket = client_socket

    monkeypatch.setattr(network._PinnedHTTPSConnection, "connect", connect)

    def stream() -> None:
        try:
            if stage == "body":
                server_socket.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\nConnection: close\r\n\r\n")
            else:
                server_socket.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
            while not stopped.wait(0.005):
                server_socket.sendall(b"x")
        except OSError:
            pass
        finally:
            server_socket.close()

    worker = threading.Thread(target=stream, daemon=True)
    worker.start()
    started = time.monotonic()
    try:
        client = NetworkClient(["docs.example"], resolver=_resolver, timeout_seconds=0.08)
        with pytest.raises(NetworkError, match="total deadline") as failure:
            client.fetch("https://docs.example/")
        assert time.monotonic() - started < 0.5
        if stage == "body":
            assert failure.value.exchanges[-1].status == 200
            assert failure.value.exchanges[-1].body and not failure.value.exchanges[-1].body_complete
    finally:
        stopped.set()
        client_socket.close()
        worker.join(timeout=1)


def test_redirect_limit_retains_all_received_hops(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _transport(monkeypatch, lambda host, target: _Response(302, b"hop", Location="/again"))
    with pytest.raises(NetworkError, match="too many redirects") as failure:
        NetworkClient(["docs.example"], resolver=_resolver).fetch("https://docs.example/")
    assert len(calls) == network.MAX_REDIRECTS + 1
    assert len(failure.value.exchanges) == network.MAX_REDIRECTS + 1
    assert len(failure.value.redirects) == network.MAX_REDIRECTS
