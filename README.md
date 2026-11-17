# llama-index-tools-vericto

[![PyPI](https://img.shields.io/pypi/v/llama-index-tools-vericto?label=PyPI)](https://pypi.org/project/llama-index-tools-vericto/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

The LlamaIndex integration for [Vericto](https://vericto.com), database
guardrails for AI agents. Vericto parses each SQL statement into an AST and
checks it against deterministic rules before it runs: `DELETE` or `UPDATE`
without `WHERE`, `DROP TABLE`, unbounded `SELECT`, and more. No LLM is involved
in the decision; the same SQL always gets the same verdict.

This package gives a LlamaIndex application two things:

- **`VerictoToolSpec`**: agent tools. `check_sql` checks a statement and returns
  a structured verdict (allowed or blocked, rule codes, messages, suggested fix)
  without running it. Given a `VerictoSQLDatabase`, the spec also provides
  `run_sql`, `list_tables` and `describe_tables`, and `run_sql` refuses blocked
  statements with a message the agent can act on. Sync and async.
- **`VerictoSQLDatabase`**: a drop-in `SQLDatabase` (for `NLSQLTableQueryEngine`,
  `SQLTableRetrieverQueryEngine`, `NLSQLRetriever` and any `run_sql` caller) that
  checks every statement before it reaches the database. Fail-closed by default.

Two ways to evaluate, same API:

| | Offline | Online |
|---|---|---|
| Account, network | none; the SQL never leaves the machine | a Vericto workspace; the SQL goes to the Vericto Runtime API |
| Needs | the Vericto CLI 2.1.0 or later installed | `VERICTO_API_KEY` (scope `proxy:evaluate`) and `VERICTO_DATABASE_ID` |
| Rules | the standard rules of the engine in the CLI, at their default severities | your workspace's rules: overrides, custom rules |
| Sensitive-column masking, agent allowlists, business policies, audit trail | no | yes |
| Metered | no | counts against the workspace's monthly query quota |

## Installation

```bash
pip install -U llama-index-tools-vericto
```

Python 3.11 or later, `llama-index-core` 0.13 or later.

## Quickstart: offline, no account

Install the Vericto CLI (it carries the engine; nothing is downloaded at run
time):

```bash
npm i -g @vericto/vericto-cli        # or: brew install vericto/tap/vericto
vericto --version                    # 2.1.0 or later
```

Check a statement:

```python
import json

from llama_index.tools.vericto import VerictoToolSpec

spec = VerictoToolSpec(offline=True, dialect="postgres")

verdict = json.loads(spec.check_sql("DELETE FROM users"))
verdict["decision"]  # 'BLOCKED'
verdict["rule_codes"]  # ['VERICTO-001']
verdict["suggested_fix"]  # 'DELETE FROM users WHERE id = $1'

json.loads(spec.check_sql("SELECT id FROM users WHERE id = 42 LIMIT 1"))["decision"]
# 'ALLOWED'

tools = spec.to_tool_list()  # [check_sql], for any LlamaIndex agent
```

Guard a database (here SQLite; any SQLAlchemy URL works):

```python
from llama_index.tools.vericto import VerictoSQLDatabase

db = VerictoSQLDatabase.from_uri("sqlite:///shop.db", offline=True)

db.run_sql("SELECT id, total FROM orders WHERE id = 1 LIMIT 10")[0]  # runs
db.run_sql("DELETE FROM orders")[0]
# Error: Vericto blocked this query (VERICTO-001, severity critical). It was NOT executed.
# Suggested fix: DELETE FROM orders WHERE id = $1
# Rewrite the query following the suggested fix and try again.
```

The dialect comes from the engine (`sqlite` here). `examples/quickstart.py` runs
all of this end to end.

## Quickstart: online, your workspace's rules

Create an API key with the `proxy:evaluate` scope in the Vericto dashboard and
register the database you are protecting. Then:

```bash
export VERICTO_API_KEY="vtro_..."
export VERICTO_DATABASE_ID="..."     # the registered database's id
```

```python
from llama_index.tools.vericto import VerictoSQLDatabase, VerictoToolSpec

spec = VerictoToolSpec(dialect="postgres")
db = VerictoSQLDatabase.from_uri("postgresql+psycopg://...")
```

The verdicts now follow your workspace's rules, sensitive columns come back
masked (`rewritten_query`, and the database runs the rewrite), and every
evaluation has an `event_id` in the audit trail.

Offline mode is never chosen on its own: with no `offline=True`, no
`VERICTO_OFFLINE=1` and no API key, the first check raises
`vericto.VerictoConfigError`. Offline mode combined with an API key raises too
("choose one"), so a missing secret can never quietly fall back to fewer rules.

## Use it in an agent

```python
# pip install llama-index-tools-vericto llama-index-llms-anthropic
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.anthropic import Anthropic

from llama_index.tools.vericto import VerictoSQLDatabase, VerictoToolSpec

db = VerictoSQLDatabase.from_uri("sqlite:///shop.db", offline=True)

agent = FunctionAgent(
    tools=VerictoToolSpec(db).to_tool_list(),  # check_sql, run_sql, list_tables, describe_tables
    llm=Anthropic(model="claude-sonnet-4-6"),  # any function-calling LLM
    system_prompt=(
        "You answer questions about the shop database. Check every query with "
        "check_sql before running it, and never run a blocked query."
    ),
)
response = await agent.run("Delete all orders.")
```

Every statement `run_sql` sends goes through Vericto, whether or not the model
calls `check_sql` first: the check tool lets it ask before it tries, the database
refuses what is blocked either way.

## Use it in a text-to-SQL query engine

```python
from llama_index.core.query_engine import NLSQLTableQueryEngine

db = VerictoSQLDatabase.from_uri("sqlite:///shop.db", offline=True, include_tables=["orders"])
query_engine = NLSQLTableQueryEngine(sql_database=db, tables=["orders"], llm=llm)
query_engine.query("Delete all orders")
```

When the generated SQL is blocked, nothing runs: the synthesis step reads
Vericto's explanation instead of a result, so the answer says why, and
`response.metadata["vericto_blocked"]` has the rule code, severity, suggested
fix and event id.

## The verdict

`check_sql` returns the verdict as a JSON string (the tool output's `content`
and `raw_output`). `spec.check(query)` returns the SDK's `vericto.Verdict`, and
`llama_index.tools.vericto.verdict_to_dict` turns it into the dict.

| Key | Meaning |
|---|---|
| `decision` | `ALLOWED`, `FLAGGED`, `MONITORED`, `PARSE_ERROR`, `BLOCKED`, or `UNEVALUATED` (no verdict, `fail_mode="open"`) |
| `allowed` | Vericto lets it run: `ALLOWED`, `FLAGGED`, `MONITORED`, `PARSE_ERROR`. Never for `BLOCKED` or `UNEVALUATED`. |
| `blocked`, `evaluated` | booleans |
| `rule_codes` | rules that matched, deciding rule first (`["VERICTO-001"]`) |
| `severity` | the deciding rule's severity |
| `messages` | readable reasons (server message, each finding and where it matched) |
| `suggested_fix` | a safer statement or advice, when Vericto has one |
| `findings` | `rule_code`, `severity`, `suggested_fix`, `location` (AST path) per rule |
| `rewritten_query` | the statement that runs instead, sensitive columns masked (online) |
| `dialect`, `mode`, `engine_version`, `ruleset_version`, `event_id` | provenance: `mode` is `offline` or `online`; `event_id` online only |
| `summary` | one paragraph for the model: what happened and what to do next |

A text with several statements gets one verdict, the strongest finding among
them: `SELECT 1; DELETE FROM orders` is `BLOCKED` by `VERICTO-001`.

## The tools

| Tool | Input | Output |
|---|---|---|
| `check_sql` | `query`, optional `dialect` | the verdict as JSON; nothing runs |
| `run_sql` (with a database) | `query` | the rows, or `Error: Vericto blocked this query ...` (nothing ran) |
| `list_tables` (with a database) | none | the usable table names |
| `describe_tables` (with a database) | optional `tables` | columns and foreign keys |

Each tool has a description and an input schema written for the model. Override
them with `spec.to_tool_list(func_to_metadata_mapping={"check_sql": ToolMetadata(...)})`.
Schema reflection (`list_tables`, `describe_tables`) is not sent to Vericto.

## Fail mode

When Vericto cannot answer (network, timeout, quota, the local engine process
failing):

- `fail_mode="closed"` (default): `vericto.VerictoUnavailable` is raised and
  nothing runs. Inside a LlamaIndex agent, the agent reports the exception to the
  model as a tool error.
- `fail_mode="open"`: `VerictoSQLDatabase` runs the statement unevaluated with a
  `vericto.VerictoFailOpenWarning`; `check_sql` returns an `UNEVALUATED` verdict
  with `allowed: false`.
- `fail_mode=None`: read `VERICTO_FAIL_MODE` (closed when unset).

Configuration errors (bad key, missing scope, no CLI in offline mode, an
unsupported dialect) raise `vericto.VerictoConfigError` in both modes.

## Configuration

`VerictoToolSpec` and `VerictoSQLDatabase` take the same connection arguments;
each falls back to an environment variable.

| Argument | Environment | Default |
|---|---|---|
| `offline` | `VERICTO_OFFLINE` | online |
| `api_key` | `VERICTO_API_KEY` | required online |
| `database_id` | `VERICTO_DATABASE_ID` | required online |
| `api_url` | `VERICTO_API_URL` | `https://api.vericto.com` |
| `fail_mode` | `VERICTO_FAIL_MODE` (only with `fail_mode=None`) | `"closed"` |
| `timeout` | `VERICTO_TIMEOUT` (online) | 5 s online, 30 s offline |
| `offline_cli_path` | `VERICTO_CLI` | `vericto` on `PATH` |
| `guard` | | a `vericto.Vericto` to share instead |

`VerictoToolSpec` also takes `dialect` (default: the database's, else
`postgres`; the model may pass another one per call) and `sql_database`. With
`sql_database`, the spec shares the database's guard, so the connection
arguments go to `VerictoSQLDatabase` only (passing them to both raises
`ValueError`), and a plain `SQLDatabase` is refused (`TypeError`): its
statements would not be checked.

`VerictoSQLDatabase` takes every `SQLDatabase` argument (`include_tables`,
`sample_rows_in_table_info`, ...), `dialect` (default: the engine's), `on_block`
(`"return"`, default, or `"raise"` to raise `vericto.VerictoBlocked`), and
`context` / `end_user` for business policies (see the
[Vericto SDK](https://github.com/vericto/vericto-python#readme)).

Call `close()` on either object when you are done: it stops the local
`vericto serve` process (offline) or closes the HTTP pool (online). A guard
passed with `guard=`, or shared from a database, is left to its owner.

## How it works, and its limits

The evaluation is done by the official Vericto SDK for Python
([`vericto`](https://pypi.org/project/vericto/), Apache-2.0), which this package
depends on; `VerictoSQLDatabase` is built on the SDK's `vericto.llamaindex`
integration.

- **Online**, the SDK sends the statement (never parameter values) to the
  Vericto Runtime API (`POST /api/v1/proxy/query`, header `X-API-Key`, scope
  `proxy:evaluate`) over HTTPS, with retries and backoff.
- **Offline**, the SDK starts the installed Vericto CLI once as
  `vericto serve --stdio` and sends it JSON Lines over a pipe. The engine runs
  in that separate process (it is AGPL-3.0-only and is never imported, linked or
  bundled by this package). No network listener, no request to anyone.

Limits, stated plainly:

- Offline mode needs the CLI installed and checks the standard rules only: no
  custom rules or severity overrides, no masking, no agent allowlists, no
  business policies, no audit trail. It answers "is this SQL obviously
  dangerous?", not "is this allowed by my organization's policy?".
- Vericto checks the statement, not the data: it does not know how many rows a
  `WHERE` matches, and it does not replace database permissions. Give the agent
  a database role with the least privilege it needs as well.
- A statement Vericto cannot parse is `PARSE_ERROR`: offline (and by default
  online) it is allowed to run and reported, per policy.
- Only what goes through `VerictoSQLDatabase.run_sql` (and `insert_into_table`)
  is checked. Code that uses the SQLAlchemy engine directly, such as
  `DatabaseToolSpec` from `llama-index-tools-database`, is not: use
  `VerictoToolSpec(db)` instead, or guard the engine itself with
  `vericto.sqlalchemy.instrument(engine)` from the SDK.
- The SDK is synchronous; the async tools run it in a worker thread.
  `NLSQLTableQueryEngine.aquery` calls `run_sql` from the event loop, so there
  each check blocks the loop for one round trip.
- Suggested fixes come from the engine and may use placeholders (`$1`) that you
  fill in; they are advice, not SQL to run blindly.

## Development

```bash
uv sync                                   # Python 3.11+, uv
make lint                                 # ruff check, ruff format --check, mypy
make test                                 # unit tests, no network
make integration_test                     # against the real engine (see below)
make build                                # sdist, wheel, twine check
```

Integration tests run offline against the real engine when a Vericto CLI is on
`PATH` or in `VERICTO_CLI` (`VERICTO_REQUIRE_CLI=1` makes a missing CLI a
failure instead of a skip), and online when `VERICTO_API_KEY` and
`VERICTO_DATABASE_ID` are set. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache License 2.0](LICENSE). See [NOTICE](NOTICE) and
[TRADEMARKS.md](TRADEMARKS.md). The Vericto engine and CLI are separate programs
under their own license (AGPL-3.0-only); this package talks to the CLI as a
separate process and does not include it.
