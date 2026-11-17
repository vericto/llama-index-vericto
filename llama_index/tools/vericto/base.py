# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""`VerictoToolSpec`: Vericto's verdict for a SQL statement, and guarded SQL tools."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Literal

from llama_index.core.bridge.pydantic import BaseModel, Field
from llama_index.core.tools import FunctionTool, ToolMetadata
from llama_index.core.tools.tool_spec.base import SPEC_FUNCTION_TYPE, BaseToolSpec

from llama_index.tools.vericto._guard import FailMode, build_guard
from llama_index.tools.vericto._verdict import verdict_to_dict
from llama_index.tools.vericto.sql_database import VerictoSQLDatabase
from vericto import Verdict, Vericto, normalize_dialect

Dialect = Literal["postgres", "mysql", "oracle", "mssql", "snowflake", "sqlite"]

_CONNECTION_ARGS = (
    "offline",
    "api_key",
    "database_id",
    "api_url",
    "timeout",
    "offline_cli_path",
    "guard",
)


class CheckSQLInput(BaseModel):
    """Input of `check_sql`."""

    query: str = Field(
        description="The exact SQL statement (or statements) you intend to run.", min_length=1
    )
    dialect: Dialect | None = Field(
        default=None,
        description="The SQL dialect of the database. Omit it to use the default.",
    )


class RunSQLInput(BaseModel):
    """Input of `run_sql`."""

    query: str = Field(description="The SQL query to run, in the database's dialect.", min_length=1)


class ListTablesInput(BaseModel):
    """Input of `list_tables` (none)."""


class DescribeTablesInput(BaseModel):
    """Input of `describe_tables`."""

    tables: list[str] | None = Field(
        default=None,
        description="The table names to describe. Omit it to describe every table.",
    )


# What the model reads: one description and one input schema per tool. Set
# explicitly so the descriptions stay short and the schemas carry their constraints.
_TOOL_METADATA: dict[str, ToolMetadata] = {
    "check_sql": ToolMetadata(
        name="check_sql",
        description=(
            "Check a SQL query with Vericto (database guardrails for AI agents) BEFORE "
            "running it. Nothing is executed. Returns JSON with `allowed`, `blocked`, the "
            "matched `rule_codes`, a `suggested_fix` and a `summary`. Do not run a query "
            "this tool reports as blocked: rewrite it following the suggested fix and "
            "check it again."
        ),
        fn_schema=CheckSQLInput,
    ),
    "run_sql": ToolMetadata(
        name="run_sql",
        description=(
            "Run a SQL query on the database and return the rows. Vericto checks the "
            "query first. A blocked query is NOT executed: the result starts with "
            '"Error: Vericto blocked this query" and gives the rule and a suggested fix. '
            "Rewrite the query following it, or tell the user it cannot be run."
        ),
        fn_schema=RunSQLInput,
    ),
    "list_tables": ToolMetadata(
        name="list_tables",
        description="List the tables you may query. Use describe_tables for their columns.",
        fn_schema=ListTablesInput,
    ),
    "describe_tables": ToolMetadata(
        name="describe_tables",
        description="Describe the columns and foreign keys of tables in the database.",
        fn_schema=DescribeTablesInput,
    ),
}


class VerictoToolSpec(BaseToolSpec):
    """Vericto (database guardrails for AI agents) as LlamaIndex agent tools.

    Vericto parses each SQL statement into an AST and checks it against
    deterministic rules (for example `VERICTO-001`, DELETE without WHERE) before
    anything runs. `to_tool_list()` returns:

    * `check_sql`: the verdict for a statement, as JSON, without running it.
    * With `sql_database` (a `VerictoSQLDatabase`), also `run_sql`,
      `list_tables` and `describe_tables`. `run_sql` goes through the guarded
      database: a blocked statement is not executed and the tool output names
      the rule and the suggested fix.

    Pick a mode:

    * Offline, no account: install the Vericto CLI 2.1.0 or later and pass
      `offline=True` (or set `VERICTO_OFFLINE=1`). The CLI's local engine checks
      the standard rules; nothing leaves the machine.
    * Online, your workspace's rules: set `VERICTO_API_KEY` (scope
      `proxy:evaluate`) and `VERICTO_DATABASE_ID`.

    Args:
        sql_database: a `VerictoSQLDatabase` to expose as guarded tools. Its guard
            and dialect are shared, so the connection arguments below must not be
            given with it.
        dialect: default dialect of `check_sql` (`postgres`, `mysql`, `oracle`,
            `mssql`, `snowflake`, `sqlite`); the model may pass another one per
            call. Defaults to the database's dialect, else `postgres`.
        offline: `True` for the local engine; `None` (default) reads
            `VERICTO_OFFLINE`; online otherwise.
        api_key: Vericto API key; defaults to `VERICTO_API_KEY`.
        database_id: the database registered in your workspace; defaults to
            `VERICTO_DATABASE_ID`.
        api_url: Vericto API URL; defaults to `VERICTO_API_URL`, then the public API.
        fail_mode: when Vericto cannot answer: `"closed"` (default) raises
            `vericto.VerictoUnavailable`; `"open"` returns an `UNEVALUATED`
            verdict (`allowed: false`). `None` reads `VERICTO_FAIL_MODE`.
        timeout: seconds per evaluation (SDK defaults: 5 s online, 30 s offline).
        offline_cli_path: the `vericto` binary; defaults to `VERICTO_CLI`, then PATH.
        guard: an existing `vericto.Vericto` to share instead of building one.

    Example:
        ```python
        from llama_index.tools.vericto import VerictoToolSpec

        tools = VerictoToolSpec(offline=True).to_tool_list()
        ```
    """

    spec_functions: list[SPEC_FUNCTION_TYPE] = [("check_sql", "acheck_sql")]

    def __init__(
        self,
        sql_database: VerictoSQLDatabase | None = None,
        *,
        dialect: str | None = None,
        offline: bool | None = None,
        api_key: str | None = None,
        database_id: str | None = None,
        api_url: str | None = None,
        fail_mode: FailMode | None = "closed",
        timeout: float | None = None,
        offline_cli_path: str | None = None,
        guard: Vericto | None = None,
    ) -> None:
        """Validate the arguments; the guard is built on first use."""
        given = {
            "offline": offline,
            "api_key": api_key,
            "database_id": database_id,
            "api_url": api_url,
            "timeout": timeout,
            "offline_cli_path": offline_cli_path,
            "guard": guard,
        }
        if sql_database is not None:
            if not isinstance(sql_database, VerictoSQLDatabase):
                msg = (
                    "sql_database must be a llama_index.tools.vericto.VerictoSQLDatabase: "
                    "a plain SQLDatabase would run statements Vericto never checked"
                )
                raise TypeError(msg)
            clashing = [name for name in _CONNECTION_ARGS if given[name] is not None]
            if clashing:
                msg = (
                    f"{', '.join(clashing)}: pass the Vericto connection arguments to "
                    "VerictoSQLDatabase; the tool spec shares its guard"
                )
                raise ValueError(msg)
            guard = sql_database.vericto_guard
            dialect = dialect or sql_database.vericto_dialect
            self.spec_functions = [
                ("check_sql", "acheck_sql"),
                ("run_sql", "arun_sql"),
                "list_tables",
                "describe_tables",
            ]
        self._sql_database = sql_database
        self._dialect = normalize_dialect(dialect or "postgres")
        self._shared_guard = guard
        self._offline = offline
        self._api_key = api_key
        self._database_id = database_id
        self._api_url = api_url
        self._fail_mode: FailMode | None = fail_mode
        self._timeout = timeout
        self._offline_cli_path = offline_cli_path
        self._guard: Vericto | None = None
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        """Never shows the API key."""
        tools = "check+database" if self._sql_database is not None else "check"
        return f"VerictoToolSpec(tools={tools!r}, dialect={self._dialect!r})"

    @property
    def dialect(self) -> str:
        """The dialect `check_sql` uses when the model does not pass one."""
        return self._dialect

    @property
    def sql_database(self) -> VerictoSQLDatabase | None:
        """The guarded database behind `run_sql`, if any."""
        return self._sql_database

    def to_tool_list(
        self,
        spec_functions: list[SPEC_FUNCTION_TYPE] | None = None,
        func_to_metadata_mapping: dict[str, ToolMetadata] | None = None,
    ) -> list[FunctionTool]:
        """The tools, with Vericto's descriptions and input schemas (overridable)."""
        mapping = {**_TOOL_METADATA, **(func_to_metadata_mapping or {})}
        return super().to_tool_list(spec_functions, mapping)

    def get_guard(self) -> Vericto:
        """The `vericto.Vericto` guard, built on first use (thread-safe)."""
        if self._shared_guard is not None:
            return self._shared_guard
        with self._lock:
            if self._guard is None:
                self._guard = build_guard(
                    offline=self._offline,
                    api_key=self._api_key,
                    database_id=self._database_id,
                    api_url=self._api_url,
                    fail_mode=self._fail_mode,
                    timeout=self._timeout,
                    offline_cli_path=self._offline_cli_path,
                )
            return self._guard

    def check(self, query: str, dialect: str | None = None) -> Verdict:
        """The `vericto.Verdict` for `query`. Nothing is executed.

        Raises:
            vericto.VerictoUnavailable: Vericto could not answer and
                `fail_mode="closed"`.
            vericto.VerictoConfigError: misconfiguration (no API key, no `vericto`
                CLI in offline mode, unsupported dialect, ...), in both fail modes.
        """
        return self.get_guard().check(query, normalize_dialect(dialect or self._dialect))

    def close(self) -> None:
        """Close the guard this tool spec built (its HTTP pool or `vericto serve` process).

        A guard passed with `guard=`, or shared from `sql_database`, is left to its
        owner.
        """
        with self._lock:
            if self._guard is not None:
                self._guard.close()
            self._guard = None

    # The tools. The model reads `_TOOL_METADATA`, not these docstrings.

    def check_sql(self, query: str, dialect: str | None = None) -> str:
        """Vericto's verdict for `query` as JSON (see `VerdictDict`). Nothing is executed."""
        return json.dumps(verdict_to_dict(self.check(query, dialect)), ensure_ascii=False)

    async def acheck_sql(self, query: str, dialect: str | None = None) -> str:
        """Async `check_sql`."""
        # The SDK is synchronous (an HTTP pool online, a pipe to `vericto serve`
        # offline, both thread-safe): run it in a worker thread so the event loop
        # is never blocked.
        return await asyncio.to_thread(self.check_sql, query, dialect)

    def _database(self) -> VerictoSQLDatabase:
        if self._sql_database is None:
            msg = "this VerictoToolSpec has no sql_database"
            raise RuntimeError(msg)
        return self._sql_database

    def run_sql(self, query: str) -> str:
        """Run `query` through the guarded database; a block returns the explanation.

        With the database's `on_block="raise"`, a block raises
        `vericto.VerictoBlocked` instead (a LlamaIndex agent reports it to the
        model as a tool error). Either way the statement does not run.
        """
        text, _metadata = self._database().run_sql(query)
        return text

    async def arun_sql(self, query: str) -> str:
        """Async `run_sql`, in a worker thread (the SDK and SQLAlchemy calls are sync)."""
        return await asyncio.to_thread(self.run_sql, query)

    def list_tables(self) -> list[str]:
        """The tables of the database the agent may query."""
        return list(self._database().get_usable_table_names())

    def describe_tables(self, tables: list[str] | None = None) -> str:
        """Columns and foreign keys of `tables` (default: every usable table).

        Raises:
            ValueError: a table that is not usable in this database.
        """
        db = self._database()
        usable = list(db.get_usable_table_names())
        names = tables or usable
        unknown = [name for name in names if name not in usable]
        if unknown:
            msg = f"unknown tables: {', '.join(unknown)}; available: {', '.join(usable)}"
            raise ValueError(msg)
        return "\n".join(db.get_single_table_info(name) for name in names)
