# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Pinned model names and native effort capabilities, not account entitlements.

Claude Code 2.1.270 and its official model-config documentation were inspected
on 2026-09-14. Preflight must additionally verify the account's live access.
Aliases are deliberately excluded because they may select another release.
"""

from __future__ import annotations

CODEX_EFFORTS: dict[str, frozenset[str]] = {
    "gpt-5.6-luna": frozenset({"low", "medium", "high", "xhigh", "max"}),
    "gpt-5.6-sol": frozenset({"low", "medium", "high", "xhigh", "max", "ultra"}),
    "gpt-5.6-terra": frozenset({"low", "medium", "high", "xhigh", "max", "ultra"}),
    "gpt-6-astra": frozenset({"low", "medium", "high", "xhigh", "max", "ultra"}),
}
CLAUDE_EFFORTS: dict[str, frozenset[str]] = {
    "claude-fable-5-1": frozenset({"low", "medium", "high", "xhigh", "max"}),
    "claude-opus-5": frozenset({"low", "medium", "high", "xhigh", "max"}),
    "claude-sonnet-5": frozenset({"low", "medium", "high", "xhigh", "max"}),
    "claude-haiku-4-5-20251001": frozenset(),
    # Retained for configurations and saved runs already supported by 0.1.0.
    "claude-sonnet-4-6": frozenset({"low", "medium", "high", "max"}),
}
MODEL_EFFORTS = {**CODEX_EFFORTS, **CLAUDE_EFFORTS}
CLAUDE_DISPLAY_NAMES = {
    "claude-fable-5-1": "Fable 5.1",
    "claude-opus-5": "Opus 5",
    "claude-sonnet-5": "Sonnet 5",
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "claude-sonnet-4-6": "Sonnet 4.6",
}
