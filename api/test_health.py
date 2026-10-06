"""Checks health, liveness, readiness, root info, and version endpoints:
- /livez
- /readyz
- /health
- / (HTML and JSON)
- /api/version

  uv run python -m api.test_health
"""
import sys
from fastapi.testclient import TestClient

from . import main

fails = []


def expect(name, got, want):
    if got != want:
        fails.append((name, got, want))


def test_health_endpoints():
    with TestClient(main.app) as client:
        # Liveness probe
        r_livez = client.get("/livez")
        expect("/livez status 200", r_livez.status_code, 200)
        if r_livez.status_code == 200:
            expect("/livez status ok", r_livez.json().get("status"), "ok")

        # Readiness probe
        r_readyz = client.get("/readyz")
        expect("/readyz status 200", r_readyz.status_code, 200)
        if r_readyz.status_code == 200:
            data_readyz = r_readyz.json()
            expect("/readyz status ok", data_readyz.get("status"), "ok")
            expect("/readyz db connected", data_readyz.get("db"), "connected")

        # Consolidated /health probe
        r_health = client.get("/health")
        expect("/health status 200", r_health.status_code, 200)
        if r_health.status_code == 200:
            expect("/health status ok", r_health.json().get("status"), "ok")

        # Root service info - JSON negotiation
        r_root_json = client.get("/", headers={"accept": "application/json"})
        expect("/ JSON status 200", r_root_json.status_code, 200)
        if r_root_json.status_code == 200:
            data_root = r_root_json.json()
            expect("/ service name", data_root.get("service"), "Hakiki Citator API")
            expect("/ docs scalar link", data_root.get("docs", {}).get("scalar"), "/scalar")
            expect("/ docs swagger link", data_root.get("docs", {}).get("swagger"), "/docs")
            expect("/ docs redoc link", data_root.get("docs", {}).get("redoc"), "/redoc")

        # Root service info - HTML UI (browser negotiation)
        r_root_html = client.get("/", headers={"accept": "text/html,application/xhtml+xml"})
        expect("/ HTML status 200", r_root_html.status_code, 200)
        expect("/ HTML content-type", "text/html" in r_root_html.headers.get("content-type", ""), True)
        html = r_root_html.text
        expect("/ HTML has title", "Hakiki Citator API" in html, True)
        expect("/ HTML has scalar link", 'href="/scalar"' in html, True)
        expect("/ HTML has docs link", 'href="/docs"' in html, True)
        expect("/ HTML has redoc link", 'href="/redoc"' in html, True)
        expect("/ HTML has seal", "§" in html, True)

        # Version endpoint
        r_version = client.get("/api/version")
        expect("/api/version status 200", r_version.status_code, 200)
        if r_version.status_code == 200:
            expect("/api/version has version", r_version.json().get("version"), "0.1")


if __name__ == "__main__":
    test_health_endpoints()
    if fails:
        for name, got, want in fails:
            print(f"FAIL: {name} (got {got!r}, want {want!r})")
        sys.exit(1)
    print("PASS: all health & service info endpoints verified")
