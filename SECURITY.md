# Security Policy

Vericto is a security product. We take vulnerabilities seriously and
appreciate responsible disclosure.

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report it privately, by either channel:

- Email **security@vericto.com**.
- Open a private report on GitHub:
  [Report a vulnerability](https://github.com/vericto/llama-index-vericto/security/advisories/new)
  (Security tab → "Report a vulnerability"). Only the maintainers can see it.

Include:

- A description of the vulnerability and its impact.
- Steps to reproduce.
- The affected versions
  (`python -c "import llama_index.tools.vericto as v, vericto; print(v.__version__, vericto.__version__)"`)
  and the LlamaIndex versions involved.
- Any suggested remediation.

You will receive an acknowledgement within **48 hours** and a status update
within **5 business days**.

## Scope

High-priority issues for this package include:

- **Guard bypass**: a path through `VerictoSQLDatabase` (or `VerictoToolSpec`'s
  `run_sql`, or a LlamaIndex query engine built on it) that executes SQL Vericto
  did not evaluate, or blocked, outside an explicit `fail_mode="open"`; or a
  masked statement that runs the original SQL instead of the rewrite.
- **Wrong "allowed"**: `check_sql` reporting `allowed: true` for a statement
  Vericto blocked or did not evaluate.
- **Credential exposure**: the API key written to logs, tool output, traces or
  anywhere other than the configured Vericto API over TLS.
- **Data leakage**: row data or parameter values in a block message, or
  parameter values sent to Vericto.

Issues in the evaluation itself (a statement that got the wrong verdict) belong
to [vericto-engine](https://github.com/vericto/vericto-engine/security); issues
in the SDK's transport or offline process handling to
[vericto-python](https://github.com/vericto/vericto-python/security).

## Disclosure process

1. Report received and acknowledged (within 48h).
2. We confirm and assess severity.
3. We develop and test a fix.
4. We release the fix and credit you (unless you prefer to remain anonymous).
5. Public disclosure after users have had reasonable time to update.

## Supported versions

Security fixes are applied to the latest released version. Older versions are
patched at the maintainers' discretion.

Thank you for helping keep Vericto and its users safe.
