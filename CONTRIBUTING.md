# Contributing to llama-index-tools-vericto

Thanks for your interest in improving the Vericto integration for LlamaIndex.
This repository holds the `llama-index-tools-vericto` package, open source under
the [Apache License 2.0](LICENSE).

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be
respectful, constructive, and technically precise.

## What belongs here

- `VerictoToolSpec` (`llama_index/tools/vericto/base.py`), its tools and the
  verdict format (`_verdict.py`).
- `VerictoSQLDatabase` (`sql_database.py`), its arguments and its LlamaIndex
  compatibility (`NLSQLTableQueryEngine`, retrievers, agents).
- Tests, examples and this repository's documentation.

Contributions that belong elsewhere:

- A statement that got the wrong verdict, a new rule, SQL parsing →
  [vericto-engine](https://github.com/vericto/vericto-engine).
- The Runtime API client, offline mode (`vericto serve --stdio`), retries, the
  checks inside `SQLDatabase` (`vericto.llamaindex`) → the Python SDK,
  [vericto-python](https://github.com/vericto/vericto-python).
- The `vericto` command line tool → [vericto-cli](https://github.com/vericto/vericto-cli).

## Getting started

```bash
git clone https://github.com/<you>/llama-index-vericto.git
cd llama-index-vericto
uv sync                  # Python 3.11+; uv.lock pins every tool
make test
```

CI uses uv 0.10.8. Unit tests use a stand-in for the engine
(`tests/unit_tests/fakes.py`) and run with sockets disabled; nothing connects to
Vericto.

Integration tests run against the real engine:

```bash
# Offline: a Vericto CLI 2.1.0+ on PATH, or VERICTO_CLI=/path/to/vericto
VERICTO_REQUIRE_CLI=1 make integration_test
# Online (optional): spends evaluations from your workspace's quota
VERICTO_API_KEY=vtro_... VERICTO_DATABASE_ID=... make integration_test
```

## Development workflow

1. Fork the repo and create a branch: `feat/...` or `fix/...`.
2. Make your change with tests, including the failure path (`fail_mode`,
   unavailable engine, configuration errors).
3. Run what CI runs:
   ```bash
   uv sync --locked
   make lint
   make test
   VERICTO_REQUIRE_CLI=1 make integration_test
   make build
   ```
4. Open a PR using the template. Keep PRs focused.

## Commit convention

We use [Conventional Commits](https://www.conventionalcommits.org/)
(`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore(deps):`, `release:`).

**Write in English**: commit messages, code comments, test names, identifiers,
`CHANGELOG.md` entries and pull request descriptions.

## Changelog

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/). Add an entry
under `## [Unreleased]` for any change a user of the package can see.

## Pull request acceptance criteria

- Required checks pass: `Lint and type-check`, `Unit tests (...)`,
  `Integration (offline engine)`, `Build` and `gitleaks`.
- New behavior has tests, including the failure path.
- `CHANGELOG.md` updated under `[Unreleased]` when a user can see the change.
- At least one maintainer review (CODEOWNERS requests it).
- A blocked statement is never executed, and block messages never contain row
  data.
- The Contributor License Agreement is signed (`CLA` check).

## Releases

Releases are cut by the maintainers:

1. Set `__version__` in `llama_index/tools/vericto/_version.py` and date the version
   section in `CHANGELOG.md`, in a pull request.
2. After it is merged, tag the merge commit `vX.Y.Z` and push the tag.
3. The tag starts `release.yml`: `scripts/check_release.py` checks that the tag
   matches `__version__`, that `CHANGELOG.md` has the section and that no
   development-only `[tool.uv]` override is left; then lint, tests, the offline
   integration tests, the build and `twine check`; the wheel is installed from
   PyPI's dependencies in a clean environment. The `pypi` environment (a
   maintainer's approval) publishes with PyPI trusted publishing, and a GitHub
   release gets the files and their `SHA256SUMS`.

## Reporting security issues

Do **not** open a public issue for vulnerabilities. See [SECURITY.md](SECURITY.md)
or email [security@vericto.com](mailto:security@vericto.com).

## Contributor License Agreement

Before a pull request can be merged, every human commit author must sign the
Vericto Individual Contributor License Agreement, version 1.1
([CLA index](CLA.md), permanent text [legal/cla/1.1.md](legal/cla/1.1.md)).

Read the agreement and post this exact pull-request comment:

```
I have read the CLA Document and I hereby sign the CLA
```

The CLA workflow records your GitHub username and numeric account ID,
repository ID, pull-request number, comment ID, comment timestamp, CLA version
and SHA-256 document hash in `signatures/v1.1/cla.json` on the
`cla-signatures` branch, as described in
[CLA_PRIVACY_NOTICE.md](CLA_PRIVACY_NOTICE.md). If the check does not rerun,
comment `recheck`.

If an employer, client or other person may own rights in your contribution,
obtain written authorization and send it to
[legal@vericto.com](mailto:legal@vericto.com) before submitting.

## License

llama-index-tools-vericto is open source under the [Apache License 2.0](LICENSE). A
contribution you submit for inclusion is under the Apache License 2.0, as its
section 5 says, and under the [Contributor License
Agreement](#contributor-license-agreement). Add the `SPDX-FileCopyrightText` and
`SPDX-License-Identifier: Apache-2.0` header to new source files.
