# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import socket

import pytest

from eval_harness.capability_network import (
    NetworkClient,
    NetworkError,
    _is_public_address,
    _parse_duckduckgo,
)


def _resolver(host: str, port: int, *, type: int) -> list[tuple[int, int, int, str, tuple[str, int]]]:
    assert host == "docs.example"
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))]


def test_network_policy_requires_https_allowlisted_dns_and_public_resolution() -> None:
    client = NetworkClient(["docs.example"], resolver=_resolver)
    assert client._validate_url("https://docs.example/guide?q=1")[0] == "https://docs.example/guide?q=1"

    with pytest.raises(NetworkError, match="HTTPS"):
        client._validate_url("http://docs.example/guide")
    with pytest.raises(NetworkError, match="allowlist"):
        client._validate_url("https://other.example/guide")
    with pytest.raises(NetworkError, match="allowlist"):
        client._validate_url("https://sub.docs.example/guide")
    with pytest.raises(NetworkError, match="credentials"):
        client._validate_url("https://user:secret@docs.example/guide")


def test_private_dns_answers_fail_closed_even_when_domain_is_allowlisted() -> None:
    def private_resolver(host: str, port: int, *, type: int) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", port))]

    client = NetworkClient(["example"], resolver=private_resolver)
    with pytest.raises(NetworkError, match="non-public"):
        client._resolve_public("docs.example")


def test_public_address_check_rejects_multicast_reserved_and_private_ranges() -> None:
    assert _is_public_address("93.184.216.34")
    for value in ("224.0.0.1", "240.0.0.1", "192.0.2.1", "10.0.0.1", "::1", "ff02::1"):
        assert not _is_public_address(value)


def test_fetch_validates_every_redirect_and_bounds_response(monkeypatch: pytest.MonkeyPatch) -> None:
    client = NetworkClient(["docs.example"], resolver=_resolver, max_bytes=8)
    responses = iter(
        [
            (302, "text/html", b"redirect", "https://docs.example/next"),
            (200, "text/plain; charset=utf-8", b"content", None),
        ]
    )
    monkeypatch.setattr(client, "_get_once", lambda url: next(responses))
    fetched = client.fetch("https://docs.example/start")
    assert fetched.final_url == "https://docs.example/next"
    assert fetched.redirects == ("https://docs.example/next",)
    assert fetched.content_type == "text/plain"
    assert fetched.body == b"content"

    oversized = NetworkClient(["docs.example"], resolver=_resolver, max_bytes=4)
    monkeypatch.setattr(oversized, "_get_once", lambda url: (200, "text/plain", b"12345", None))
    with pytest.raises(NetworkError, match="limit"):
        oversized.fetch("https://docs.example/start")


def test_duckduckgo_parser_returns_title_url_and_bounded_snippet() -> None:
    body = b"""
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.example%2Fpython">Python docs</a>
      <a class="result__snippet">A <b>useful</b> snippet.</a>
    </div>
    """
    results = _parse_duckduckgo(body)
    assert results == [{"title": "Python docs", "url": "https://docs.example/python", "snippet": "A useful snippet."}]
