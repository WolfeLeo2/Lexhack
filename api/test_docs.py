"""Checks that API documentation endpoints are available:
- /docs (Swagger UI)
- /redoc (ReDoc)
- /scalar (Scalar API Reference)
- /openapi.json (OpenAPI schema)

  uv run python -m api.test_docs
"""
import sys
from fastapi.testclient import TestClient

from . import main

fails = []


def expect(name, got, want):
    if got != want:
        fails.append((name, got, want))


def test_docs():
    with TestClient(main.app) as client:
        # Swagger UI at /docs
        r_docs = client.get("/docs")
        expect("/docs status 200", r_docs.status_code, 200)

        # ReDoc at /redoc
        r_redoc = client.get("/redoc")
        expect("/redoc status 200", r_redoc.status_code, 200)

        # Scalar at /scalar
        r_scalar = client.get("/scalar")
        expect("/scalar status 200", r_scalar.status_code, 200)
        expect("/scalar contains scalar reference", "scalar" in r_scalar.text.lower(), True)

        # OpenAPI schema
        r_openapi = client.get("/openapi.json")
        expect("/openapi.json status 200", r_openapi.status_code, 200)
        data = r_openapi.json()
        expect("openapi title", data.get("info", {}).get("title"), "Hakiki Citator API")
        expect("openapi has description", bool(data.get("info", {}).get("description")), True)


if __name__ == "__main__":
    test_docs()
    if fails:
        for name, got, want in fails:
            print(f"FAIL: {name} (got {got!r}, want {want!r})")
        sys.exit(1)
    print("PASS: all docs endpoints verified (/docs, /redoc, /scalar, /openapi.json)")
