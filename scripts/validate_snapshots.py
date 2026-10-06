"""Validate the committed snapshots in data/sample_output/ (used by CI).

Run:  python scripts/validate_snapshots.py
Exit code 1 if any snapshot is missing, unreadable or malformed.
"""
from __future__ import annotations

import json
import sys

try:
    import _bootstrap  # noqa: F401  (adds repo root to sys.path)
except ImportError:  # run as `python -m scripts.<name>`
    from scripts import _bootstrap  # noqa: F401

from src.cities import CITY_KEYS
from src.pipeline import precomputed_path, validate_snapshot


def main() -> int:
    failed = False
    for city in CITY_KEYS:
        path = precomputed_path(city)
        if not path.exists():
            print(f"FAIL {city}: {path} missing (run scripts/pull_live_data.py {city})")
            failed = True
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"FAIL {city}: invalid JSON ({exc})")
            failed = True
            continue
        problems = validate_snapshot(payload)
        if payload.get("meta", {}).get("sources", {}).get("competitors") == "google_places":
            problems.append("contains Google Places data, which must not be committed or "
                            "published (Google Maps Platform terms); keep it in data/private/")
        if problems:
            print(f"FAIL {city}: " + "; ".join(problems))
            failed = True
        else:
            s = payload["meta"]["sources"]
            print(f"ok   {city}: {len(payload['hexes'])} hexes, pois={s['pois']}, "
                  f"demographics={s['demographics']}, competitors={s['competitors']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
