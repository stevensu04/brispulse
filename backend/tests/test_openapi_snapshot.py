"""The committed OpenAPI document is the contract the web app's types are generated from.

If this fails, the API changed. Regenerate both files and commit them together:

    uv run python -m brispulse.openapi > openapi.json      (from backend/)
    npm run api:types                                      (from frontend/)
"""

import json
from pathlib import Path

from brispulse.openapi import document

SNAPSHOT = Path(__file__).resolve().parent.parent / "openapi.json"


def test_committed_openapi_document_matches_the_application() -> None:
    assert json.loads(SNAPSHOT.read_text()) == json.loads(document())
