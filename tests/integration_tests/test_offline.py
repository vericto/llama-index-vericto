# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""Offline mode against the real local engine of the Vericto CLI (`vericto serve`)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from vericto import VerictoBlocked

from llama_index.tools.vericto import VerictoSQLDatabase, VerictoToolSpec


@pytest.fixture
def spec(offline_env: str) -> Iterator[VerictoToolSpec]:
    tool_spec = VerictoToolSpec(offline=True, offline_cli_path=offline_env)
    yield tool_spec
    tool_spec.close()


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_engine(f"sqlite:///{tmp_path / 'shop.db'}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, total INTEGER)"))
        conn.execute(text("INSERT INTO orders VALUES (1, 10), (2, 20)"))
    yield eng
    eng.dispose()


def _count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM orders")).scalar_one())


def _check(spec: VerictoToolSpec, **kwargs: Any) -> dict[str, Any]:
    tool = next(t for t in spec.to_tool_list() if t.metadata.name == "check_sql")
    verdict: dict[str, Any] = json.loads(tool.call(**kwargs).content)
    return verdict


def test_safe_select_is_allowed(spec: VerictoToolSpec) -> None:
    verdict = _check(spec, query="SELECT id, total FROM orders WHERE id = 1 LIMIT 10")
    assert verdict["decision"] == "ALLOWED"
    assert verdict["allowed"] is True
    assert verdict["mode"] == "offline"
    assert verdict["engine_version"]
    assert verdict["ruleset_version"].startswith("standard@engine-")


@pytest.mark.parametrize("dialect", ["postgres", "mysql", "oracle", "mssql", "snowflake", "sqlite"])
def test_delete_without_where_is_blocked_with_vericto_001(
    spec: VerictoToolSpec, dialect: str
) -> None:
    verdict = _check(spec, query="DELETE FROM orders", dialect=dialect)
    assert verdict["decision"] == "BLOCKED"
    assert verdict["blocked"] is True
    assert verdict["rule_codes"][0] == "VERICTO-001"
    assert verdict["severity"] == "critical"
    assert verdict["suggested_fix"]
    assert verdict["dialect"] == dialect


def test_strongest_finding_of_several_statements(spec: VerictoToolSpec) -> None:
    verdict = _check(spec, query="SELECT 1; DELETE FROM orders")
    assert verdict["rule_codes"][0] == "VERICTO-001"


async def test_async_and_sync_agree(spec: VerictoToolSpec) -> None:
    sync = json.loads(spec.check_sql("UPDATE orders SET total = 0"))
    # Concurrent calls share one `vericto serve` process.
    results = await asyncio.gather(
        *(spec.acheck_sql("UPDATE orders SET total = 0") for _ in range(5))
    )
    assert all(json.loads(r)["rule_codes"] == sync["rule_codes"] for r in results)
    assert sync["blocked"] is True


def test_sql_database_refuses_delete_without_where(offline_env: str, engine: Engine) -> None:
    db = VerictoSQLDatabase(engine, offline=True, offline_cli_path=offline_env)
    try:
        assert db.vericto_dialect == "sqlite"
        assert db.run_sql("SELECT id, total FROM orders WHERE id = 1 LIMIT 5")[0] == "[(1, 10)]"
        result, metadata = db.run_sql("DELETE FROM orders")
        assert result.startswith("Error: Vericto blocked this query (VERICTO-001")
        assert metadata["vericto_blocked"]["rule_code"] == "VERICTO-001"
        assert _count(engine) == 2
        # A safe, targeted DELETE goes through.
        db.run_sql("DELETE FROM orders WHERE id = 2")
        assert _count(engine) == 1
    finally:
        db.close()


def test_sql_database_on_block_raise(offline_env: str, engine: Engine) -> None:
    db = VerictoSQLDatabase(engine, offline=True, offline_cli_path=offline_env, on_block="raise")
    try:
        with pytest.raises(VerictoBlocked) as info:
            db.run_sql("DROP TABLE orders")
        assert info.value.verdict.blocked
        assert info.value.verdict.mode == "offline"
        assert _count(engine) == 2
    finally:
        db.close()


def test_tool_spec_over_the_database(offline_env: str, engine: Engine) -> None:
    db = VerictoSQLDatabase(engine, offline=True, offline_cli_path=offline_env)
    try:
        tools = {t.metadata.name: t for t in VerictoToolSpec(db).to_tool_list()}
        assert json.loads(tools["check_sql"].call(query="DELETE FROM orders").content)["blocked"]
        refused = tools["run_sql"].call(query="UPDATE orders SET total = 0")
        assert "Vericto blocked this query" in refused.content
        assert _count(engine) == 2
        assert tools["list_tables"].call().raw_output == ["orders"]
    finally:
        db.close()
