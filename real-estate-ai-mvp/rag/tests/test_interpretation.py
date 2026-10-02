import httpx
import pytest

from rag_ingestion import interpretation


@pytest.mark.parametrize(
    ('status', 'provider_error', 'expected'),
    [
        (400, {'type': 'invalid_model', 'message': 'Invalid model'}, 'MISTRAL_EXTRACTION_MODEL'),
        (429, {'type': 'rate_limited', 'message': 'Rate limit exceeded'}, 'rate limit'),
    ],
)
def test_interpretation_http_errors_explain_the_action_without_exposing_provider_body(
    monkeypatch, status, provider_error, expected
):
    real_client = httpx.Client

    def client(**kwargs):
        transport = httpx.MockTransport(lambda request: httpx.Response(status, json=provider_error))
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(interpretation.httpx, 'Client', client)

    with pytest.raises(ValueError, match=expected) as error:
        interpretation.MistralInterpreter('private-test-key', 'bad-model')({'blocks': []})

    assert 'private-test-key' not in str(error.value)
    assert provider_error['message'] not in str(error.value)
