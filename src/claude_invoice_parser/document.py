"""Read the raw text layer of a PDF, for checks that look at the document rather than the extraction.

This is everything a text extractor would see, including text a person can't: white text,
text drawn off the page, and text hidden under shapes. That is the point. Attacks hide in
there, so the validator compares it with what was extracted.
"""

from pathlib import Path

from pypdf import PdfReader


def pdf_text(path: Path) -> str:
    """Return the text layer of every page, or "" for image-only PDFs and unreadable files."""
    try:
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:  # a broken PDF should reach a person through the other checks, not crash the batch
        return ""
