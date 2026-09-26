"""Check the ground truth against the stored sources. Offline; run after every edit.

  uv run python -m ground_truth.check

Every quote must appear verbatim (whitespace-normalised) in the parsed judgment, every provision must
exist in a parsed Act version, and every affects_event must point at a real row.
"""
import csv
import json
import re
import sys
from pathlib import Path

from crawler.config import parsed_dir

HERE = Path(__file__).parent
ACT_WORKS = {"cap-63": "1930_10", "cap-63a": "2006_3", "cap-411a": "1998_2"}   # act slug -> AKN work
EVENT_TYPES = {"declared_unconstitutional", "read_down", "severed", "upheld", "interpreted",
               "reversed_on_appeal", "repealed_by_statute", "amended_by_statute"}


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def judgment_text(judgment_id):
    stem = "akn_" + judgment_id.replace("/", "_") + "_eng@"
    files = [f for f in (parsed_dir() / "judgment").glob(stem + "*.json") if "source" not in f.name]
    return norm(json.loads(files[0].read_text())["text"]) if files else None


def provision_exists(provision_id):
    _, _, slug, eid = provision_id.split("/", 3)
    for f in (parsed_dir() / "act").glob(f"akn_ke_act_{ACT_WORKS[slug]}_*.json"):
        if any(s["eid"] == eid for s in json.loads(f.read_text())["sections"]):
            return True
    return False


def main():
    errors = []
    events = list(csv.DictReader(open(HERE / "events.csv")))
    keys = {e["event_key"] for e in events}
    for e in events:
        k = e["event_key"]
        text = judgment_text(e["judgment_id"])
        if text is None:
            errors.append(f"{k}: no parsed judgment for {e['judgment_id']}")
        else:
            for col in ("operative_quote", "scope_text"):
                if e[col] and norm(e[col]) not in text:
                    errors.append(f"{k}: {col} not found verbatim in {e['judgment_id']}")
        if not provision_exists(e["provision_id"]):
            errors.append(f"{k}: unknown provision {e['provision_id']}")
        if e["event_type"] not in EVENT_TYPES:
            errors.append(f"{k}: bad event_type {e['event_type']}")
        if e["scope"] not in ("total", "partial"):
            errors.append(f"{k}: bad scope {e['scope']}")
        if e["scope"] == "partial" and not e["scope_text"]:
            errors.append(f"{k}: partial scope needs scope_text")
        if e["affects_event"] and e["affects_event"] not in keys:
            errors.append(f"{k}: affects_event {e['affects_event']} does not exist")
        if e["verified"] not in ("true", "false"):
            errors.append(f"{k}: verified must be true/false")
    for n in csv.DictReader(open(HERE / "negatives.csv")):
        if judgment_text(n["judgment_id"]) is None:
            errors.append(f"negative: no parsed judgment for {n['judgment_id']}")
        if not provision_exists(n["provision_id"]):
            errors.append(f"negative: unknown provision {n['provision_id']}")
    verified = sum(e["verified"] == "true" for e in events)
    print("\n".join(errors) or f"OK: {len(events)} events ({verified} verified), all quotes found in source")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
