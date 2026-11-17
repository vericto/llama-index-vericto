# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""The README's agent, with a scripted function-calling model instead of an LLM."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from llama_index.core.agent.workflow import FunctionAgent, ToolCallResult
from llama_index.core.base.llms.types import ChatMessage, MessageRole, ToolCallBlock
from llama_index.core.llms.mock import MockFunctionCallingLLM
from llama_index.core.tools import BaseTool
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from llama_index.tools.vericto import VerictoSQLDatabase, VerictoToolSpec
from tests.unit_tests.fakes import FakeEvaluator, fake_guard


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


def _call(name: str, **kwargs: Any) -> ChatMessage:
    return ChatMessage(
        role=MessageRole.ASSISTANT,
        blocks=[ToolCallBlock(tool_call_id=f"call-{name}", tool_name=name, tool_kwargs=kwargs)],
    )


def _agent_tools(db: VerictoSQLDatabase) -> list[BaseTool | Callable[..., Any]]:
    return [*VerictoToolSpec(db).to_tool_list()]


class Script:
    """Answers the n-th model turn with the n-th scripted message."""

    def __init__(self, turns: list[ChatMessage]) -> None:
        self.turns = turns
        self.seen: list[Sequence[ChatMessage]] = []

    def __call__(self, messages: Sequence[ChatMessage], **_kwargs: Any) -> ChatMessage:
        self.seen.append(list(messages))
        return self.turns.pop(0)


async def test_agent_checks_then_is_refused_then_runs_the_fix(engine: Engine) -> None:
    db = VerictoSQLDatabase(engine, guard=fake_guard(FakeEvaluator()))
    script = Script(
        [
            _call("check_sql", query="DELETE FROM orders"),
            # The model ignores the verdict and tries anyway: the database refuses.
            _call("run_sql", query="DELETE FROM orders"),
            _call("run_sql", query="DELETE FROM orders WHERE id = 2"),
            ChatMessage(role=MessageRole.ASSISTANT, content="Deleted order 2 only."),
        ]
    )
    agent = FunctionAgent(
        tools=_agent_tools(db),
        llm=MockFunctionCallingLLM(response_generator=script, is_chat_model=True),
        system_prompt="Check every query with check_sql before running it.",
    )

    handler = agent.run(user_msg="Delete all orders.")
    results = [ev async for ev in handler.stream_events() if isinstance(ev, ToolCallResult)]
    response = await handler

    assert str(response) == "Deleted order 2 only."
    assert [r.tool_name for r in results] == ["check_sql", "run_sql", "run_sql"]
    check, refused, fixed = (r.tool_output for r in results)
    assert '"blocked": true' in check.content
    assert '"VERICTO-001"' in check.content
    assert refused.is_error is False
    assert refused.content.startswith("Error: Vericto blocked this query (VERICTO-001")
    assert fixed.is_error is False
    # Only the targeted DELETE ran.
    assert _count(engine) == 1
    # The model saw the refusal before writing the fix.
    tool_messages = [m for m in script.seen[2] if m.role == MessageRole.TOOL]
    assert "Vericto blocked this query" in str(tool_messages[-1].content)


async def test_agent_sees_fail_closed_as_a_tool_error_and_nothing_runs(engine: Engine) -> None:
    db = VerictoSQLDatabase(engine, guard=fake_guard(FakeEvaluator(unavailable=True)))
    script = Script(
        [
            _call("run_sql", query="DELETE FROM orders WHERE id = 1"),
            ChatMessage(role=MessageRole.ASSISTANT, content="Vericto is unavailable."),
        ]
    )
    agent = FunctionAgent(
        tools=_agent_tools(db),
        llm=MockFunctionCallingLLM(response_generator=script, is_chat_model=True),
    )
    handler = agent.run(user_msg="Delete order 1.")
    results = [ev async for ev in handler.stream_events() if isinstance(ev, ToolCallResult)]
    await handler
    assert results[0].tool_output.is_error is True
    assert _count(engine) == 2
