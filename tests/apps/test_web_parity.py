"""Guards the one web↔api contract still kept in sync by hand, by parsing the TS
source and comparing to the Python side so drift fails in CI:

  1. pipeline config defaults — web config.ts CONFIG_DEFAULTS vs PipelineRequest

Confidence tiers used to be guarded here too. The web no longer computes them —
it reads `confidence_tier` off the wire — so there is nothing left to drift.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_TS = _ROOT / "apps" / "web" / "lib" / "config.ts"


def _parse_web_config_defaults() -> dict[str, object]:
    text = _CONFIG_TS.read_text()
    # CONFIG_DEFAULTS = { ... } — scalars only, so the first `}` closes it.
    m = re.search(r"CONFIG_DEFAULTS[^{]*\{(.*?)\}", text, re.S)
    assert m, f"could not locate CONFIG_DEFAULTS object in {_CONFIG_TS}"
    out: dict[str, object] = {}
    for key, raw in re.findall(r'(\w+):\s*("[^"]*"|[\d.]+)', m.group(1)):
        out[key] = raw.strip('"') if raw.startswith('"') else float(raw)
    assert out, "parsed no CONFIG_DEFAULTS entries — config.ts format changed?"
    return out


def test_pipeline_config_defaults_match_web() -> None:
    from apps.api.schemas import PipelineRequest

    api = PipelineRequest().model_dump()
    web = _parse_web_config_defaults()

    assert set(web) == set(api), (
        f"config-key drift — web-only={set(web) - set(api)}, "
        f"api-only={set(api) - set(web)}"
    )
    for key, api_val in api.items():
        web_val = web[key]
        if isinstance(api_val, bool):
            assert str(web_val).lower() == str(api_val).lower(), f"{key}: web={web_val} api={api_val}"
        elif isinstance(api_val, (int, float)):
            assert float(web_val) == float(api_val), f"{key}: web={web_val} api={api_val}"
        else:
            assert str(web_val) == str(api_val), f"{key}: web={web_val!r} api={api_val!r}"
