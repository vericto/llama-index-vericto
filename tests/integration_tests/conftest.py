# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests run against the real Vericto engine.

* Offline (`test_offline.py`): the local engine of the Vericto CLI 2.1.0 or
  later (`vericto serve --stdio`), found through `VERICTO_CLI` or PATH. Skipped
  when there is none, unless `VERICTO_REQUIRE_CLI=1` (CI), which fails instead.
* Online (`test_online.py`): the Vericto Runtime API. Skipped unless
  `VERICTO_API_KEY` and `VERICTO_DATABASE_ID` are set.
"""

from __future__ import annotations

import os
import subprocess
from typing import NoReturn

import pytest
from vericto import VerictoConfigError
from vericto.offline import MIN_CLI_VERSION, find_cli, parse_version


def _missing(reason: str) -> NoReturn:
    if os.environ.get("VERICTO_REQUIRE_CLI", "").strip() == "1":
        pytest.fail(f"VERICTO_REQUIRE_CLI=1 but {reason}")
    pytest.skip(reason)


def require_cli() -> str:
    """The Vericto CLI to use offline: found, and recent enough for `vericto serve`."""
    try:
        cli = find_cli()
    except VerictoConfigError as exc:
        _missing(f"no Vericto CLI for offline mode: {exc}")
    out = subprocess.run(
        [cli, "--version"], capture_output=True, text=True, check=False, timeout=10
    )
    version = parse_version(out.stdout)
    if version is None or version < MIN_CLI_VERSION:
        wanted = ".".join(map(str, MIN_CLI_VERSION))
        _missing(f"{cli} is {out.stdout.strip() or 'unknown'}; offline mode needs {wanted}+")
    return cli


@pytest.fixture
def offline_env(monkeypatch: pytest.MonkeyPatch) -> str:
    """A Vericto CLI, and no online configuration (offline mode refuses one)."""
    cli = require_cli()
    for name in ("VERICTO_API_KEY", "VERICTO_DATABASE_ID", "VERICTO_API_URL", "VERICTO_OFFLINE"):
        monkeypatch.delenv(name, raising=False)
    return cli
