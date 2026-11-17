# Changelog

All notable changes to this package are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-16

First release.

### Added

- `VerictoToolSpec`, a LlamaIndex `BaseToolSpec` (import path
  `llama_index.tools.vericto`). `to_tool_list()` returns `check_sql` (sync and
  async), which checks a SQL statement with Vericto without running it and
  returns the verdict as JSON: `decision`, `allowed`, `blocked`, `rule_codes`,
  `messages`, `suggested_fix`, `findings`, `rewritten_query`, provenance (`mode`,
  `engine_version`, `ruleset_version`, `event_id`) and a `summary` for the model.
  Each tool has a description and a pydantic input schema written for the model;
  `func_to_metadata_mapping` overrides them.
- `VerictoToolSpec(sql_database)`: with a `VerictoSQLDatabase`, also `run_sql`
  (sync and async), `list_tables` and `describe_tables`. `run_sql` goes through
  the guarded database, so a blocked statement is not executed and the tool
  output names the rule and the suggested fix. The spec shares the database's
  guard and dialect, refuses a plain `SQLDatabase` (`TypeError`) and refuses
  connection arguments given to both (`ValueError`).
- `VerictoSQLDatabase`, a `llama_index.core.SQLDatabase` that checks every
  statement `run_sql` and `insert_into_table` send, in the engine's dialect, for
  `NLSQLTableQueryEngine`, `SQLTableRetrieverQueryEngine`, `NLSQLRetriever` and
  the tool spec. A block returns the explanation as the SQL result with
  `metadata["vericto_blocked"]` (`on_block="return"`, default) or raises
  `vericto.VerictoBlocked` (`"raise"`). Built on the Vericto SDK's
  `vericto.llamaindex` integration, with the connection arguments below and
  `close()`.
- Offline mode (`offline=True` or `VERICTO_OFFLINE=1`): the standard rules of the
  local engine in the Vericto CLI 2.1.0+, no account, no network. Online mode
  (`VERICTO_API_KEY`, `VERICTO_DATABASE_ID`): your workspace's rules through the
  Vericto Runtime API.
- `fail_mode="closed"` by default; `"open"` and `None` (`VERICTO_FAIL_MODE`) are
  opt-in.
- `[tool.llamahub]` metadata (`import_path`, `class_authors`) in `pyproject.toml`,
  as in the LlamaIndex monorepo's integration packages.
