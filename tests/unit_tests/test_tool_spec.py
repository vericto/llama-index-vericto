# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from typing import Any

import pytest
from llama_index.core.bridge.pydantic import ValidationError
from llama_index.core.tools import FunctionTool, ToolMetadata
from llama_index.core.tools.tool_spec.base import BaseToolSpec
from vericto import VerictoConfigError, VerictoUnavailable

from llama_index.tools.vericto import VerictoToolSpec
from llama_index.tools.vericto.base import CheckSQLInput
from tests.unit_tests.fakes import FakeEvaluator, fake_guard, masking


def _spec(evaluator: FakeEvaluator | None = None, **kwargs: Any) -> VerictoToolSpec:
    fail_mode = kwargs.pop("fail_mode", "closed")
    return VerictoToolSpec(guard=fake_guard(evaluator, fail_mode=fail_mode), **kwargs)


def _tool(spec: VerictoToolSpec, name: str = "check_sql") -> FunctionTool:
    return next(t for t in spec.to_tool_list() if t.metadata.name == name)


def _verdict(spec: VerictoToolSpec, query: str, **kwargs: Any) -> dict[str, Any]:
    output = _tool(spec).call(query=query, **kwargs)
    assert output.is_error is False
    verdict: dict[str, Any] = json.loads(str(output.raw_output))
    assert json.loads(output.content) == verdict
    return verdict


def test_is_a_tool_spec_with_one_tool_without_a_database() -> None:
    spec = _spec()
    assert isinstance(spec, BaseToolSpec)
    tools = spec.to_tool_list()
    assert [t.metadata.name for t in tools] == ["check_sql"]
    assert isinstance(tools[0], FunctionTool)


def test_safe_select_is_allowed() -> None:
    evaluator = FakeEvaluator()
    verdict = _verdict(_spec(evaluator), "SELECT id FROM users WHERE id = 1 LIMIT 10")
    assert verdict["decision"] == "ALLOWED"
    assert verdict["allowed"] is True
    assert verdict["blocked"] is False
    assert verdict["rule_codes"] == []
    assert verdict["summary"].startswith("Vericto found no problem")
    assert evaluator.calls == [("SELECT id FROM users WHERE id = 1 LIMIT 10", "postgres")]


def test_delete_without_where_is_blocked_with_vericto_001() -> None:
    verdict = _verdict(_spec(), "DELETE FROM orders")
    assert verdict["decision"] == "BLOCKED"
    assert verdict["allowed"] is False
    assert verdict["blocked"] is True
    assert verdict["rule_codes"] == ["VERICTO-001"]
    assert verdict["severity"] == "critical"
    assert verdict["suggested_fix"] == "DELETE FROM orders WHERE id = $1"
    assert verdict["findings"] == [
        {
            "rule_code": "VERICTO-001",
            "severity": "critical",
            "suggested_fix": "DELETE FROM orders WHERE id = $1",
            "location": "DeleteStmt > WhereClause = NULL",
        }
    ]
    assert verdict["messages"] == [
        "VERICTO-001 (critical) matched at DeleteStmt > WhereClause = NULL."
    ]
    assert "NOT executed" in verdict["summary"]
    assert "Suggested fix: DELETE FROM orders WHERE id = $1" in verdict["summary"]
    assert verdict["mode"] == "offline"
    assert verdict["engine_version"] == "5.0.0"


def test_flagged_query_may_run_and_says_why() -> None:
    verdict = _verdict(_spec(), "SELECT * FROM users")
    assert verdict["decision"] == "FLAGGED"
    assert verdict["allowed"] is True
    assert verdict["rule_codes"] == ["VERICTO-050"]
    assert "VERICTO-050" in verdict["summary"]


def test_masked_rewrite_is_reported() -> None:
    verdict = _verdict(_spec(FakeEvaluator(masking)), "SELECT id, email FROM customers LIMIT 10")
    assert verdict["allowed"] is True
    assert verdict["rewritten_query"] == "SELECT id, '***' AS email FROM customers LIMIT 10"
    assert verdict["event_id"] == "evt_123"
    assert "masked" in verdict["summary"]


def test_server_message_and_parse_error_are_messages() -> None:
    body = {"decision": "PARSE_ERROR", "parse_error": "syntax error at SELEC", "error": "unparsed"}
    verdict = _verdict(_spec(FakeEvaluator(lambda _sql: body)), "SELEC 1")
    assert verdict["decision"] == "PARSE_ERROR"
    assert verdict["allowed"] is True
    assert verdict["messages"] == ["unparsed", "Parser: syntax error at SELEC"]


def test_unknown_decision_is_never_read_as_allowed() -> None:
    verdict = _verdict(_spec(FakeEvaluator(lambda _sql: {"decision": "MAYBE"})), "SELECT 1")
    assert verdict["blocked"] is True
    assert verdict["allowed"] is False


async def test_async_call_matches_sync() -> None:
    spec = _spec()
    output = await _tool(spec).acall(query="DELETE FROM orders")
    assert json.loads(output.content)["rule_codes"] == ["VERICTO-001"]
    assert json.loads(await spec.acheck_sql("SELECT 1"))["decision"] == "ALLOWED"


def test_dialect_argument_overrides_default_and_is_normalized() -> None:
    evaluator = FakeEvaluator()
    spec = _spec(evaluator, dialect="postgresql")
    assert spec.dialect == "postgres"
    _verdict(spec, "SELECT 1")
    _verdict(spec, "SELECT 1", dialect="sqlite")
    assert [d for _, d in evaluator.calls] == ["postgres", "sqlite"]


def test_tool_metadata_is_written_for_the_model() -> None:
    tool = _tool(_spec())
    assert tool.metadata.description.startswith("Check a SQL query with Vericto")
    assert "database guardrails for AI agents" in tool.metadata.description
    assert "Annotated" not in tool.metadata.description
    schema = tool.metadata.get_parameters_dict()
    assert schema["required"] == ["query"]
    assert schema["properties"]["query"]["description"]
    assert schema["properties"]["dialect"]["anyOf"][0]["enum"] == [
        "postgres",
        "mysql",
        "oracle",
        "mssql",
        "snowflake",
        "sqlite",
    ]


def test_input_schema_rejects_unknown_dialect_and_empty_query() -> None:
    with pytest.raises(ValidationError):
        CheckSQLInput(query="SELECT 1", dialect="db2")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        CheckSQLInput(query="")


def test_tool_metadata_can_be_overridden() -> None:
    custom = ToolMetadata(name="vericto_check", description="Ask Vericto first.")
    tools = _spec().to_tool_list(func_to_metadata_mapping={"check_sql": custom})
    assert tools[0].metadata.name == "vericto_check"
    assert tools[0].metadata.description == "Ask Vericto first."


def test_fail_closed_raises_when_vericto_cannot_answer() -> None:
    spec = _spec(FakeEvaluator(unavailable=True))
    with pytest.raises(VerictoUnavailable):
        spec.check_sql("SELECT 1")
    with pytest.raises(VerictoUnavailable):
        _tool(spec).call(query="SELECT 1")


def test_fail_open_returns_unevaluated_not_allowed() -> None:
    verdict = _verdict(_spec(FakeEvaluator(unavailable=True), fail_mode="open"), "SELECT 1")
    assert verdict["decision"] == "UNEVALUATED"
    assert verdict["evaluated"] is False
    assert verdict["allowed"] is False
    assert "could not evaluate" in verdict["summary"]


def test_unsupported_dialect_is_a_config_error() -> None:
    spec = _spec(FakeEvaluator(dialects=("postgres",)))
    with pytest.raises(VerictoConfigError):
        spec.check("SELECT 1", "mysql")


def test_guard_is_built_lazily_and_closed_by_the_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[dict[str, Any]] = []
    evaluator = FakeEvaluator()

    def fake_build(**kwargs: Any) -> Any:
        built.append(kwargs)
        return fake_guard(evaluator)

    monkeypatch.setattr("llama_index.tools.vericto.base.build_guard", fake_build)
    spec = VerictoToolSpec(api_key="vtro_secret", database_id="db-1", timeout=2.0)
    assert built == []
    spec.check_sql("SELECT 1")
    spec.check_sql("SELECT 2")
    assert len(built) == 1
    assert built[0]["api_key"] == "vtro_secret"
    assert built[0]["database_id"] == "db-1"
    assert built[0]["fail_mode"] == "closed"
    assert built[0]["timeout"] == 2.0
    spec.close()
    assert evaluator.closed == 1
    spec.close()
    assert evaluator.closed == 1


def test_close_leaves_a_shared_guard_open() -> None:
    evaluator = FakeEvaluator()
    spec = VerictoToolSpec(guard=fake_guard(evaluator))
    spec.check_sql("SELECT 1")
    spec.close()
    assert evaluator.closed == 0


def test_api_key_is_not_in_repr() -> None:
    spec = VerictoToolSpec(api_key="vtro_secret")
    assert "vtro_secret" not in repr(spec)
    assert "vtro_secret" not in str(spec)


def test_offline_with_api_key_is_refused() -> None:
    spec = VerictoToolSpec(offline=True, api_key="vtro_secret")
    with pytest.raises(VerictoConfigError, match="choose one"):
        spec.check_sql("SELECT 1")


def test_no_mode_and_no_key_is_a_config_error() -> None:
    with pytest.raises(VerictoConfigError, match="API key"):
        VerictoToolSpec().check_sql("SELECT 1")


def test_offline_without_cli_explains_how_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(VerictoConfigError, match="npm i -g @vericto/vericto-cli"):
        VerictoToolSpec(offline=True).check_sql("SELECT 1")


def test_database_tools_need_a_database() -> None:
    with pytest.raises(RuntimeError, match="no sql_database"):
        _spec().run_sql("SELECT 1")
