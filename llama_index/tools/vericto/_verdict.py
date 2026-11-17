# SPDX-FileCopyrightText: 2026 Vericto S.A.S.
# SPDX-License-Identifier: Apache-2.0

"""The structured verdict `check_sql` returns: a plain, JSON-serializable dict."""

from __future__ import annotations

from typing import TypedDict

from vericto import Decision, Verdict

# Decisions under which Vericto lets the statement run. PARSE_ERROR is in the list
# because the workspace policy (offline: the standard behavior) lets an unparsed
# statement run and reports it; BLOCKED and UNEVALUATED are not.
_RUNNABLE = frozenset(
    {Decision.ALLOWED, Decision.FLAGGED, Decision.MONITORED, Decision.PARSE_ERROR}
)


class FindingDict(TypedDict):
    """One rule that matched the statement."""

    rule_code: str
    severity: str | None
    suggested_fix: str | None
    location: str | None


class VerdictDict(TypedDict):
    """The verdict of `VerictoToolSpec.check_sql`, as a JSON-serializable dict.

    Keys:
        decision: `ALLOWED`, `FLAGGED`, `MONITORED`, `PARSE_ERROR`, `BLOCKED`, or
            `UNEVALUATED` (Vericto could not answer and `fail_mode="open"`).
        allowed: whether Vericto lets the statement run (`False` for `BLOCKED` and
            `UNEVALUATED`).
        blocked: whether Vericto blocked it.
        evaluated: `False` only for `UNEVALUATED`.
        rule_codes: the rules that matched, deciding rule first.
        severity: the deciding rule's severity.
        messages: human-readable reasons, one per finding or server message.
        suggested_fix: a safer statement or advice from Vericto, when it has one.
        findings: one entry per matched rule.
        rewritten_query: when set, the statement that runs instead (sensitive
            columns masked; online only).
        dialect: the dialect the statement was evaluated as.
        mode: `"offline"` (local engine, standard rules) or `"online"` (your
            workspace's rules through the Vericto Runtime API).
        engine_version: the vericto-engine version, when known.
        ruleset_version: the ruleset the verdict was computed under, when known.
        event_id: the audit-trail event id (online only).
        summary: one paragraph for the model: what happened and what to do next.
    """

    decision: str
    allowed: bool
    blocked: bool
    evaluated: bool
    rule_codes: list[str]
    severity: str | None
    messages: list[str]
    suggested_fix: str | None
    findings: list[FindingDict]
    rewritten_query: str | None
    dialect: str
    mode: str
    engine_version: str | None
    ruleset_version: str | None
    event_id: str | None
    summary: str


def _finding_message(rule_code: str, severity: str | None, location: str | None) -> str:
    text = f"{rule_code}"
    if severity:
        text += f" ({severity})"
    text += " matched"
    if location:
        text += f" at {location}"
    return text + "."


def verdict_to_dict(verdict: Verdict) -> VerdictDict:
    """Turn a `vericto.Verdict` into the structured verdict `check_sql` returns."""
    findings: list[FindingDict] = [
        {
            "rule_code": f.rule_code,
            "severity": f.severity,
            "suggested_fix": f.suggested_fix,
            "location": f.ast_node_path,
        }
        for f in verdict.findings
    ]
    messages = [_finding_message(f["rule_code"], f["severity"], f["location"]) for f in findings]
    if verdict.message:
        messages.insert(0, verdict.message)
    if verdict.parse_error:
        messages.append(f"Parser: {verdict.parse_error}")
    return {
        "decision": verdict.decision.value,
        "allowed": verdict.decision in _RUNNABLE,
        "blocked": verdict.blocked,
        "evaluated": verdict.decision is not Decision.UNEVALUATED,
        "rule_codes": [f["rule_code"] for f in findings],
        "severity": verdict.severity,
        "messages": messages,
        "suggested_fix": verdict.suggested_fix,
        "findings": findings,
        "rewritten_query": verdict.rewritten_query,
        "dialect": verdict.dialect,
        "mode": verdict.mode,
        "engine_version": verdict.engine_version,
        "ruleset_version": verdict.ruleset_version,
        "event_id": verdict.event_id,
        "summary": summarize(verdict),
    }


def _rule_label(verdict: Verdict) -> str:
    rule = verdict.rule_code or "a Vericto rule"
    return f"{rule}, severity {verdict.severity}" if verdict.severity else rule


def block_message(verdict: Verdict) -> str:
    """What the model reads when its statement is blocked. Never contains row data."""
    lines = [f"Vericto blocked this query ({_rule_label(verdict)}). It was NOT executed."]
    if verdict.message:
        lines.append(f"Reason: {verdict.message}")
    others = [f.rule_code for f in verdict.findings if f.rule_code != verdict.rule_code]
    if others:
        lines.append("Other findings: " + ", ".join(others) + ".")
    if verdict.suggested_fix:
        lines.append(f"Suggested fix: {verdict.suggested_fix}")
        lines.append("Rewrite the query following the suggested fix and try again.")
    else:
        lines.append(
            "Rewrite the query so that it complies with this rule, "
            "or tell the user it cannot be run."
        )
    return " ".join(lines)


def summarize(verdict: Verdict) -> str:
    """One paragraph for the model: the decision and what to do next."""
    decision = verdict.decision
    if decision is Decision.BLOCKED:
        return block_message(verdict)
    if decision is Decision.UNEVALUATED:
        reason = verdict.message or "no verdict"
        return (
            f"Vericto could not evaluate the query ({reason}). Treat it as unchecked: "
            "do not run it unless the user confirms."
        )
    if decision is Decision.ALLOWED:
        text = "Vericto found no problem with this query. It may run."
    elif decision is Decision.PARSE_ERROR:
        text = (
            "Vericto could not parse the query; the policy lets it run, unchecked. "
            "Check the SQL syntax for the dialect."
        )
    else:
        text = f"{decision.value}: the query may run ({_rule_label(verdict)})."
        if verdict.suggested_fix:
            text += f" Consider: {verdict.suggested_fix}"
    if verdict.rewritten_query:
        text += (
            f" Sensitive columns are masked: the query that will run is: {verdict.rewritten_query}"
        )
    return text
