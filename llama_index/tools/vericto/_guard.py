# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""Building the `vericto.Vericto` guard that evaluates statements."""

from __future__ import annotations

from typing import Literal

from vericto import Vericto

FailMode = Literal["closed", "open"]


def build_guard(
    *,
    offline: bool | None = None,
    api_key: str | None = None,
    database_id: str | None = None,
    api_url: str | None = None,
    fail_mode: FailMode | None = "closed",
    timeout: float | None = None,
    offline_cli_path: str | None = None,
) -> Vericto:
    """Build a `vericto.Vericto` guard.

    * Offline (`offline=True` or `VERICTO_OFFLINE=1`): the local engine of the
      `vericto` CLI (2.1.0 or later, `vericto serve --stdio`), its standard rules,
      no account and no network.
    * Online (the default): the Vericto Runtime API with your workspace's rules.
      Needs an API key (`VERICTO_API_KEY`, scope `proxy:evaluate`) and the database
      id registered in your workspace (`VERICTO_DATABASE_ID`).

    Offline mode is never chosen on its own: without it and without an API key the
    guard raises `vericto.VerictoConfigError`. Combining both raises too.

    `fail_mode` is what happens when Vericto cannot answer: `"closed"` (default)
    raises `vericto.VerictoUnavailable` and nothing runs; `"open"` lets the
    statement through unevaluated. `None` defers to `VERICTO_FAIL_MODE` (closed
    when unset).
    """
    # One call: the SDK refuses offline mode combined with an API key, database id
    # or API URL ("choose one") rather than silently dropping either.
    return Vericto(
        api_key=api_key,
        database_id=database_id,
        api_url=api_url,
        fail_mode=fail_mode,
        timeout=timeout,
        offline=offline,
        offline_cli_path=offline_cli_path,
    )
