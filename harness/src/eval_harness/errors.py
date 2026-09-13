# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Errors raised by the local harness."""


class HarnessError(Exception):
    """Base class for expected user-facing harness errors."""


class ConfigError(HarnessError):
    """A YAML configuration cannot be used."""


class OutputExistsError(HarnessError):
    """An operation would overwrite an existing output directory."""


class ArtifactError(HarnessError):
    """A saved artifact or immutable input is missing or invalid."""
