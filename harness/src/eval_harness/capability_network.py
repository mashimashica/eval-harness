# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Small, unauthenticated HTTPS client used by the capability service.

The participant-facing service must be able to fetch public research material without
inheriting the host's proxy, cookie, netrc, or credential configuration.  This module
therefore deliberately uses :mod:`http.client` directly, resolves a hostname once,
and connects to the resolved address while retaining the hostname for TLS
certificate verification.  It is intentionally independent of the harness executor.
"""

from __future__ import annotations

import html
import http.client
import ipaddress
import json
import math
import queue
import re
import socket
import ssl
import threading
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable, Iterable, Mapping, Sequence

from .errors import HarnessError

MAX_FETCH_BYTES = 20 * 1024 * 1024
MAX_FETCH_TIMEOUT_SECONDS = 30.0
MAX_REDIRECTS = 5
MAX_SEARCH_QUERY_CHARS = 2_000
MAX_SEARCH_RESULTS = 10
USER_AGENT = "eval-harness-capability/1"


# A resolver can outlive a caller's deadline. Bound these daemon workers so a
# stalled system resolver cannot accumulate an unbounded number of threads.
_DNS_SLOTS = threading.BoundedSemaphore(4)
MAX_DNS_ADDRESSES = 16
_RESERVED_HOSTS = (
    "localhost",
    "local",
    "localdomain",
    "alt",
    "internal",
    "lan",
    "home",
    "home.arpa",
    "onion",
    "test",
    "invalid",
    "example",
    "example.com",
    "example.net",
    "example.org",
    "arpa",
)


@dataclass(frozen=True)
class HTTPExchange:
    """One address attempt, including bounded partial bytes on failure."""

    url: str
    retrieved_at: str
    elapsed_seconds: float
    status: int | None = None
    content_type: str | None = None
    body: bytes | None = None
    body_complete: bool = False
    error: str | None = None
    location: str | None = None


@dataclass(frozen=True)
class FetchResponse:
    """Bounded response bytes and metadata from one safe GET request."""

    requested_url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    redirects: tuple[str, ...] = ()
    exchanges: tuple[HTTPExchange, ...] = ()

    @property
    def byte_count(self) -> int:
        return len(self.body)


@dataclass(frozen=True)
class SearchAttempt:
    """Provenance for each backend, whether successful or unsuccessful."""

    backend: str
    requested_url: str
    final_url: str
    redirects: tuple[str, ...]
    retrieved_at: str
    elapsed_seconds: float
    status: int | None
    error: str | None
    exchanges: tuple[HTTPExchange, ...]


class NetworkError(HarnessError):
    """A policy or transport failure retaining any received response evidence."""

    def __init__(
        self,
        message: str,
        *,
        final_url: str | None = None,
        redirects: tuple[str, ...] = (),
        exchanges: tuple[HTTPExchange, ...] = (),
        attempts: tuple[SearchAttempt, ...] = (),
    ) -> None:
        super().__init__(message)
        self.final_url = final_url
        self.redirects = redirects
        self.exchanges = exchanges
        self.attempts = attempts


@dataclass(frozen=True)
class SearchResult:
    """Public search results plus all backend attempts needed for a receipt."""

    query: str
    backend: str
    url: str
    response: FetchResponse
    results: tuple[dict[str, str], ...]
    attempts: tuple[SearchAttempt, ...] = ()


@dataclass
class _RequestBudget:
    deadline: float
    remaining_bytes: int

    def remaining_seconds(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise NetworkError("network request exceeded the total deadline")
        return remaining


def _idna_host(host: str) -> str:
    """Return a canonical ASCII DNS name, rejecting malformed host strings."""

    if not host or "\x00" in host:
        raise NetworkError("URL host is empty or contains a NUL byte")
    try:
        canonical = host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise NetworkError("URL host is not valid IDNA") from exc
    if not canonical or len(canonical) > 253:
        raise NetworkError("URL host is invalid")
    labels = canonical.split(".")
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in labels):
        raise NetworkError("URL host is invalid")
    if any(not all(char.isalnum() or char == "-" for char in label) for label in labels):
        raise NetworkError("URL host is invalid")
    return canonical


def _canonical_domains(domains: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for raw in domains:
        if not isinstance(raw, str) or not raw.strip():
            raise NetworkError("network_domains entries must be non-empty host names")
        value = raw.strip().lower()
        if "://" in value or "/" in value or "@" in value or value.startswith("*"):
            raise NetworkError(f"invalid network allowlist entry: {raw!r}")
        # A port in an allowlist is ambiguous and could make host matching unsafe.
        if ":" in value:
            raise NetworkError(f"network allowlist entries must not contain ports: {raw!r}")
        result.append(_idna_host(value))
    return tuple(dict.fromkeys(result))


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    # Keep every unsafe class explicit.  ``is_global`` has changed its treatment
    # of multicast and reserved ranges across Python releases, so relying on it
    # alone could turn a resolver result into an SSRF route after a runtime swap.
    return (
        address.is_global
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_private
    )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection that connects only to a previously validated IP address."""

    def __init__(self, hostname: str, address: str, *, timeout: float, context: ssl.SSLContext) -> None:
        super().__init__(hostname, 443, timeout=timeout, context=context)
        self._capability_hostname = hostname
        self._capability_address = address
        self._capability_context = context
        self._capability_deadline = time.monotonic() + timeout
        self._capability_socket: socket.socket | None = None

    def connect(self) -> None:
        # socket.create_connection would call getaddrinfo again even for a numeric
        # address. An explicit AF_INET/AF_INET6 socket avoids that lookup entirely.
        family = socket.AF_INET6 if ":" in self._capability_address else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        self._capability_socket = sock
        try:
            sock.settimeout(max(0.001, self._capability_deadline - time.monotonic()))
            sock.connect((self._capability_address, 443))
            remaining = self._capability_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("network request exceeded the total deadline")
            sock.settimeout(remaining)
            # Expose the SSL socket before its handshake so the deadline watchdog
            # can shut down a stalled handshake as well as a stalled body/header.
            wrapped = self._capability_context.wrap_socket(
                sock, server_hostname=self._capability_hostname, do_handshake_on_connect=False
            )
            self._capability_socket = wrapped
            self.sock = wrapped
            wrapped.do_handshake()
        except BaseException:
            self.abort()
            raise

    def abort(self) -> None:
        sock = self._capability_socket
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        self.close()


class NetworkClient:
    """Anonymous GET/443 with an exact allowlist or the public HTTPS policy."""

    def __init__(
        self,
        network_domains: Sequence[str],
        *,
        network_policy: str = "allowlist",
        max_bytes: int = MAX_FETCH_BYTES,
        timeout_seconds: float = MAX_FETCH_TIMEOUT_SECONDS,
        resolver: Callable[..., list[tuple[Any, ...]]] | None = None,
    ) -> None:
        domains = _canonical_domains(network_domains)
        if network_policy not in {"allowlist", "public_https"}:
            raise NetworkError("network_policy must be allowlist or public_https")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 0 < max_bytes <= MAX_FETCH_BYTES:
            raise NetworkError(f"fetch byte limit must be between 1 and {MAX_FETCH_BYTES}")
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= MAX_FETCH_TIMEOUT_SECONDS
        ):
            raise NetworkError(f"fetch timeout must be between 0 and {MAX_FETCH_TIMEOUT_SECONDS} seconds")
        self.domains = domains
        self.network_policy = network_policy
        self.max_bytes = max_bytes
        self.timeout_seconds = float(timeout_seconds)
        self._resolver = resolver or socket.getaddrinfo

    def _allowed_host(self, host: str) -> str:
        canonical = _idna_host(host)
        if self.network_policy == "allowlist" and canonical not in self.domains:
            raise NetworkError(f"network host is outside the configured public allowlist: {canonical}")
        try:
            ipaddress.ip_address(canonical)
        except ValueError:
            pass
        else:
            raise NetworkError("network URLs must use a DNS hostname, not an IP address")
        if self.network_policy == "public_https" and (
            "." not in canonical
            or all(char.isdigit() or char == "." for char in canonical)
            or any(canonical == suffix or canonical.endswith("." + suffix) for suffix in _RESERVED_HOSTS)
        ):
            raise NetworkError("public HTTPS forbids internal, reserved, or literal hosts")
        return canonical

    def _validate_url(self, value: str) -> tuple[str, urllib.parse.SplitResult]:
        if (
            not isinstance(value, str)
            or not value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise NetworkError("URL must be a non-empty string without control characters")
        try:
            parsed = urllib.parse.urlsplit(value.strip())
        except ValueError as exc:
            raise NetworkError("URL is malformed") from exc
        if parsed.scheme.lower() != "https":
            raise NetworkError("network requests require HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise NetworkError("URL credentials are forbidden")
        try:
            port = parsed.port
        except ValueError as exc:
            raise NetworkError("URL has an invalid port") from exc
        if port not in (None, 443):
            raise NetworkError("network requests only allow HTTPS port 443")
        host = self._allowed_host(parsed.hostname or "")
        normalized = parsed._replace(scheme="https", netloc=host).geturl()
        return normalized, parsed._replace(scheme="https", netloc=host)

    def _resolve_public(self, host: str, *, budget: _RequestBudget | None = None) -> tuple[str, ...]:
        budget = budget or self._new_budget()
        if not _DNS_SLOTS.acquire(timeout=budget.remaining_seconds()):
            raise NetworkError("DNS resolution exceeded the total deadline")
        answer: queue.Queue[list[tuple[Any, ...]] | Exception] = queue.Queue(maxsize=1)

        def resolve() -> None:
            try:
                answer.put(self._resolver(host, 443, type=socket.SOCK_STREAM))
            except Exception as exc:
                answer.put(exc)
            finally:
                _DNS_SLOTS.release()

        worker = threading.Thread(target=resolve, daemon=True, name="capability-dns")
        try:
            worker.start()
        except BaseException:
            _DNS_SLOTS.release()
            raise
        try:
            result = answer.get(timeout=budget.remaining_seconds())
        except queue.Empty as exc:
            raise NetworkError("DNS resolution exceeded the total deadline") from exc
        budget.remaining_seconds()
        if isinstance(result, Exception):
            raise NetworkError(f"DNS resolution failed for {host}: {result}") from result
        addresses: list[str] = []
        for info in result:
            if len(info) < 5 or not info[4]:
                continue
            address = str(info[4][0])
            if not _is_public_address(address):
                raise NetworkError(f"DNS for {host} resolved to a non-public address")
            if address not in addresses:
                addresses.append(address)
        if not addresses:
            raise NetworkError(f"DNS returned no usable address for {host}")
        return tuple(addresses[:MAX_DNS_ADDRESSES])

    @staticmethod
    def _request_target(parsed: urllib.parse.SplitResult) -> str:
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        return target

    def _new_budget(self) -> _RequestBudget:
        return _RequestBudget(time.monotonic() + self.timeout_seconds, self.max_bytes)

    def _get_once(self, url: str, *, budget: _RequestBudget) -> tuple[tuple[HTTPExchange, ...], str | None]:
        normalized, parsed = self._validate_url(url)
        host = parsed.hostname or ""
        addresses = self._resolve_public(host, budget=budget)
        context = ssl.create_default_context()
        exchanges: list[HTTPExchange] = []
        for address in addresses:
            started = time.monotonic()
            retrieved_at = datetime.now(timezone.utc).isoformat()
            status: int | None = None
            content_type: str | None = None
            location: str | None = None
            body: bytearray | None = None
            response: http.client.HTTPResponse | None = None
            try:
                remaining = budget.remaining_seconds()
            except NetworkError as exc:
                raise NetworkError(str(exc), exchanges=tuple(exchanges)) from exc
            connection = _PinnedHTTPSConnection(host, address, timeout=remaining, context=context)
            watchdog = threading.Timer(remaining, connection.abort)
            watchdog.daemon = True
            watchdog.start()
            try:
                connection.request(
                    "GET",
                    self._request_target(parsed),
                    headers={
                        "Accept": "*/*",
                        "Accept-Encoding": "identity",
                        "Connection": "close",
                        "Host": host,
                        "User-Agent": USER_AGENT,
                    },
                )
                response = connection.getresponse()
                status = response.status
                content_type = (
                    (response.getheader("Content-Type") or "application/octet-stream").split(";", 1)[0].strip().lower()
                )
                location = response.getheader("Location")
                body = bytearray()
                content_length = response.getheader("Content-Length")
                if content_length is not None:
                    try:
                        declared = int(content_length)
                    except ValueError:
                        declared = -1
                    if declared < 0:
                        raise NetworkError("response has an invalid Content-Length")
                    if declared > budget.remaining_bytes:
                        raise NetworkError(f"response exceeds the {self.max_bytes}-byte total limit")
                while True:
                    remaining = budget.remaining_seconds()
                    if connection.sock is not None:
                        connection.sock.settimeout(remaining)
                    # One sentinel byte detects undeclared overflow. It is never
                    # retained; total retained bytes stay within the shared limit.
                    chunk = response.read1(min(64 * 1024, budget.remaining_bytes + 1))
                    if not chunk:
                        break
                    accepted = chunk[: budget.remaining_bytes]
                    body.extend(accepted)
                    budget.remaining_bytes -= len(accepted)
                    if len(accepted) != len(chunk):
                        raise NetworkError(f"response exceeds the {self.max_bytes}-byte total limit")
                budget.remaining_seconds()
                if content_length is not None and len(body) != int(content_length):
                    raise NetworkError("response ended before its declared Content-Length")
                exchanges.append(
                    HTTPExchange(
                        normalized,
                        retrieved_at,
                        time.monotonic() - started,
                        status,
                        content_type,
                        bytes(body),
                        True,
                        location=location,
                    )
                )
                return tuple(exchanges), location
            except (NetworkError, OSError, http.client.HTTPException) as exc:
                if isinstance(exc, http.client.IncompleteRead) and body is not None:
                    accepted = exc.partial[: budget.remaining_bytes]
                    body.extend(accepted)
                    budget.remaining_bytes -= len(accepted)
                error = str(exc)
                if time.monotonic() >= budget.deadline:
                    error = "network request exceeded the total deadline"
                exchanges.append(
                    HTTPExchange(
                        normalized,
                        retrieved_at,
                        time.monotonic() - started,
                        status,
                        content_type,
                        bytes(body) if body is not None else None,
                        False,
                        error,
                        location,
                    )
                )
                # A received response is evidence, not an invitation to redownload
                # it from another address. Retry only connection-level failures.
                if isinstance(exc, NetworkError) or status is not None or time.monotonic() >= budget.deadline:
                    raise NetworkError(error, exchanges=tuple(exchanges)) from exc
            finally:
                watchdog.cancel()
                if response is not None:
                    response.close()
                connection.abort()
        raise NetworkError(f"HTTPS request failed for {normalized}: {exchanges[-1].error}", exchanges=tuple(exchanges))

    def fetch(self, url: str, *, _budget: _RequestBudget | None = None) -> FetchResponse:
        """GET with one deadline and byte budget across DNS, addresses, and hops."""

        budget = _budget or self._new_budget()
        requested, _ = self._validate_url(url)
        current = requested
        redirects: list[str] = []
        exchanges: list[HTTPExchange] = []
        try:
            for _ in range(MAX_REDIRECTS + 1):
                budget.remaining_seconds()
                hop_exchanges, location = self._get_once(current, budget=budget)
                exchanges.extend(hop_exchanges)
                hop = hop_exchanges[-1]
                if hop.status in {301, 302, 303, 307, 308}:
                    if not location:
                        raise NetworkError(f"redirect from {current} has no Location header")
                    next_url = urllib.parse.urljoin(current, location)
                    normalized, _ = self._validate_url(next_url)
                    if len(redirects) >= MAX_REDIRECTS:
                        raise NetworkError("too many redirects")
                    redirects.append(normalized)
                    current = normalized
                    continue
                assert hop.status is not None and hop.body is not None
                return FetchResponse(
                    requested,
                    current,
                    hop.status,
                    hop.content_type or "application/octet-stream",
                    hop.body,
                    tuple(redirects),
                    tuple(exchanges),
                )
        except NetworkError as exc:
            raise NetworkError(
                str(exc), final_url=current, redirects=tuple(redirects), exchanges=tuple(exchanges) + exc.exchanges
            ) from exc
        raise NetworkError(
            "too many redirects", final_url=current, redirects=tuple(redirects), exchanges=tuple(exchanges)
        )

    def _search_backends(self) -> tuple[tuple[str, str], ...]:
        # Search endpoint selection is independent of URLs returned as results.
        # Broad public research does not enable arbitrary search backend URLs.
        backends: list[tuple[str, str]] = []
        if self.network_policy == "public_https" or "html.duckduckgo.com" in self.domains:
            backends.append(("duckduckgo-html", "https://html.duckduckgo.com/html/"))
        if self.network_policy == "public_https" or "www.bing.com" in self.domains:
            backends.append(("bing-rss", "https://www.bing.com/search"))
        return tuple(backends)

    def search(self, query: str) -> SearchResult:
        """Search fixed anonymous backends, retaining every attempted response."""

        if not isinstance(query, str) or not query.strip():
            raise NetworkError("search query must be a non-empty string")
        if len(query) > MAX_SEARCH_QUERY_CHARS or "\x00" in query:
            raise NetworkError("search query is too long or contains a NUL byte")
        backends = self._search_backends()
        if not backends:
            raise NetworkError("search requires html.duckduckgo.com or www.bing.com in network_domains")
        attempts: list[SearchAttempt] = []
        budget = self._new_budget()
        for backend, endpoint in backends:
            params = {"q": query} if backend == "duckduckgo-html" else {"q": query, "format": "rss"}
            target = endpoint + "?" + urllib.parse.urlencode(params)
            started = time.monotonic()
            retrieved_at = datetime.now(timezone.utc).isoformat()
            response: FetchResponse | None = None
            try:
                response = self.fetch(target, _budget=budget)
                if not 200 <= response.status < 300:
                    raise NetworkError(f"search backend returned HTTP {response.status}")
                results = (
                    _parse_duckduckgo(response.body)
                    if backend == "duckduckgo-html"
                    else _parse_bing_rss(response.body)
                )
                if not results:
                    raise NetworkError(f"{backend} returned no parseable results")
                budget.remaining_seconds()
            except NetworkError as exc:
                exchanges = response.exchanges if response is not None else exc.exchanges
                if response is not None and not exchanges:
                    exchanges = (
                        HTTPExchange(
                            response.final_url,
                            retrieved_at,
                            time.monotonic() - started,
                            response.status,
                            response.content_type,
                            response.body,
                            True,
                        ),
                    )
                attempts.append(
                    SearchAttempt(
                        backend,
                        target,
                        response.final_url if response is not None else exc.final_url or target,
                        response.redirects if response is not None else exc.redirects,
                        retrieved_at,
                        time.monotonic() - started,
                        response.status
                        if response is not None
                        else next(
                            (item.status for item in reversed(exchanges) if item.url == (exc.final_url or target)),
                            None,
                        ),
                        str(exc),
                        exchanges,
                    )
                )
                continue
            exchanges = response.exchanges or (
                HTTPExchange(
                    response.final_url,
                    retrieved_at,
                    time.monotonic() - started,
                    response.status,
                    response.content_type,
                    response.body,
                    True,
                ),
            )
            attempts.append(
                SearchAttempt(
                    backend,
                    target,
                    response.final_url,
                    response.redirects,
                    retrieved_at,
                    time.monotonic() - started,
                    response.status,
                    None,
                    exchanges,
                )
            )
            return SearchResult(query, backend, response.final_url, response, tuple(results), tuple(attempts))
        raise NetworkError(
            "all configured search backends failed: "
            + "; ".join(f"{item.backend}: {item.error}" for item in attempts),
            attempts=tuple(attempts),
        )


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._anchor_depth = 0
        self._snippet_depth = 0
        self._text_target: str | None = None

    @staticmethod
    def _classes(attrs: Sequence[tuple[str, str | None]]) -> set[str]:
        value = next((item for key, item in attrs if key == "class"), None) or ""
        return set(value.split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attrs)
        if tag == "a" and "result__a" in classes and self._current is None:
            href = next((value for key, value in attrs if key == "href"), None)
            if href:
                self._current = {"url": _unwrap_search_link(html.unescape(href)), "title": "", "snippet": ""}
                self._anchor_depth = 1
                self._text_target = "title"
                return
        if self._current is not None and tag == "a":
            self._anchor_depth += 1
        if self._current is not None and tag == "a" and "result__snippet" in classes:
            self._snippet_depth = 1
            self._text_target = "snippet"
        elif self._current is not None and "result__snippet" in classes:
            self._snippet_depth = 1
            self._text_target = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "a" and self._anchor_depth:
            self._anchor_depth -= 1
            if not self._anchor_depth and self._text_target == "title":
                self._text_target = None
        if self._snippet_depth and tag in {"div", "a", "span"}:
            self._snippet_depth -= 1
            if not self._snippet_depth:
                self._text_target = None
                self._finish()

    def handle_data(self, data: str) -> None:
        if self._current is None or self._text_target is None:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self._current[self._text_target] = (self._current[self._text_target] + " " + text).strip()

    def _finish(self) -> None:
        if self._current is None:
            return
        value = {
            "title": self._current.get("title", "")[:500],
            "url": self._current.get("url", "")[:4_000],
            "snippet": self._current.get("snippet", "")[:2_000],
        }
        if value["url"] and len(self.results) < MAX_SEARCH_RESULTS:
            self.results.append(value)
        self._current = None
        self._anchor_depth = 0
        self._snippet_depth = 0
        self._text_target = None


def _unwrap_search_link(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme in {"http", "https"}:
        return value
    if parsed.path.startswith("/l/") or parsed.path == "/l/":
        query = urllib.parse.parse_qs(parsed.query)
        target = query.get("uddg", [""])[0]
        if target:
            return urllib.parse.unquote(target)
    if value.startswith("//"):
        return "https:" + value
    return value


def _parse_duckduckgo(body: bytes) -> list[dict[str, str]]:
    parser = _DuckDuckGoParser()
    try:
        parser.feed(body.decode("utf-8", errors="replace"))
        parser.close()
    except Exception as exc:  # HTMLParser should be forgiving, but never break the service.
        raise NetworkError(f"search response could not be parsed: {exc}") from exc
    if parser._current is not None:
        parser._finish()
    return parser.results


def _parse_bing_rss(body: bytes) -> list[dict[str, str]]:
    import xml.etree.ElementTree as ElementTree

    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise NetworkError(f"search RSS response could not be parsed: {exc}") from exc
    results: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        snippet = (item.findtext("description") or "").strip()
        if title and url and len(results) < MAX_SEARCH_RESULTS:
            results.append({"title": title[:500], "url": url[:4_000], "snippet": snippet[:2_000]})
    return results


def fetch_summary(response: FetchResponse, *, body_sha256: str, visible_path: str | None = None) -> dict[str, Any]:
    """Create a JSON-safe receipt without embedding response bytes."""

    result: dict[str, Any] = {
        "requested_url": response.requested_url,
        "final_url": response.final_url,
        "redirects": list(response.redirects),
        "status": response.status,
        "content_type": response.content_type,
        "bytes": response.byte_count,
        "sha256": body_sha256,
    }
    if visible_path is not None:
        result["path"] = visible_path
    return result


def search_summary(result: SearchResult, *, body_sha256: str, visible_path: str | None = None) -> dict[str, Any]:
    summary = fetch_summary(result.response, body_sha256=body_sha256, visible_path=visible_path)
    summary.update({"query": result.query, "backend": result.backend, "results": list(result.results)})
    return summary


def json_summary(value: Mapping[str, Any]) -> str:
    """Stable bounded JSON text for an MCP ``text`` content block."""

    return json.dumps(dict(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
