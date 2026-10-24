"""Regex pre-filter for obvious secrets. Runs before any Mubit call."""
import re

REDACTED = "[REDACTED]"

# Each pattern's group "value" is the part that gets redacted.
SECRET_PATTERNS = [
    re.compile(r"(?P<value>sk_live_[A-Za-z0-9_]+)"),
    re.compile(r"(?P<value>sk-[A-Za-z0-9_-]{20,})"),
    re.compile(r"(?P<value>AKIA[A-Z0-9]{16})"),
    re.compile(
        r"""(?i)\b(?P<key>\w*(?:api_?key|secret)\w*)['"]?\s*(?:=>|=|:)\s*['"](?P<value>[^'"\s]{16,})['"]"""
    ),
]

# Names that point at a secret rather than hold one (e.g. SecretId="prod/db").
REFERENCE_KEY = re.compile(r"(?i)(?:id|name|arn|path|ref|env|var)$")


def _matches(code):
    for pattern in SECRET_PATTERNS:
        for m in pattern.finditer(code):
            key = m.groupdict().get("key")
            if key and REFERENCE_KEY.search(key):
                continue
            yield m


def redact(code):
    for m in sorted(_matches(code), key=lambda m: m.start("value"), reverse=True):
        code = code[: m.start("value")] + REDACTED + code[m.end("value"):]
    return code


def check(code):
    """Return (label_or_None, redacted_code). label is 'hardcoded_secret' if found."""
    found = next(_matches(code), None) is not None
    return ("hardcoded_secret" if found else None), redact(code)
