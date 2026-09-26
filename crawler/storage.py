"""WARC storage: gzip-per-record WARC files rotated at ~1 GB, indexed in frontier.db."""
import io
import os
from pathlib import Path

from warcio.archiveiterator import ArchiveIterator
from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import WARCWriter

from .frontier import now

ROTATE_BYTES = 1_000_000_000


class WarcStore:
    def __init__(self, raw_dir: Path, frontier, prefix="kenyalaw"):
        self.dir = raw_dir
        self.frontier = frontier
        self.prefix = prefix

    def _current(self) -> Path:
        files = sorted(self.dir.glob(f"{self.prefix}-*.warc.gz"))
        if files and files[-1].stat().st_size < ROTATE_BYTES:
            return files[-1]
        return self.dir / f"{self.prefix}-{len(files):05d}.warc.gz"

    def write(self, url, req_headers: dict, status: int, reason: str, resp_headers: list, body: bytes):
        path = self._current()
        with open(path, "ab") as f:
            writer = WARCWriter(f, gzip=True)
            http_resp = StatusAndHeaders(f"{status} {reason}", resp_headers, protocol="HTTP/1.1")
            resp = writer.create_warc_record(url, "response", payload=io.BytesIO(body), http_headers=http_resp)
            path_qs = url.split("/", 3)[3] if url.count("/") >= 3 else ""
            http_req = StatusAndHeaders(f"GET /{path_qs} HTTP/1.1", list(req_headers.items()), is_http_request=True)
            req = writer.create_warc_record(url, "request", http_headers=http_req)
            writer.ensure_digest(resp, block=False, payload=True)
            req.rec_headers.replace_header("WARC-Concurrent-To", resp.rec_headers.get_header("WARC-Record-ID"))
            ctype = dict((k.lower(), v) for k, v in resp_headers).get("content-type")
            for rec, rtype in ((resp, "response"), (req, "request")):
                start = f.tell()
                writer.write_record(rec)
                f.flush()
                os.fsync(f.fileno())
                self.frontier.add_record(warc_file=path.name, offset=start, length=f.tell() - start, uri=url,
                                         record_type=rtype, http_status=status if rtype == "response" else None,
                                         content_type=ctype, date=now())


def read_record(raw_dir: Path, warc_file: str, offset: int):
    """Returns (http_headers, body bytes) for one indexed record, via seek, like the Pocket Law reader."""
    with open(raw_dir / warc_file, "rb") as f:
        f.seek(offset)
        rec = next(iter(ArchiveIterator(f)))
        return rec.http_headers, rec.content_stream().read()
