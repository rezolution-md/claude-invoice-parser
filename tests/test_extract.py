"""Exercise extract_invoice against a mocked API, so the request shape is tested without a key."""

import json
from pathlib import Path

import anthropic
import httpx2 as httpx
import pytest

from claude_invoice_parser.extract import MODEL, ExtractionError, extract_invoice

ROOT = Path(__file__).parent.parent
PDF = ROOT / "samples" / "invoices" / "01-us-table.pdf"
EXPECTED = (ROOT / "samples" / "expected" / "01-us-table.json").read_text(encoding="utf-8")


def fake_client(stop_reason: str = "end_turn", text: str = EXPECTED, captured: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": MODEL,
                "content": [{"type": "text", "text": text}],
                "stop_reason": stop_reason,
                "stop_sequence": None,
                "usage": {"input_tokens": 1500, "output_tokens": 400},
            },
        )

    return anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.mark.skipif(not PDF.exists(), reason="run samples/generate_samples.py first")
def test_request_shape_and_parsing():
    captured: list = []
    result = extract_invoice(PDF, fake_client(captured=captured))

    body = captured[0]
    assert body["model"] == MODEL
    assert body["fallbacks"] == "default"
    assert body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"]["type"] == "json_schema"
    doc = body["messages"][0]["content"][0]
    assert doc["type"] == "document" and doc["source"]["media_type"] == "application/pdf"

    assert result.invoice.invoice_number == "BNS-24817"
    assert result.invoice.total == 1417.22
    assert (result.input_tokens, result.output_tokens) == (1500, 400)


@pytest.mark.skipif(not PDF.exists(), reason="run samples/generate_samples.py first")
def test_truncated_response_raises():
    with pytest.raises(ExtractionError, match="did not match the invoice schema"):
        extract_invoice(PDF, fake_client(stop_reason="max_tokens", text='{"vendor_name": "Blue'))
