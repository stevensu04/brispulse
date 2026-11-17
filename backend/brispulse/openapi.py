"""Prints the API's OpenAPI document: ``python -m brispulse.openapi > openapi.json``."""

import json

from brispulse.main import create_app


def document() -> str:
    # Sorted and indented, so a change to the API shows up as a readable diff.
    return json.dumps(create_app().openapi(), indent=1, sort_keys=True) + "\n"


if __name__ == "__main__":
    print(document(), end="")
