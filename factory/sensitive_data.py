"""Shared credential detection and redaction for release and evidence paths."""

from __future__ import annotations

import re


CREDENTIAL_PATTERNS = (
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bBearer[ \t]+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
    re.compile(
        r"\b(?:OPENAI|ANTHROPIC|GITHUB|GH|AWS|AZURE)_[A-Z0-9_]+"
        r"[ \t]*[:=][ \t]*[\"']?[^ \t\r\n\"']{8,}"
    ),
)


def redact_credentials(value: str) -> str:
    result = value
    for pattern in CREDENTIAL_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def contains_credentials(value: str) -> bool:
    return any(pattern.search(value) for pattern in CREDENTIAL_PATTERNS)
