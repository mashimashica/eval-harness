# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from eval_harness import capability_environment as environment
from eval_harness.errors import ConfigError


def test_public_network_and_native_commands_are_explicit(tmp_path: Path) -> None:
    parsed = environment.parse_environment({"profile": "gdpval-v2", "network_policy": "public_https"}, tmp_path)
    assert parsed == {"profile": "gdpval-v2", "network_policy": "public_https", "network_domains": []}
    assert environment.enabled({"environment": parsed})
    assert (
        environment.parse_environment({"profile": "gdpval-v1", "network_domains": []}, tmp_path)["network_policy"]
        == "allowlist"
    )
    with pytest.raises(ConfigError, match="must be empty"):
        environment.parse_environment({**parsed, "network_domains": ["example.org"]}, tmp_path)
    with pytest.raises(ConfigError, match="only ffmpeg"):
        environment.parse_environment({**parsed, "executables": {"python": "/usr/bin/python3"}}, tmp_path)
    native = tmp_path / "node"
    native.write_text("test executable")
    with pytest.raises(ConfigError, match="unavailable"):
        environment.parse_environment({**parsed, "executables": {"node": "node"}}, tmp_path)
    native.chmod(0o700)
    assert environment.parse_environment({**parsed, "executables": {"node": "node"}}, tmp_path)["executables"] == {
        "node": str(native)
    }


def test_dependency_closure_uses_active_requirements_and_never_optional_extras(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(environment, "PACKAGES", ("base",))
    monkeypatch.setattr(environment, "EXTENDED_PACKAGES", ("feature",))
    requirements = {
        "base": ["shared>=1", "ambient; extra == 'danger'"],
        "feature": ["shared>=1", "inactive; python_version < '3.0'"],
        "shared": ["base>=1"],
    }

    def distribution(name: str) -> Any:
        return SimpleNamespace(requires=requirements[name])

    monkeypatch.setattr(environment.importlib.metadata, "distribution", distribution)
    assert environment.runtime_packages("gdpval-v2") == ("base", "feature", "shared")
    assert environment.runtime_packages("gdpval-v1") == ("base",)


def test_prompt_declares_actual_policy_and_optional_programs() -> None:
    public = environment.environment_prompt(
        "application",
        {"profile": "gdpval-v2", "network_policy": "public_https", "executables": {"node": "/configured/node"}},
    )
    assert "per-hop DNS/address validation" in public
    assert "Configured native commands: node" in public
    assert "OCP" in public
    assert "Configured native commands" not in environment.environment_prompt("application")
    assert "configured public HTTPS domains" in environment.environment_prompt("application")
