"""Secret scanning for collected files and dataset records.

The goal is to keep credentials out of a training set. It is a filter, not a
guarantee: review anything you plan to publish. Findings report the pattern name
and line number, never the secret itself.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("aws_secret_access_key", re.compile(r"(?i)aws.{0,20}?(?:secret|private).{0,20}?['\"][0-9a-zA-Z/+]{40}['\"]")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("gitlab_token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b")),
    ("hugging_face_token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("discord_bot_token", re.compile(r"\b[MNO][A-Za-z0-9_\-]{23,26}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,}\b")),
    ("stripe_key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("connection_string", re.compile(r"(?i)\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:@/]+:[^\s:@/]+@")),
    ("generic_assigned_secret", re.compile(
        r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd)\b"
        r"\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"
    )),
)

# Values that look like credentials but are obviously placeholders.
_PLACEHOLDER_HINTS = (
    "example", "placeholder", "changeme", "your_", "yourkey", "xxxx", "dummy",
    "sample", "redacted", "fake", "<", "${", "{{", "test_token", "notreal",
)

ENTROPY_MIN_LENGTH = 32
ENTROPY_THRESHOLD = 4.3


@dataclass
class SecretFinding:
    pattern: str
    line: int
    preview: str  # Always masked.


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _looks_like_placeholder(line: str) -> bool:
    lowered = line.lower()
    return any(hint in lowered for hint in _PLACEHOLDER_HINTS)


def _mask(match_text: str) -> str:
    if len(match_text) <= 8:
        return "*" * len(match_text)
    return f"{match_text[:3]}{'*' * 8}{match_text[-2:]}"


def scan_text(text: str, *, check_entropy: bool = True) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if len(line) > 4000:
            # Minified bundles produce endless false positives and are not worth
            # training on anyway.
            continue
        for name, pattern in PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            if name == "generic_assigned_secret" and _looks_like_placeholder(line):
                continue
            findings.append(SecretFinding(name, line_number, _mask(match.group(0))))

        if check_entropy and not _looks_like_placeholder(line):
            for token in re.findall(r"['\"]([A-Za-z0-9+/=_\-]{32,})['\"]", line):
                if len(token) >= ENTROPY_MIN_LENGTH and shannon_entropy(token) >= ENTROPY_THRESHOLD:
                    findings.append(SecretFinding("high_entropy_string", line_number, _mask(token)))
                    break

    return findings


def contains_secret(text: str, *, check_entropy: bool = True) -> bool:
    return bool(scan_text(text, check_entropy=check_entropy))


def redact(text: str) -> str:
    """Replace matched secrets with a marker, keeping the surrounding code intact."""

    redacted = text
    for name, pattern in PATTERNS:
        redacted = pattern.sub(f"<REDACTED:{name}>", redacted)
    return redacted
