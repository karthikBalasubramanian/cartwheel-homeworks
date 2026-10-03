"""Unit and contract tests for observability instrumentation and session authentication.

Homework 2 Part A (instrumentation) and Part D (authentication).
"""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent.auth import AuthContext
from observability.instrument import record_tool_result, _set_permission_denied_attributes


def test_record_tool_result_shopper_success() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    ctx = AuthContext(user_id=1, role="shopper")
    result = {"ok": True, "orders": []}

    with tracer.start_as_current_span("test_tool_span"):
        record_tool_result(ctx, result)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = spans[0].attributes
    assert attrs["cartwheel.user_role"] == "shopper"
    assert attrs["cartwheel.user_id"] == "1"
    assert "cartwheel.store_id" not in attrs
    assert attrs["cartwheel.permission_denied"] is False
    assert "cartwheel.permission_denied.reason" not in attrs


def test_record_tool_result_merchant_permission_denied() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    ctx = AuthContext(user_id=9001, role="merchant", store_id=1)
    result = {
        "ok": False,
        "error": "permission_denied",
        "reason": "order belongs to another store",
    }

    with tracer.start_as_current_span("test_tool_span"):
        record_tool_result(ctx, result)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = spans[0].attributes
    assert attrs["cartwheel.user_role"] == "merchant"
    assert attrs["cartwheel.user_id"] == "9001"
    assert attrs["cartwheel.store_id"] == "1"
    assert attrs["cartwheel.permission_denied"] is True
    assert attrs["cartwheel.permission_denied.reason"] == "order belongs to another store"


def test_create_session_role_mismatch_rejected() -> None:
    import pytest
    from fastapi import HTTPException
    from server import app as server_app

    # User 1 is a shopper in the database. Claiming "merchant" must be rejected with 403.
    with pytest.raises(HTTPException) as exc_info:
        server_app.create_session(server_app.SessionCreate(user_id=1, role="merchant"))
    assert exc_info.value.status_code == 403


def test_cross_session_token_authorization_rejected() -> None:
    import pytest
    from fastapi import HTTPException
    from server import app as server_app

    server_app._SESSIONS.clear()
    res1 = server_app.create_session(server_app.SessionCreate(user_id=1, role="shopper"))
    res2 = server_app.create_session(server_app.SessionCreate(user_id=2, role="shopper"))

    # Token issued for session 1 must not authorize session 2.
    with pytest.raises(HTTPException) as exc_info:
        server_app._authorize(res2["session_id"], f"Bearer {res1['token']}")
    assert exc_info.value.status_code == 403


def test_redact_text_pii_entities() -> None:
    from observability.redact import redact_text

    raw = "I'm Alex Johnson. Call me at 415-555-0132 or email alex@example.com about my refund."
    redacted = redact_text(raw)

    assert "Alex Johnson" not in redacted
    assert "415-555-0132" not in redacted
    assert "alex@example.com" not in redacted
    assert "<PERSON>" in redacted or "<PHONE_NUMBER>" in redacted
    assert "<PHONE_NUMBER>" in redacted
    assert "<EMAIL_ADDRESS>" in redacted
