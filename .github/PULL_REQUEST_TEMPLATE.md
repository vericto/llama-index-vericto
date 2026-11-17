## What does this PR change?

<!-- A clear, concise description of the change. -->

## Why?

<!-- Context: a LlamaIndex incompatibility, a statement that ran without being checked, a verdict field an agent needs. A wrong verdict for a statement belongs in vericto-engine; transport and offline-process issues in vericto-python. -->

## Type of change

- [ ] `VerictoToolSpec` (tools, verdict format)
- [ ] `VerictoSQLDatabase`
- [ ] Bug fix
- [ ] Documentation or examples
- [ ] Dependencies or CI

## Tests

- [ ] Added or updated tests that cover the change, including the failure path
- [ ] `make lint` passes (ruff check, ruff format --check, mypy)
- [ ] `make test` passes
- [ ] `VERICTO_REQUIRE_CLI=1 make integration_test` passes
- [ ] `make build` succeeds (twine check)

## Checklist

- [ ] Commits follow Conventional Commits
- [ ] `CHANGELOG.md` updated under `[Unreleased]` (if a user of the package can see the change)
- [ ] New or changed arguments, environment variables or errors documented in `README.md`
- [ ] A blocked statement still never runs; block messages carry no row data
- [ ] CI is green
