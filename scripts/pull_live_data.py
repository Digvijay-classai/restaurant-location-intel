"""Build a snapshot from LIVE data: OpenStreetMap (Overpass) + INE tracts.

Run:
    python scripts/pull_live_data.py madrid
    python scripts/pull_live_data.py madrid --places      # + Google Places counts (PRIVATE output)
    python scripts/pull_live_data.py madrid --no-cache    # re-download from Overpass

Writes data/sample_output/<city>_demo.json with meta.sources.pois =
"osm_overpass". Demographics come from data/ine/<city>.csv when present,
otherwise city medians (labelled as such in the app).

On any failure nothing is written and the existing snapshot is kept.

Google Places data may not be shown on a non-Google map or cached long-term
(Google Maps Platform terms), so `--places` snapshots go to data/private/
(gitignored) by default and must never be committed or deployed. Load them
locally with `RLI_SNAPSHOT_DIR=data/private streamlit run app.py`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import _bootstrap  # noqa: F401  (adds repo root to sys.path, loads .env)
except ImportError:  # run as `python -m scripts.<name>`
    from scripts import _bootstrap  # noqa: F401

from src.cities import CITY_KEYS
from src.data_sources.google_places import PlacesError, api_key_present
from src.data_sources.overture_maps import OverpassError
from src.pipeline import PRIVATE_DIR, build_base_frame, write_snapshot


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build a LIVE snapshot from Overpass + INE.")
    p.add_argument("city", choices=CITY_KEYS, help="City to refresh.")
    p.add_argument("--places", action="store_true",
                   help="Also fetch Google Places competitor counts (needs GOOGLE_PLACES_API_KEY; "
                        "~9 calls per hex).")
    p.add_argument("--no-cache", action="store_true",
                   help="Ignore data/cache/osm_<city>.json and re-download.")
    p.add_argument("--out", type=Path, default=None,
                   help="Write to this path instead of data/sample_output/<city>_demo.json.")
    args = p.parse_args(argv)

    if args.places and args.out is None:
        args.out = PRIVATE_DIR / f"{args.city}_demo.json"
    if args.places and not api_key_present():
        print("error: --places needs GOOGLE_PLACES_API_KEY. Add it to .env (see .env.example).",
              file=sys.stderr)
        return 2

    print(f"[live] building {args.city} from Overpass"
          + (" + Google Places" if args.places else "") + " ...")
    try:
        result = build_base_frame(args.city, with_places=args.places, use_cache=not args.no_cache)
    except (OverpassError, PlacesError) as exc:
        print(f"error: {exc}\nThe existing snapshot was not modified.", file=sys.stderr)
        return 1

    path = write_snapshot(args.city, result.df, result.meta, args.out)
    if args.places:
        print("note: this snapshot contains Google Places data. Keep it private: don't commit, "
              "publish or deploy it (Google Maps Platform terms).")
    s = result.meta["sources"]
    print(f"wrote {path}  ({len(result.df)} hexes, {result.meta['n_pois']:,} POIs; "
          f"demographics={s['demographics']}, competitors={s['competitors']}, "
          f"boundary={s['boundary']})")
    if s["demographics"] != "ine_csv":
        print(f"note: no data/ine/{args.city}.csv, so demographics are city medians. The app "
              "will show the numbers but withhold verdicts (see data/ine/README.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
