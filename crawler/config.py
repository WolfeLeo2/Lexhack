"""Environment + scope loading. Nothing here touches the network."""
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")


def require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        sys.exit(f"{name} is not set (environment or {REPO_ROOT / '.env'}). Refusing to start.")
    return val


def data_dir() -> Path:
    return Path(require_env("LEXHACK_DATA")).expanduser()


def raw_dir() -> Path:
    p = data_dir() / "raw"
    p.mkdir(parents=True, exist_ok=True)
    return p


def parsed_dir() -> Path:
    p = data_dir() / "parsed"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_agent() -> str:
    contact = require_env("CRAWLER_CONTACT")
    name = os.environ.get("CRAWLER_AGENT", "").strip() or "LexHackResearchBot/0.1"
    return f"{name} (student research project; contact: {contact})"


WAYBACK_RE = re.compile(r"^https?://web\.archive\.org/web/(\d{4,14})(?:[a-z]{2}_)?/(.+)$")


def origin(url: str) -> str:
    """Original URL of a Wayback playback URL (identity for anything else)."""
    m = WAYBACK_RE.match(url)
    return m.group(2) if m else url


def wayback_url(ts: str, original: str) -> str:
    """id_ = the archived bytes exactly as captured: no toolbar, no link rewriting."""
    return f"https://web.archive.org/web/{ts}id_/{original}"


@dataclass
class Scope:
    name: str
    hosts: list[str]
    kinds: list[tuple[str, re.Pattern]]      # first match wins
    follow: dict[str, list[str]]             # from_kind -> kinds whose links we enqueue
    same_work: list[str]                     # to_kinds only followed within the same FRBR work
    max_depth: int
    max_requests: int
    min_delay: float
    seeds: list[dict] = field(default_factory=list)
    wayback: dict | None = None              # set = fetch captures from the Internet Archive, not the origin

    def classify(self, url: str) -> str | None:
        url = origin(url)
        for kind, pat in self.kinds:
            if pat.search(url):
                return kind
        return None


def load_scope(path: str | Path) -> Scope:
    path = Path(path)
    if not path.is_absolute():
        path = Path(__file__).parent / path
    d = yaml.safe_load(path.read_text())
    return Scope(
        name=d["name"],
        hosts=d["hosts"],
        kinds=[(k["kind"], re.compile(k["pattern"])) for k in d["kinds"]],
        follow=d.get("follow", {}),
        same_work=d.get("same_work", []),
        max_depth=d["max_depth"],
        max_requests=d["max_requests"],
        min_delay=max(2.0, float(d.get("min_delay", 2.0))),   # hard floor: 2 s
        seeds=d.get("seeds", []),
        wayback=d.get("wayback"),
    )
