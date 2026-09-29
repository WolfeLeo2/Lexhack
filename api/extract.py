"""Read an uploaded filing (PDF, DOCX or plain text) into text for the filing checker. The file is not stored.

The text goes back to the page so the reader sees what was read before checking it. No OCR: a PDF without a text
layer (a scan) is refused with a message saying so.
"""
import io
import re
import unicodedata
import zipfile
from xml.etree import ElementTree

from pypdf import PdfReader

MAX_BYTES = 10 * 1024 * 1024
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MIN_PAGE_CHARS = 20   # a page with less text than this has no real text layer


def tidy(text):
    """Ligatures to letters ('ﬁ' -> 'fi'), runs of spaces to one, no trailing spaces, at most one blank line."""
    text = unicodedata.normalize("NFKC", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


class ExtractError(Exception):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


def read_pdf(data):
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractError("This PDF is password-protected. Remove the password, or paste the text.", 422)
        # layout mode places text by position: plain mode breaks PDFs that draw every word as its own object on a
        # flipped page (Google Docs exports) into one word per line
        pages = [tidy(p.extract_text(extraction_mode="layout") or "") for p in reader.pages]
    except ExtractError:
        raise
    except Exception:
        raise ExtractError("This PDF could not be read. Try saving it again as PDF, or paste the text.", 422)
    text = "\n\n".join(p for p in pages if p)
    if sum(len(p) >= MIN_PAGE_CHARS for p in pages) * 2 < max(len(pages), 1):   # most pages have no text: a scan
        raise ExtractError("This PDF looks scanned: it has no text layer to read. Paste the text, or upload a PDF "
                           "or DOCX with selectable text.", 422)
    # layout mode keeps blank lines between paragraphs (by vertical gap), so quotes stay within their paragraph
    return {"kind": "pdf", "pages": len(pages), "text": text}


def read_docx(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ElementTree.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        raise ExtractError("This Word file could not be read. Save it again as DOCX or PDF, or paste the text.", 415)
    paras = []
    for p in root.iter(f"{W}p"):
        parts = []
        for el in p.iter():
            if el.tag == f"{W}t":
                parts.append(el.text or "")
            elif el.tag == f"{W}tab":
                parts.append("\t")
            elif el.tag in (f"{W}br", f"{W}cr"):
                parts.append("\n")
        line = "".join(parts).strip()
        if line:
            paras.append(line)
    # a blank line between paragraphs: quotes are attributed within a paragraph (api/filing.py blocks)
    return {"kind": "docx", "pages": None, "text": tidy("\n\n".join(paras))}


def read(data, filename=""):
    """-> {"kind": pdf|docx|text, "pages": int|None, "text": str}; raises ExtractError(message, HTTP status)."""
    if len(data) > MAX_BYTES:
        raise ExtractError(f"That file is larger than {MAX_BYTES // (1024 * 1024)} MB.", 413)
    if data.startswith(b"%PDF"):
        return read_pdf(data)
    if data.startswith(b"PK\x03\x04"):
        return read_docx(data)
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        raise ExtractError("Old Word (.doc) files can't be read. Save it as DOCX or PDF, or paste the text.", 415)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = None
    if text is None or "\x00" in text:
        raise ExtractError("Hakiki reads PDF, DOCX and plain text files.", 415)
    return {"kind": "text", "pages": None, "text": tidy(text.replace("\r\n", "\n"))}
