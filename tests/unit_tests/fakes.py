# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""A stand-in for the Vericto engine: canned Runtime API / offline responses."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from vericto import Vericto, VerictoUnavailable
from vericto.verdict import Verdict

Body = Mapping[str, Any]

ALLOWED: Body = {"decision": "ALLOWED", "mode": "offline", "engine_version": "5.0.0"}
DELETE_WITHOUT_WHERE: Body = {
    "decision": "BLOCKED",
    "rule_code": "VERICTO-001",
    "severity": "critical",
    "ast_node_path": "DeleteStmt > WhereClause = NULL",
    "suggested_safe_query": "DELETE FROM orders WHERE id = $1",
    "mode": "offline",
    "engine_version": "5.0.0",
    "ruleset_version": "standard@engine-5.0.0",
}
SELECT_WITHOUT_LIMIT: Body = {
    "decision": "FLAGGED",
    "rule_code": "VERICTO-050",
    "severity": "medium",
    "ast_node_path": "SelectStmt > LimitCount = NULL",
    "suggested_safe_query": "SELECT ... WHERE <condition> LIMIT 1000",
    "mode": "offline",
    "engine_version": "5.0.0",
}


def standard_rules(sql: str) -> Body:
    """A tiny imitation of the standard rules: enough for the unit tests."""
    text = sql.strip().upper()
    if text.startswith("DELETE") and " WHERE " not in f" {text} ":
        return DELETE_WITHOUT_WHERE
    if text.startswith("SELECT") and " FROM " in text and " LIMIT " not in f"{text} ":
        return SELECT_WITHOUT_LIMIT
    return ALLOWED


class FakeEvaluator:
    """Implements `vericto.Evaluator`; records every statement it is asked about."""

    mode = "offline"

    def __init__(
        self,
        respond: Callable[[str], Body] = standard_rules,
        *,
        unavailable: bool = False,
        dialects: Sequence[str] = ("postgres", "mysql", "oracle", "mssql", "snowflake", "sqlite"),
    ) -> None:
        self.respond = respond
        self.unavailable = unavailable
        self.dialects = tuple(dialects)
        self.calls: list[tuple[str, str]] = []
        self.closed = 0

    def evaluate(self, sql: str, dialect: str) -> Verdict:
        self.calls.append((sql, dialect))
        if self.unavailable:
            msg = "the local Vericto engine did not answer"
            raise VerictoUnavailable(msg)
        return Verdict.from_response(dict(self.respond(sql)), sql, dialect)

    def supported_dialects(self) -> Sequence[str]:
        return self.dialects

    def close(self) -> None:
        self.closed += 1


def fake_guard(evaluator: FakeEvaluator | None = None, **kwargs: Any) -> Vericto:
    return Vericto(evaluator=evaluator or FakeEvaluator(), **kwargs)


def masking(sql: str) -> Body:
    """Online-style answer that masks the `email` column."""
    if re.search(r"\bemail\b", sql, re.IGNORECASE):
        return {
            "decision": "ALLOWED",
            "mode": "online",
            "rewritten_query": "SELECT id, '***' AS email FROM customers LIMIT 10",
            "event_id": "evt_123",
        }
    return standard_rules(sql)
