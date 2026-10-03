"""Trace Content Redactor (PII Sanitizer) using Presidio Recognizers & Regex.

Sanitizes customer identifying details (names, phone numbers, emails, credit cards)
and secret tokens from user prompts before exporting spans to Langfuse.
"""

from __future__ import annotations

import json
import re
from typing import Any

_SECRET_PATTERNS = [
    (re.compile(r"\b(sk-proj-[A-Za-z0-9_-]+)\b"), "<REDACTED_API_KEY>"),
    (re.compile(r"\b(sk-lf-[A-Za-z0-9_-]+)\b"), "<REDACTED_API_KEY>"),
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{20,})\b"), "<REDACTED_API_KEY>"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]+=*"), "Bearer <REDACTED_TOKEN>"),
]

_REGEX_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "<EMAIL_ADDRESS>"),
    (re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "<PHONE_NUMBER>"),
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "<CREDIT_CARD>"),
]

_analyzer = None
_anonymizer = None

try:
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
    from presidio_anonymizer import AnonymizerEngine

    _analyzer = AnalyzerEngine()
    _anonymizer = AnonymizerEngine()

    intro_name_pattern = Pattern(
        name="intro_name_pattern",
        regex=r"\b(?:I'm|I am|My name is|This is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b",
        score=0.85,
    )
    name_recognizer = PatternRecognizer(supported_entity="PERSON", patterns=[intro_name_pattern])
    _analyzer.registry.add_recognizer(name_recognizer)
except Exception:
    pass


def redact_text(text: str, entities: list[str] | None = None) -> str:
    """Sanitize PII and secret tokens from user prompt text."""
    if not text:
        return text

    sanitized = text

    # Step 1: Redact API keys and Bearer tokens
    for pattern, replacement in _SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    # Step 2: Presidio PII analysis and anonymization
    target_entities = entities or ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "CREDIT_CARD"]
    if _analyzer and _anonymizer:
        try:
            results = _analyzer.analyze(text=sanitized, entities=target_entities, language="en")
            filtered_results = [r for r in results if r.score >= 0.3]
            if filtered_results:
                anonymized_result = _anonymizer.anonymize(text=sanitized, analyzer_results=filtered_results)
                sanitized = anonymized_result.text
        except Exception:
            pass

    # Step 3: High-precision regex fallback matchers
    for pattern, replacement in _REGEX_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized
