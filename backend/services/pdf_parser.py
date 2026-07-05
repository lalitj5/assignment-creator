import io
import re
import pdfplumber

_MAX_CHARS = 6000


def extract_text(file_bytes: bytes) -> str:
    """Extract and clean text from a PDF given its raw bytes.

    Returns a string truncated to _MAX_CHARS to stay within the model's
    context window.  Empty pages are skipped.
    """
    parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                parts.append(text)

    combined = "\n\n".join(parts)
    # Collapse runs of whitespace (preserve single newlines as paragraph breaks)
    combined = re.sub(r"[ \t]+", " ", combined)
    combined = re.sub(r"\n{3,}", "\n\n", combined)
    return combined[:_MAX_CHARS]
