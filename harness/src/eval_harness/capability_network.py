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
import re
import socket
import ssl
import urllib.parse
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Callable, Iterable, Mapping, Sequence

from .errors import HarnessError

MAX_FETCH_BYTES = 20 * 1024 * 1024
MAX_FETCH_TIMEOUT_SECONDS = 30.0
MAX_REDIRECTS = 5
MAX_SEARCH_QUERY_CHARS = 2_000
MAX_SEARCH_RESULTS = 10
USER_AGENT = "eval-harness-capability/1"


class NetworkError(HarnessError):
    """A URL did not satisfy the public network policy or its request failed."""


@dataclass(frozen=True)
class FetchResponse:
    """Bounded response bytes and metadata from one safe GET request."""

    requested_url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    redirects: tuple[str, ...] = ()

    @property
    def byte_count(self) -> int:
        return len(self.body)


@dataclass(frozen=True)
class SearchResult:
    """Public search results plus the response provenance needed for a receipt."""

    query: str
    backend: str
    url: str
    response: FetchResponse
    results: tuple[dict[str, str], ...]


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
    """HTTPSConnection that never performs a second DNS lookup."""

    def __init__(self, hostname: str, address: str, *, timeout: float, context: ssl.SSLContext) -> None:
        # The base class stores a host used for request headers and error messages.
        # ``connect`` below uses the already resolved address instead.
        super().__init__(hostname, 443, timeout=timeout, context=context)
        self._capability_hostname = hostname
        self._capability_address = address
        self._capability_context = context

    def connect(self) -> None:
        sock = socket.create_connection((self._capability_address, self.port), self.timeout)
        try:
            self.sock = self._capability_context.wrap_socket(sock, server_hostname=self._capability_hostname)
        except BaseException:
            sock.close()
            raise


class NetworkClient:
    """Perform policy-checked public HTTPS GETs and the shared HTML search."""

    def __init__(
        self,
        network_domains: Sequence[str],
        *,
        max_bytes: int = MAX_FETCH_BYTES,
        timeout_seconds: float = MAX_FETCH_TIMEOUT_SECONDS,
        resolver: Callable[..., list[tuple[Any, ...]]] | None = None,
    ) -> None:
        domains = _canonical_domains(network_domains)
        if max_bytes <= 0 or max_bytes > MAX_FETCH_BYTES:
            raise NetworkError(f"fetch byte limit must be between 1 and {MAX_FETCH_BYTES}")
        if timeout_seconds <= 0 or timeout_seconds > MAX_FETCH_TIMEOUT_SECONDS:
            raise NetworkError(f"fetch timeout must be between 0 and {MAX_FETCH_TIMEOUT_SECONDS} seconds")
        self.domains = domains
        self.max_bytes = int(max_bytes)
        self.timeout_seconds = float(timeout_seconds)
        self._resolver = resolver or socket.getaddrinfo

    def _allowed_host(self, host: str) -> str:
        canonical = _idna_host(host)
        if canonical not in self.domains:
            raise NetworkError(f"network host is outside the configured public allowlist: {canonical}")
        # Literal IP URLs bypass DNS and make the allowlist easier to accidentally
        # broaden.  Public HTTPS should use a hostname so certificate pinning stays
        # meaningful.
        try:
            ipaddress.ip_address(canonical)
        except ValueError:
            return canonical
        raise NetworkError("network URLs must use a DNS hostname, not an IP address")

    def _validate_url(self, value: str) -> tuple[str, urllib.parse.SplitResult]:
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise NetworkError("URL must be a non-empty string without NUL bytes")
        parsed = urllib.parse.urlsplit(value.strip())
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
        # Normalize the host while preserving the path/query exactly as supplied.
        normalized = parsed._replace(scheme="https", netloc=host).geturl()
        return normalized, parsed._replace(scheme="https", netloc=host)

    def _resolve_public(self, host: str) -> tuple[str, ...]:
        try:
            infos = self._resolver(host, 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise NetworkError(f"DNS resolution failed for {host}: {exc}") from exc
        addresses: list[str] = []
        for info in infos:
            if len(info) < 5:
                continue
            sockaddr = info[4]
            if not sockaddr:
                continue
            address = str(sockaddr[0])
            if not _is_public_address(address):
                raise NetworkError(f"DNS for {host} resolved to a non-public address")
            if address not in addresses:
                addresses.append(address)
        if not addresses:
            raise NetworkError(f"DNS returned no usable address for {host}")
        return tuple(addresses)

    @staticmethod
    def _request_target(parsed: urllib.parse.SplitResult) -> str:
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        return target

    def _get_once(self, url: str) -> tuple[int, str, bytes, str | None]:
        normalized, parsed = self._validate_url(url)
        host = parsed.hostname or ""
        addresses = self._resolve_public(host)
        context = ssl.create_default_context()
        last_error: BaseException | None = None
        for address in addresses:
            connection = _PinnedHTTPSConnection(host, address, timeout=self.timeout_seconds, context=context)
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
                content_length = response.getheader("Content-Length")
                if content_length is not None:
                    try:
                        declared = int(content_length)
                    except ValueError:
                        declared = -1
                    if declared < 0:
                        raise NetworkError("response has an invalid Content-Length")
                    if declared > self.max_bytes:
                        raise NetworkError(f"response exceeds the {self.max_bytes}-byte limit")
                body = response.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise NetworkError(f"response exceeds the {self.max_bytes}-byte limit")
                content_type = response.getheader("Content-Type") or "application/octet-stream"
                location = response.getheader("Location")
                return response.status, content_type, body, location
            except NetworkError:
                raise
            except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
                last_error = exc
            finally:
                connection.close()
        raise NetworkError(f"HTTPS request failed for {normalized}: {last_error}")

    def fetch(self, url: str) -> FetchResponse:
        """GET a public allowlisted URL with bounded, validated redirects."""

        requested, _ = self._validate_url(url)
        current = requested
        redirects: list[str] = []
        for _ in range(MAX_REDIRECTS + 1):
            status, content_type, body, location = self._get_once(current)
            if len(body) > self.max_bytes:
                raise NetworkError(f"response exceeds the {self.max_bytes}-byte limit")
            if status in {301, 302, 303, 307, 308}:
                if not location:
                    raise NetworkError(f"redirect from {current} has no Location header")
                next_url = urllib.parse.urljoin(current, location)
                normalized, _ = self._validate_url(next_url)
                redirects.append(normalized)
                current = normalized
                if len(redirects) > MAX_REDIRECTS:
                    raise NetworkError("too many redirects")
                continue
            return FetchResponse(
                requested_url=requested,
                final_url=current,
                status=status,
                content_type=content_type.split(";", 1)[0].strip().lower() or "application/octet-stream",
                body=body,
                redirects=tuple(redirects),
            )
        raise NetworkError("too many redirects")

    def _search_backends(self) -> tuple[tuple[str, str], ...]:
        # Keep one ordered backend contract for all roles.  Bing RSS is an
        # explicitly allowlisted fallback for installations where DDG is blocked;
        # it is never contacted unless its host was selected by configuration.
        backends: list[tuple[str, str]] = []
        if "html.duckduckgo.com" in self.domains:
            backends.append(("duckduckgo-html", "https://html.duckduckgo.com/html/"))
        if "www.bing.com" in self.domains:
            backends.append(("bing-rss", "https://www.bing.com/search"))
        return tuple(backends)

    def search(self, query: str) -> SearchResult:
        """Search via the configured public unauthenticated backend."""

        if not isinstance(query, str) or not query.strip():
            raise NetworkError("search query must be a non-empty string")
        if len(query) > MAX_SEARCH_QUERY_CHARS or "\x00" in query:
            raise NetworkError("search query is too long or contains a NUL byte")
        backends = self._search_backends()
        if not backends:
            raise NetworkError("search requires html.duckduckgo.com or www.bing.com in network_domains")
        errors: list[str] = []
        for backend, endpoint in backends:
            if backend == "duckduckgo-html":
                target = endpoint + "?" + urllib.parse.urlencode({"q": query})
            else:
                target = endpoint + "?" + urllib.parse.urlencode({"q": query, "format": "rss"})
            try:
                response = self.fetch(target)
                if not 200 <= response.status < 300:
                    raise NetworkError(f"search backend returned HTTP {response.status}")
                results = (
                    _parse_duckduckgo(response.body)
                    if backend == "duckduckgo-html"
                    else _parse_bing_rss(response.body)
                )
                if not results:
                    raise NetworkError(f"{backend} returned no parseable results")
                return SearchResult(query, backend, response.final_url, response, tuple(results))
            except NetworkError as exc:
                errors.append(f"{backend}: {exc}")
        raise NetworkError("all configured search backends failed: " + "; ".join(errors))


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
