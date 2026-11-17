# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""Quickstart: the code of the README, end to end.

Offline (default): needs the Vericto CLI 2.1.0 or later on PATH (or `VERICTO_CLI`)
and `pip install llama-index-tools-vericto`. No account, nothing leaves the machine.

    python examples/quickstart.py

Online, with your workspace's rules (no CLI needed):

    VERICTO_API_KEY=vtro_... VERICTO_DATABASE_ID=... python examples/quickstart.py --online
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

from llama_index.tools.vericto import VerictoSQLDatabase, VerictoToolSpec


def main(*, online: bool) -> int:
    """Run the quickstart; return the process exit code."""
    offline = not online

    # 1. The check tool: a verdict, nothing runs.
    spec = VerictoToolSpec(offline=offline, dialect="postgres")
    try:
        check_sql = spec.to_tool_list()[0]
        safe = json.loads(
            check_sql.call(query="SELECT id, email FROM users WHERE id = 42 LIMIT 1").content
        )
        print("safe SELECT  ->", safe["decision"], safe["summary"])
        risky = json.loads(check_sql.call(query="DELETE FROM users").content)
        print(
            "DELETE       ->",
            risky["decision"],
            risky["rule_codes"],
            "fix:",
            risky["suggested_fix"],
        )
    finally:
        spec.close()

    # 2. The guarded database: blocked statements never reach it.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "shop.db"
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, total INTEGER)")
            conn.execute("INSERT INTO orders VALUES (1, 10), (2, 20)")
        conn.close()

        db = VerictoSQLDatabase.from_uri(f"sqlite:///{path}", offline=offline)
        try:
            tools = {t.metadata.name: t for t in VerictoToolSpec(db).to_tool_list()}
            print("tools        ->", list(tools))
            print("dialect      ->", db.vericto_dialect)
            run_sql = tools["run_sql"]
            print(
                "SELECT       ->",
                run_sql.call(query="SELECT id, total FROM orders WHERE id = 1 LIMIT 10").content,
            )
            print("DELETE       ->", run_sql.call(query="DELETE FROM orders").content)
            rows_left = db.run_sql("SELECT count(*) FROM orders LIMIT 1")[0]
            print("rows left    ->", rows_left)
        finally:
            db.close()
            db.engine.dispose()
    blocked = risky["blocked"] and "VERICTO-001" in risky["rule_codes"]
    return 0 if blocked and safe["allowed"] and rows_left == "[(2,)]" else 1


if __name__ == "__main__":
    sys.exit(main(online="--online" in sys.argv[1:]))
