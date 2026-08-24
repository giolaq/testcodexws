"""Validated, read-only code-review results for a candidate pull request."""

from __future__ import annotations

from pathlib import PurePosixPath

from json_response import extract_last_json_object


SCHEMA_VERSION = 2
MAX_FINDINGS = 30
MAX_TEXT = 2_000
SEVERITIES = {"blocking", "warning", "note"}


class CodeReviewError(ValueError):
    """The review adapter returned an invalid or unsafe result."""


def extract_review(output: str) -> dict:
    """Extract the last JSON object from adapter output.

    Agent CLIs may add progress text around the response, so decode each object
    candidate and keep the last complete mapping.
    """
    value = extract_last_json_object(
        output, {"schema_version", "decision", "summary", "findings"},
    )
    if value is None:
        raise CodeReviewError("Code Review Agent did not return a structured JSON decision.")
    return value


def _text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CodeReviewError(f"Code review requires {field}.")
    value = value.strip()
    if len(value) > MAX_TEXT:
        raise CodeReviewError(f"Code review {field} is longer than {MAX_TEXT} characters.")
    return value


def validate_review(value: dict, changed_paths: set[str]) -> dict:
    """Validate and normalize a review before it can affect lifecycle state."""
    fields = {"schema_version", "decision", "summary", "findings"}
    if not isinstance(value, dict) or set(value) != fields:
        raise CodeReviewError(
            "Code review fields must be exactly " + ", ".join(sorted(fields)) + "."
        )
    if value["schema_version"] != SCHEMA_VERSION:
        raise CodeReviewError(f"Code review schema_version must be {SCHEMA_VERSION}.")
    decision = value["decision"]
    if decision not in {"APPROVE", "REQUEST_CHANGES"}:
        raise CodeReviewError("Code review decision must be APPROVE or REQUEST_CHANGES.")
    summary = _text(value["summary"], "summary")
    findings = value["findings"]
    if not isinstance(findings, list) or len(findings) > MAX_FINDINGS:
        raise CodeReviewError(f"Code review findings must be a list of at most {MAX_FINDINGS} items.")

    normalized = []
    for finding in findings:
        expected = {"severity", "path", "line", "message"}
        if not isinstance(finding, dict) or set(finding) != expected:
            raise CodeReviewError(
                "Each code review finding must contain severity, path, line, and message."
            )
        severity = finding["severity"]
        if severity not in SEVERITIES:
            raise CodeReviewError("Code review severity must be blocking, warning, or note.")
        path = _text(finding["path"], "finding path")
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts or path not in changed_paths:
            raise CodeReviewError(f"Code review finding targets unchanged or unsafe path: {path}")
        line = finding["line"]
        if line is not None and (not isinstance(line, int) or isinstance(line, bool) or line < 1):
            raise CodeReviewError("Code review finding line must be a positive integer or null.")
        normalized.append({
            "severity": severity,
            "path": path,
            "line": line,
            "message": _text(finding["message"], "finding message"),
        })

    if decision == "REQUEST_CHANGES" and not normalized:
        raise CodeReviewError("REQUEST_CHANGES requires at least one review comment.")
    if decision == "APPROVE" and normalized:
        raise CodeReviewError("APPROVE cannot contain comments; request changes so implementation fixes them.")
    return {
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "summary": summary,
        "findings": normalized,
    }


def render_review_comment(review: dict, ticket_number: int, attempt: int) -> str:
    """Render a validated result as bounded Markdown for a GitHub PR comment."""
    def safe_text(value: str) -> str:
        # Avoid turning untrusted review prose into unsolicited GitHub mentions.
        return value.replace("@", "@\u200b")

    icon = "✅" if review["decision"] == "APPROVE" else "🔁"
    lines = [
        f"## {icon} Factory Code Review · {review['decision'].replace('_', ' ')}",
        "",
        f"Ticket #{ticket_number}, implementation attempt {attempt}.",
        "",
        safe_text(review["summary"]),
    ]
    if review["findings"]:
        lines += ["", "### Findings", ""]
        for finding in review["findings"]:
            location = f"`{finding['path'].replace('`', 'ˋ')}`"
            if finding["line"]:
                location += f" line {finding['line']}"
            lines.append(f"- **{finding['severity'].title()}** · {location}: {safe_text(finding['message'])}")
    else:
        lines += ["", "No findings were reported."]
    lines += [
        "",
        "This is an automated, read-only review decision. The Supervisor may recommend only this approved revision; normal profiles still require a human exact-revision merge action.",
    ]
    return "\n".join(lines)
