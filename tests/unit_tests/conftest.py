# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

_VARS = (
    "VERICTO_API_KEY",
    "VERICTO_DATABASE_ID",
    "VERICTO_API_URL",
    "VERICTO_OFFLINE",
    "VERICTO_FAIL_MODE",
    "VERICTO_CLI",
)


@pytest.fixture(autouse=True)
def _clean_vericto_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests never read the developer's Vericto configuration."""
    for name in _VARS:
        monkeypatch.delenv(name, raising=False)
