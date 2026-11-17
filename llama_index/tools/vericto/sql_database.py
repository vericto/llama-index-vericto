# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""`VerictoSQLDatabase`: a LlamaIndex `SQLDatabase` that checks every statement first."""

from __future__ import annotations

from typing import Any, Literal, Self

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

from llama_index.tools.vericto._guard import FailMode, build_guard
from vericto import Vericto
from vericto.llamaindex import VerictoSQLDatabase as _SDKVerictoSQLDatabase


class VerictoSQLDatabase(_SDKVerictoSQLDatabase):
    """A `llama_index.core.SQLDatabase` whose statements Vericto checks.

    It goes wherever a `SQLDatabase` goes (`NLSQLTableQueryEngine`,
    `SQLTableRetrieverQueryEngine`, `NLSQLRetriever`, `VerictoToolSpec`): every
    statement that `run_sql` or `insert_into_table` sends through SQLAlchemy is
    checked by Vericto first, in the dialect of the engine.

    * Blocked: nothing runs. With `on_block="return"` (default) `run_sql` returns
      an `Error: Vericto blocked this query (VERICTO-001, ...)` message with the
      rule and the suggested fix as the SQL result, and the metadata carries
      `vericto_blocked`; the query engine's answer then says why. With
      `on_block="raise"` it raises `vericto.VerictoBlocked`. `insert_into_table`
      always raises on a block.
    * Masked (online): the rewrite with masked sensitive columns runs instead.
    * Flagged / monitored: runs, and is logged on the `vericto` logger.
    * Vericto unavailable: `fail_mode="closed"` (default) raises
      `vericto.VerictoUnavailable` and nothing runs; `fail_mode="open"` runs the
      statement unevaluated with a `vericto.VerictoFailOpenWarning`.

    Schema reflection is not sent to Vericto. The class is built on the Vericto
    SDK's `vericto.llamaindex` integration.

    Args:
        engine: the SQLAlchemy engine; `from_uri(...)` works too.
        *args: passed to `SQLDatabase`.
        offline: `True` for the local engine of the Vericto CLI (no account, the
            standard rules); `None` (default) reads `VERICTO_OFFLINE`; online
            otherwise (`VERICTO_API_KEY` and `VERICTO_DATABASE_ID`).
        api_key: Vericto API key (`proxy:evaluate` scope); default `VERICTO_API_KEY`.
        database_id: database registered in your workspace; default
            `VERICTO_DATABASE_ID`.
        api_url: Vericto API URL; default `VERICTO_API_URL`, then the public API.
        fail_mode: `"closed"` (default) or `"open"`; `None` reads `VERICTO_FAIL_MODE`.
        timeout: seconds per evaluation.
        offline_cli_path: the `vericto` binary; default `VERICTO_CLI`, then PATH.
        guard: an existing `vericto.Vericto`, instead of the arguments above.
        dialect: the Vericto dialect; read from `engine.dialect.name` when omitted.
        on_block: `"return"` (default) or `"raise"`.
        **kwargs: passed to `SQLDatabase` (`include_tables`, ...), and `context` /
            `end_user` for business policies (see the Vericto SDK).

    Example:
        ```python
        from llama_index.tools.vericto import VerictoSQLDatabase

        db = VerictoSQLDatabase.from_uri("sqlite:///shop.db", offline=True)
        db.run_sql("DELETE FROM orders")[0]
        # 'Error: Vericto blocked this query (VERICTO-001, severity critical). ...'
        ```
    """

    def __init__(
        self,
        engine: Engine,
        *args: Any,
        offline: bool | None = None,
        api_key: str | None = None,
        database_id: str | None = None,
        api_url: str | None = None,
        fail_mode: FailMode | None = "closed",
        timeout: float | None = None,
        offline_cli_path: str | None = None,
        guard: Vericto | None = None,
        dialect: str | None = None,
        on_block: Literal["return", "raise"] = "return",
        **kwargs: Any,
    ) -> None:
        """Build the guard (unless `guard` is given) and the checked `SQLDatabase`."""
        owns = guard is None
        if guard is None:
            guard = build_guard(
                offline=offline,
                api_key=api_key,
                database_id=database_id,
                api_url=api_url,
                fail_mode=fail_mode,
                timeout=timeout,
                offline_cli_path=offline_cli_path,
            )
        try:
            super().__init__(
                engine, *args, guard=guard, dialect=dialect, on_block=on_block, **kwargs
            )
        except BaseException:
            if owns:
                guard.close()
            raise
        self._li_vericto_owns_guard = owns

    @classmethod
    def from_uri(
        cls,
        database_uri: str | URL,
        engine_args: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Self:
        """Connect with a SQLAlchemy URL; `kwargs` are the arguments of the constructor."""
        return cls(create_engine(database_uri, **(engine_args or {})), **kwargs)

    def close(self) -> None:
        """Stop checking and close the guard this database built.

        Detaches the listener from the engine; closes the guard (its HTTP pool, or
        the `vericto serve` process offline) unless it was passed in with `guard=`.
        """
        self.close_vericto()
        if self._li_vericto_owns_guard:
            self.vericto_guard.close()
