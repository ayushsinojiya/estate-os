"""Credentials in request URLs never reach the logs."""

import logging

from app.observability.logging import RedactSecrets, configure, redact


def test_webhook_token_is_masked_in_access_log_lines():
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                               ("100.100.0.50:44198", "POST", "/telephony/voicelink/webhook?token=fakeTok1", "1.1", 200),
                               None)
    RedactSecrets().filter(record)
    line = record.getMessage()
    assert "fakeTok1" not in line and "/telephony/voicelink/webhook?token=***" in line


def test_other_query_parameters_are_left_alone():
    assert redact("/v1/x?phone=%2B91&api_key=abc&days=3") == "/v1/x?phone=%2B91&api_key=***&days=3"


def test_configure_attaches_the_filter_to_uvicorn_access():
    configure("INFO", "text")
    assert any(isinstance(f, RedactSecrets) for f in logging.getLogger("uvicorn.access").filters)
