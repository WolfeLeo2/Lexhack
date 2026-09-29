"""Read an uploaded filing (PDF, DOCX or plain text) into text for the filing checker. The file is not stored.

The text goes back to the page so the reader sees what was read before checking it. PDF pages without a text layer
(scans) are read by OCR on this server (Tesseract; the file never leaves it), up to OCR_MAX_PAGES, and the result says
which pages: OCR slips can look like misquotes, so the page tells the reader to compare with the original.
"""
import functools
import io
import re
import shutil
import subprocess
import unicodedata
import zipfile
from xml.etree import ElementTree

import pypdfium2
from pypdf import PdfReader

MAX_BYTES = 10 * 1024 * 1024
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MIN_PAGE_CHARS = 20   # a page with less text than this has no real text layer
OCR_MAX_PAGES = 30    # scanned pages read per file (~1-3 s each); longer scans are refused with a message
OCR_DPI = 300


@functools.cache
def tesseract():
    return shutil.which("tesseract") or next((p for p in ("/opt/homebrew/bin/tesseract", "/usr/bin/tesseract")
                                              if shutil.which(p)), None)


def ocr_available():
    return tesseract() is not None


def ocr_pages(data, numbers):
    """{page number (1-based): text} for the given pages: rendered grey at OCR_DPI, written as PGM for Tesseract."""
    doc, out = pypdfium2.PdfDocument(data), {}
    for n in numbers:
        bm = doc[n - 1].render(scale=OCR_DPI / 72, grayscale=True)
        buf = bytes(bm.buffer)
        pgm = b"P5\n%d %d\n255\n" % (bm.width, bm.height) + b"".join(
            buf[y * bm.stride:y * bm.stride + bm.width] for y in range(bm.height))
        run = subprocess.run([tesseract(), "stdin", "stdout", "-l", "eng", "--psm", "3"], input=pgm,
                             capture_output=True, timeout=120)
        out[n] = tidy(run.stdout.decode("utf-8", "replace"))
    return out


def tidy(text):
    """Ligatures to letters ('ﬁ' -> 'fi'), runs of spaces to one, no trailing spaces, at most one blank line."""
    text = unicodedata.normalize("NFKC", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


class ExtractError(Exception):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


def read_pdf(data, max_ocr_pages=OCR_MAX_PAGES):
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
    blank = [n for n, p in enumerate(pages, 1) if len(p) < MIN_PAGE_CHARS]
    ocr = []
    if blank and len(blank) * 2 >= len(pages):   # mostly without a text layer: a scan
        if not ocr_available():
            raise ExtractError("This PDF looks scanned: it has no text layer to read. Paste the text, or upload a PDF "
                               "or DOCX with selectable text.", 422)
        if len(blank) > max_ocr_pages:
            raise ExtractError(f"This PDF is a scan of {len(blank)} pages; Hakiki reads scans of up to "
                               f"{max_ocr_pages} pages. Upload the pages you need, or paste the text.", 422)
        for n, t in ocr_pages(data, blank).items():
            pages[n - 1] = t
        ocr = blank
        if sum(len(p) >= MIN_PAGE_CHARS for p in pages) * 2 < len(pages):
            raise ExtractError("This PDF looks scanned, and OCR found almost no text in it. Paste the text instead.", 422)
    text = "\n\n".join(p for p in pages if p)
    # layout mode keeps blank lines between paragraphs (by vertical gap), so quotes stay within their paragraph
    return {"kind": "pdf", "pages": len(pages), "text": text, "ocr_pages": ocr}


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
    return {"kind": "docx", "pages": None, "text": tidy("\n\n".join(paras)), "ocr_pages": []}


def read(data, filename="", max_bytes=MAX_BYTES, max_ocr_pages=OCR_MAX_PAGES):
    """-> {"kind": pdf|docx|text, "pages": int|None, "text": str, "ocr_pages": [int]}; raises ExtractError(message,
    HTTP status). The limits are for uploads; pipeline.fetch_sources lifts them."""
    if len(data) > max_bytes:
        raise ExtractError(f"That file is larger than {max_bytes // (1024 * 1024)} MB.", 413)
    if data.startswith(b"%PDF"):
        return read_pdf(data, max_ocr_pages)
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
    return {"kind": "text", "pages": None, "text": tidy(text.replace("\r\n", "\n")), "ocr_pages": []}
