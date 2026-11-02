"""The structured shape every invoice is extracted into.

This one Pydantic model is both the output schema sent to Claude and the type the
rest of the pipeline works with, so the two can't drift apart.
"""

from typing import Optional

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str = Field(description="Line description exactly as printed.")
    quantity: Optional[float] = Field(description="Quantity as a number, or null if not printed.")
    unit_price: Optional[float] = Field(description="Price per unit as a number, or null if not printed.")
    line_total: float = Field(description="Line amount as printed. Negative for discounts or credits.")


class PaymentDetails(BaseModel):
    bank_name: Optional[str] = Field(description="Bank name, or null if not printed.")
    iban: Optional[str] = Field(description="IBAN without spaces, or null.")
    bic_swift: Optional[str] = Field(description="BIC or SWIFT code, or null.")
    account_number: Optional[str] = Field(description="Local account number, or null.")
    routing_or_sort_code: Optional[str] = Field(description="US routing number or UK sort code, or null.")


class Invoice(BaseModel):
    vendor_name: str
    vendor_tax_id: Optional[str] = Field(description="VAT, EIN, NIF or similar tax ID, or null.")
    customer_name: Optional[str]
    invoice_number: str
    issue_date: Optional[str] = Field(description="ISO date YYYY-MM-DD, or null if not printed.")
    due_date: Optional[str] = Field(
        description="ISO date YYYY-MM-DD. If only payment terms are printed (e.g. 'within 14 days'), "
        "compute it from the issue date. Null if neither is printed."
    )
    currency: str = Field(description="ISO 4217 code, e.g. USD, EUR, GBP.")
    line_items: list[LineItem]
    subtotal: Optional[float] = Field(description="Net amount before tax as printed, or null.")
    tax_rate_percent: Optional[float] = Field(description="Tax rate as a percentage, e.g. 19 for 19%, or null.")
    tax_amount: Optional[float] = Field(description="Tax amount as printed. 0 if tax is shown as zero or reverse charge.")
    total: float = Field(description="Final amount due as printed.")
    payment: PaymentDetails
    notes: Optional[str] = Field(
        description="Anything a bookkeeper should know that doesn't fit a field (reverse charge, deposits), or null."
    )
