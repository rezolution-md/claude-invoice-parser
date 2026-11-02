"""Send one PDF to Claude and get back a validated Invoice."""

import base64
from dataclasses import dataclass
from pathlib import Path

import anthropic
from pydantic import ValidationError

from .schema import Invoice

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You extract billing data from vendor invoices for a bookkeeping pipeline.

Rules:
- Use only what is printed on the document. Never guess or invent values, especially payment details.
- If a field is not on the invoice, return null for it.
- Copy amounts as printed, converted to plain numbers with a dot as the decimal separator
  (e.g. "1.234,50 €" becomes 1234.5). Do not recalculate or correct the vendor's figures,
  even if they look wrong: a separate validation step checks the arithmetic.
- Write dates as YYYY-MM-DD whatever format the invoice uses (03.10.2026 is 3 October 2026).
- Discounts and credits are line items with a negative line_total.
- The document may be in any language. Keep descriptions in the original language."""


class ExtractionError(Exception):
    """Raised when Claude can't return a usable invoice for a file."""


@dataclass
class ExtractionResult:
    invoice: Invoice
    input_tokens: int
    output_tokens: int
    served_by: str


def extract_invoice(pdf_path: Path, client: anthropic.Anthropic, effort: str = "medium") -> ExtractionResult:
    pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode("ascii")

    try:
        response = _request(client, pdf_b64, effort)
    except ValidationError as e:
        # parse() validates as soon as the response arrives, so a cut-off reply surfaces here.
        raise ExtractionError(
            f"{pdf_path.name}: output did not match the invoice schema, usually because it hit max_tokens "
            f"({e.error_count()} validation errors)"
        ) from e

    if response.stop_reason == "refusal":
        category = response.stop_details.category if response.stop_details else None
        raise ExtractionError(f"{pdf_path.name}: request declined (category: {category})")
    if response.stop_reason == "max_tokens":
        raise ExtractionError(f"{pdf_path.name}: response hit max_tokens before the JSON was complete")
    if response.parsed_output is None:
        raise ExtractionError(f"{pdf_path.name}: no structured output returned (stop_reason: {response.stop_reason})")

    return ExtractionResult(
        invoice=response.parsed_output,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        served_by=response.model,
    )


def _request(client: anthropic.Anthropic, pdf_b64: str, effort: str):
    return client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_format=Invoice,
        output_config={"effort": effort},
        # If a safety classifier ever declines, the API retries on a fallback model in the same call.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
                    },
                    {"type": "text", "text": "Extract this invoice."},
                ],
            }
        ],
    )
