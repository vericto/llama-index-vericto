# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""Online mode against the Vericto Runtime API (your workspace's rules).

Opt in with `VERICTO_API_KEY` (scope `proxy:evaluate`) and `VERICTO_DATABASE_ID`.
Each test is one or two evaluations against the workspace's monthly quota. The
assertions assume VERICTO-001 is enabled and blocking, as in a new workspace.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator

import pytest

from llama_index.tools.vericto import VerictoToolSpec

pytestmark = pytest.mark.skipif(
    not (os.environ.get("VERICTO_API_KEY") and os.environ.get("VERICTO_DATABASE_ID")),
    reason="online tests need VERICTO_API_KEY and VERICTO_DATABASE_ID",
)


@pytest.fixture
def spec(monkeypatch: pytest.MonkeyPatch) -> Iterator[VerictoToolSpec]:
    monkeypatch.delenv("VERICTO_OFFLINE", raising=False)
    tool_spec = VerictoToolSpec(dialect="postgres")
    yield tool_spec
    tool_spec.close()


def test_delete_without_where_is_blocked(spec: VerictoToolSpec) -> None:
    verdict = json.loads(spec.check_sql("DELETE FROM orders"))
    assert verdict["mode"] == "online"
    assert verdict["blocked"] is True
    assert "VERICTO-001" in verdict["rule_codes"]
    assert verdict["event_id"]


async def test_safe_select_is_not_blocked(spec: VerictoToolSpec) -> None:
    verdict = json.loads(await spec.acheck_sql("SELECT id FROM orders WHERE id = 1 LIMIT 10"))
    assert verdict["mode"] == "online"
    assert verdict["blocked"] is False
