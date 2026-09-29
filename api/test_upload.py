"""Checks for reading uploaded filings (api/extract.py). Fixtures are built here: a PDF with a text layer, one
without (a scan), a DOCX made with zipfile.

  uv run python -m api.test_upload
"""
import io
import zipfile

from . import extract

fails = []


def expect(name, got, want):
    if got != want:
        fails.append((name, got, want))


def pdf(lines_per_page):
    """A minimal PDF, one text line per entry; a page with no lines has no text layer (like a scan)."""
    objs = ["<</Type/Catalog/Pages 2 0 R>>", None, "<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    kids = []
    for lines in lines_per_page:
        ops = "".join(f"({line}) Tj T* " for line in lines)
        stream = f"BT /F1 12 Tf 14 TL 72 720 Td {ops}ET" if lines else ""
        objs.append(f"<</Length {len(stream)}>>stream\n{stream}\nendstream")
        objs.append(f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 3 0 R>>>>"
                    f"/Contents {len(objs)} 0 R>>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<</Type/Pages/Kids[{' '.join(kids)}]/Count {len(kids)}>>"
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj{body}endobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def pdf_word_objects(lines, extra=""):
    """A PDF laid out the way Google Docs exports: every word its own text object (BT..ET), positioned on its line."""
    # like Google Docs: a flipped page (cm) and text matrix (Tm), every word AND every space its own text object
    ops, y = ["1 0 0 -1 0 792 cm"], 72
    for line in lines:
        x = 72
        for word in line.split():
            ops.append(f"BT /F1 12 Tf 1 0 0 -1 0 0 Tm {x} {-y} Td ({word}) Tj ET")
            x += 7 * len(word)
            ops.append(f"BT /F1 12 Tf 1 0 0 -1 0 0 Tm {x} {-y} Td ( ) Tj ET")
            x += 4
        y += 16
    stream = "\n".join(ops) + extra
    objs = ["<</Type/Catalog/Pages 2 0 R>>", "<</Type/Pages/Kids[5 0 R]/Count 1>>",
            "<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>", f"<</Length {len(stream)}>>stream\n{stream}\nendstream",
            "<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 3 0 R>>>>/Contents 4 0 R>>"]
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj{body}endobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def docx(paragraphs):
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p>{''.join(f'<w:r><w:t xml:space=\"preserve\">{run}</w:t></w:r>' for run in p)}</w:p>"
                   for p in paragraphs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f'<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>')
    return buf.getvalue()


def error_of(data, name):
    try:
        extract.read(data, name)
    except extract.ExtractError as e:
        return e.status
    return None


def main():
    r = extract.read(pdf([["In Okuta v AG [2017] eKLR the court held that"], ["section 194 of the Penal Code"]]),
                     "submissions.pdf")
    expect("pdf kind and pages", (r["kind"], r["pages"]), ("pdf", 2))
    expect("pdf text, pages apart", "[2017] eKLR the court held that" in r["text"] and
           "\n\nsection 194 of the Penal Code" in r["text"], True)
    expect("scanned pdf refused", error_of(pdf([[], []]), "scan.pdf"), 422)
    r = extract.read(pdf_word_objects(["In Okuta v Attorney General the court held", "that section 194 is limited"]),
                     "gdocs.pdf")
    expect("word-per-object pdf reads as lines of words", r["text"],
           "In Okuta v Attorney General the court held\nthat section 194 is limited")
    expect("ligatures become letters", extract.tidy("we \ufb01nd the o\ufb03ce  was   \ufb02at"), "we find the office was flat")
    r = extract.read(docx([["1. In Okuta v AG ", "[2017] eKLR"], [], ["2. Section 204 of the Penal Code."]]), "f.docx")
    expect("docx paragraphs, runs joined, empty dropped", (r["kind"], r["text"]),
           ("docx", "1. In Okuta v AG [2017] eKLR\n\n2. Section 204 of the Penal Code."))
    r = extract.read("Plain filing text, section 107 of the Evidence Act.".encode(), "f.txt")
    expect("text file", (r["kind"], r["text"]), ("text", "Plain filing text, section 107 of the Evidence Act."))
    expect("old .doc refused", error_of(b"\xd0\xcf\x11\xe0" + b"\x00" * 100, "old.doc"), 415)
    expect("binary refused", error_of(b"\x00\x01\x02garbage", "x.bin"), 415)
    expect("too large refused", error_of(b"a" * (extract.MAX_BYTES + 1), "big.txt"), 413)
    for f in fails:
        print("FAIL", *f)
    print("FAILED" if fails else "all passed")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
