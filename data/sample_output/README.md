# Snapshots

`<city>_demo.json` holds the pre-aggregated hex table the app loads, so the
app starts instantly without network access. Each file has a `meta` block
recording where every input came from (`meta.sources`) and when
(`meta.vintages`). The app's provenance bar reads it.

Check what is committed:

```bash
python scripts/validate_snapshots.py
```

**Live (needs network, ~1-5 min per city):**
```bash
python scripts/pull_live_data.py barcelona
# if overpass-api.de is busy (HTTP 504), use a mirror:
OVERPASS_URL=https://overpass.kumi.systems/api/interpreter python scripts/pull_live_data.py barcelona
```

**Synthetic (offline, deterministic, clearly labelled in the app):**
```bash
python scripts/build_demo_data.py            # skips cities that already have LIVE data
python scripts/build_demo_data.py --force    # replace LIVE data with synthetic
```

CI validates these files and never regenerates them.

## Licence

Snapshots combine OpenStreetMap-derived counts (© OpenStreetMap contributors) with INE statistics, so they are released under the **Open Database License (ODbL) 1.0**, with INE content under CC BY 4.0. See [DATA_LICENSES.md](../../DATA_LICENSES.md).
