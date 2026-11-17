# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""LlamaIndex integration for Vericto, database guardrails for AI agents.

* `VerictoToolSpec`: agent tools. `check_sql` returns Vericto's verdict for a SQL
  statement without running it; with a `VerictoSQLDatabase`, `run_sql`,
  `list_tables` and `describe_tables` too, where blocked statements never run.
* `VerictoSQLDatabase`: a `SQLDatabase` (for `NLSQLTableQueryEngine` and the other
  text-to-SQL engines) that checks every statement before it runs and refuses
  blocked ones.
"""

from llama_index.tools.vericto._verdict import FindingDict, VerdictDict, verdict_to_dict
from llama_index.tools.vericto._version import __version__
from llama_index.tools.vericto.base import VerictoToolSpec
from llama_index.tools.vericto.sql_database import VerictoSQLDatabase

__all__ = [
    "FindingDict",
    "VerdictDict",
    "VerictoSQLDatabase",
    "VerictoToolSpec",
    "__version__",
    "verdict_to_dict",
]
