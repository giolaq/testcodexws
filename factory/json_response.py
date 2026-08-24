"""Bounded extraction of structured decisions from noisy Agent Adapter output."""

from __future__ import annotations

import json


MAX_RESPONSE_CHARACTERS = 1_000_000


def extract_last_json_object(output: str, required_fields: set[str]) -> dict | None:
    """Return the last complete mapping with the required fields, if one exists."""
    bounded = output[-MAX_RESPONSE_CHARACTERS:]
    decoder = json.JSONDecoder()
    match = None
    for index, character in enumerate(bounded):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(bounded[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and required_fields <= set(value):
            match = value
    return match
