"""Dump the API's OpenAPI schema without booting a server.

The web's wire types are generated from this (`npm run gen:api-types`), and CI
diffs the committed apps/web/openapi.json against a fresh dump — so a response
model can't change without the web's types changing with it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# main.py fails fast at import when production has no CORS allowlist.
os.environ.setdefault("EWL_ENV", "development")

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from apps.api.main import app
from apps.api.schemas_responses import SSE_FRAMES

_REF_TEMPLATE = "#/components/schemas/{model}"


def main() -> None:
    spec = app.openapi()
    schemas = spec["components"]["schemas"]

    # The narration route returns a StreamingResponse, so FastAPI never sees the
    # frame models and won't publish them. Add them by hand — without this the web
    # is back to hand-typing the frame payloads.
    for model in SSE_FRAMES:
        schema = model.model_json_schema(ref_template=_REF_TEMPLATE)
        schemas.update(schema.pop("$defs", {}))
        schemas[model.__name__] = schema

    sys.stdout.write(json.dumps(spec, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
