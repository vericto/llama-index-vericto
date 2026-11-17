# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from llama_index.core import SQLDatabase
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.llms import CompletionResponse, CompletionResponseGen, CustomLLM, LLMMetadata
from llama_index.core.query_engine import NLSQLTableQueryEngine
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from vericto import VerictoBlocked, VerictoConfigError, VerictoFailOpenWarning, VerictoUnavailable

from llama_index.tools.vericto import VerictoSQLDatabase, VerictoToolSpec
from tests.unit_tests.fakes import FakeEvaluator, fake_guard, masking


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_engine(f"sqlite:///{tmp_path / 'shop.db'}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, total INTEGER)"))
        conn.execute(text("INSERT INTO orders VALUES (1, 10), (2, 20)"))
        conn.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY, email TEXT)"))
        conn.execute(text("INSERT INTO customers VALUES (1, 'ana@example.com')"))
    yield eng
    eng.dispose()


def _count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM orders")).scalar_one())


def _db(engine: Engine, evaluator: FakeEvaluator, **kwargs: Any) -> VerictoSQLDatabase:
    fail_mode = kwargs.pop("fail_mode", "closed")
    return VerictoSQLDatabase(engine, guard=fake_guard(evaluator, fail_mode=fail_mode), **kwargs)


class ScriptedLLM(CustomLLM):
    """A completion model that answers the n-th prompt with the n-th scripted text."""

    responses: list[str]
    prompts: list[str] = []

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(model_name="scripted")

    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        self.prompts.append(prompt)
        return CompletionResponse(text=self.responses.pop(0))

    def stream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponseGen:
        raise NotImplementedError


# VerictoSQLDatabase


def test_is_a_llamaindex_sql_database_with_the_engine_dialect(engine: Engine) -> None:
    db = _db(engine, FakeEvaluator())
    assert isinstance(db, SQLDatabase)
    assert db.vericto_dialect == "sqlite"
    assert db.dialect == "sqlite"


def test_safe_select_runs_and_is_checked(engine: Engine) -> None:
    evaluator = FakeEvaluator()
    db = _db(engine, evaluator)
    evaluator.calls.clear()
    result, metadata = db.run_sql("SELECT id, total FROM orders WHERE id = 1 LIMIT 5")
    assert result == "[(1, 10)]"
    assert metadata["result"] == [(1, 10)]
    assert evaluator.calls == [("SELECT id, total FROM orders WHERE id = 1 LIMIT 5", "sqlite")]


def test_schema_reflection_is_not_sent_to_vericto(engine: Engine) -> None:
    evaluator = FakeEvaluator()
    db = _db(engine, evaluator)
    db.get_single_table_info("orders")
    assert evaluator.calls == []


def test_delete_without_where_is_refused_with_a_message(engine: Engine) -> None:
    db = _db(engine, FakeEvaluator())
    result, metadata = db.run_sql("DELETE FROM orders")
    assert result.startswith("Error: Vericto blocked this query (VERICTO-001, severity critical)")
    assert "It was NOT executed." in result
    assert "Suggested fix: DELETE FROM orders WHERE id = $1" in result
    assert metadata["vericto_blocked"]["rule_code"] == "VERICTO-001"
    assert metadata["result"] == []
    assert _count(engine) == 2


def test_on_block_raise(engine: Engine) -> None:
    db = _db(engine, FakeEvaluator(), on_block="raise")
    with pytest.raises(VerictoBlocked) as info:
        db.run_sql("DELETE FROM orders")
    assert info.value.verdict.rule_code == "VERICTO-001"
    assert _count(engine) == 2


def test_insert_into_table_is_checked(engine: Engine) -> None:
    def no_inserts(sql: str) -> dict[str, Any]:
        if sql.upper().startswith("INSERT"):
            return {"decision": "BLOCKED", "rule_code": "VERICTO-900", "severity": "high"}
        return {"decision": "ALLOWED"}

    db = _db(engine, FakeEvaluator(no_inserts), include_tables=["orders"])
    with pytest.raises(VerictoBlocked):
        db.insert_into_table("orders", {"id": 3, "total": 30})
    assert _count(engine) == 2


def test_masked_rewrite_runs_instead_of_the_original(engine: Engine) -> None:
    db = _db(engine, FakeEvaluator(masking))
    assert db.run_sql("SELECT id, email FROM customers LIMIT 10")[0] == "[(1, '***')]"


def test_fail_closed_raises_and_runs_nothing(engine: Engine) -> None:
    db = _db(engine, FakeEvaluator(unavailable=True))
    with pytest.raises(VerictoUnavailable):
        db.run_sql("DELETE FROM orders WHERE id = 1")
    assert _count(engine) == 2


def test_fail_open_runs_unevaluated_with_a_warning(engine: Engine) -> None:
    db = _db(engine, FakeEvaluator(unavailable=True), fail_mode="open")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        db.run_sql("DELETE FROM orders WHERE id = 1")
    assert any(issubclass(w.category, VerictoFailOpenWarning) for w in caught)
    assert _count(engine) == 1


def test_nl_sql_query_engine_never_runs_a_blocked_statement(engine: Engine) -> None:
    # The SDK guide's example: the model writes an unsafe DELETE, the synthesis
    # step reads Vericto's explanation instead of a result.
    llm = ScriptedLLM(
        responses=["SQLQuery: DELETE FROM orders\nSQLResult: ", "Vericto blocked that query."]
    )
    db = _db(engine, FakeEvaluator(), include_tables=["orders"])
    query_engine = NLSQLTableQueryEngine(
        sql_database=db, tables=["orders"], llm=llm, embed_model=MockEmbedding(embed_dim=8)
    )
    response = query_engine.query("Delete all orders")
    assert str(response) == "Vericto blocked that query."
    assert "Vericto blocked this query (VERICTO-001" in llm.prompts[-1]
    assert response.metadata is not None
    assert response.metadata["vericto_blocked"]["rule_code"] == "VERICTO-001"
    assert _count(engine) == 2


def test_from_uri_builds_the_guard_from_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evaluator = FakeEvaluator()
    seen: dict[str, Any] = {}

    def fake_build(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return fake_guard(evaluator)

    monkeypatch.setattr("llama_index.tools.vericto.sql_database.build_guard", fake_build)
    db = VerictoSQLDatabase.from_uri(f"sqlite:///{tmp_path / 'x.db'}", offline=True, timeout=3.0)
    assert seen["offline"] is True
    assert seen["fail_mode"] == "closed"
    assert seen["timeout"] == 3.0
    db.close()
    db.engine.dispose()
    assert evaluator.closed == 1


def test_close_leaves_a_shared_guard_open(engine: Engine) -> None:
    evaluator = FakeEvaluator()
    db = _db(engine, evaluator)
    db.close()
    assert evaluator.closed == 0
    # Detached: statements are no longer checked.
    evaluator.calls.clear()
    db.run_sql("SELECT 1")
    assert evaluator.calls == []


def test_guard_is_closed_when_construction_fails(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    evaluator = FakeEvaluator(dialects=("postgres",))
    monkeypatch.setattr(
        "llama_index.tools.vericto.sql_database.build_guard", lambda **_kw: fake_guard(evaluator)
    )
    with pytest.raises(VerictoConfigError):
        VerictoSQLDatabase(engine)  # sqlite is not supported by this evaluator
    assert evaluator.closed == 1


# VerictoToolSpec over a VerictoSQLDatabase


def _tools(spec: VerictoToolSpec) -> dict[str, Any]:
    return {t.metadata.get_name(): t for t in spec.to_tool_list()}


def test_spec_with_database_has_guarded_sql_tools(engine: Engine) -> None:
    evaluator = FakeEvaluator()
    db = _db(engine, evaluator)
    spec = VerictoToolSpec(db)
    assert spec.sql_database is db
    assert spec.get_guard() is db.vericto_guard
    assert spec.dialect == "sqlite"
    tools = _tools(spec)
    assert list(tools) == ["check_sql", "run_sql", "list_tables", "describe_tables"]
    verdict = json.loads(tools["check_sql"].call(query="DELETE FROM orders").content)
    assert verdict["dialect"] == "sqlite"
    assert verdict["rule_codes"] == ["VERICTO-001"]


def test_run_sql_tool_refuses_blocked_and_runs_safe(engine: Engine) -> None:
    spec = VerictoToolSpec(_db(engine, FakeEvaluator()))
    run_sql = _tools(spec)["run_sql"]
    blocked = run_sql.call(query="DELETE FROM orders")
    assert blocked.is_error is False
    assert blocked.content.startswith("Error: Vericto blocked this query (VERICTO-001")
    assert _count(engine) == 2
    assert run_sql.call(query="SELECT id, total FROM orders WHERE id = 2 LIMIT 1").content == (
        "[(2, 20)]"
    )
    run_sql.call(query="DELETE FROM orders WHERE id = 2")
    assert _count(engine) == 1


async def test_run_sql_tool_async(engine: Engine) -> None:
    spec = VerictoToolSpec(_db(engine, FakeEvaluator()))
    output = await _tools(spec)["run_sql"].acall(query="DELETE FROM orders")
    assert "Vericto blocked this query" in output.content
    assert (await spec.arun_sql("SELECT total FROM orders WHERE id = 1 LIMIT 1")) == "[(10,)]"


def test_run_sql_tool_raises_with_on_block_raise(engine: Engine) -> None:
    spec = VerictoToolSpec(_db(engine, FakeEvaluator(), on_block="raise"))
    with pytest.raises(VerictoBlocked):
        _tools(spec)["run_sql"].call(query="DELETE FROM orders")
    assert _count(engine) == 2


def test_list_and_describe_tables(engine: Engine) -> None:
    evaluator = FakeEvaluator()
    spec = VerictoToolSpec(_db(engine, evaluator, include_tables=["orders"]))
    evaluator.calls.clear()
    tools = _tools(spec)
    assert tools["list_tables"].call().raw_output == ["orders"]
    description = tools["describe_tables"].call().content
    assert description.startswith("Table 'orders' has columns: id (INTEGER), total (INTEGER)")
    assert tools["describe_tables"].call(tables=["orders"]).content == description
    with pytest.raises(ValueError, match="unknown tables: customers"):
        spec.describe_tables(["customers"])
    assert evaluator.calls == []


def test_spec_refuses_a_plain_sql_database(engine: Engine) -> None:
    with pytest.raises(TypeError, match="VerictoSQLDatabase"):
        VerictoToolSpec(SQLDatabase(engine))  # type: ignore[arg-type]


def test_spec_refuses_connection_arguments_with_a_database(engine: Engine) -> None:
    db = _db(engine, FakeEvaluator())
    with pytest.raises(ValueError, match="offline, api_key"):
        VerictoToolSpec(db, offline=True, api_key="vtro_secret")


def test_spec_close_leaves_the_database_guard_open(engine: Engine) -> None:
    evaluator = FakeEvaluator()
    spec = VerictoToolSpec(_db(engine, evaluator))
    spec.check_sql("SELECT 1")
    spec.close()
    assert evaluator.closed == 0
