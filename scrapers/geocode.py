"""
Geocodes all centre postal codes via the OneMap API (no auth required).
API: https://www.onemap.gov.sg/api/common/elastic/search

Reads postal codes from data/ecda_centres-latest.json.
Merges against any existing data/geocoded-latest.json to avoid re-fetching
unchanged postcodes on repeat runs.

Output: data/geocoded.json  (→ geocoded-YYYY-MM-DD.json + geocoded-latest.json)
"""
import json
import time
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from scrapers.utils import fetch, make_client, write_dataset

API_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
CENTRES_PATH = Path("data/ecda_centres-latest.json")
EXISTING_PATH = Path("data/geocoded-latest.json")
OUT_PATH = Path("data/geocoded.json")
CRAWL_DELAY = 0.2  # OneMap is fast; 5 req/s is well within their limits
console = Console()


def load_existing(path: Path) -> dict[str, dict]:
    """postal_code → {lat, lng} from a previous geocoded run."""
    if not path.exists():
        return {}
    with open(path) as f:
        records = json.load(f)
    return {r["postal_code"]: r for r in records if r.get("lat") and r.get("lng")}


def geocode(client, postal: str) -> dict | None:
    """Return {lat, lng, block, road, building} or None on miss."""
    resp = fetch(
        client,
        f"{API_URL}?searchVal={postal}&returnGeom=Y&getAddrDetails=Y&pageNum=1",
    )
    data = resp.json()
    results = data.get("results", [])
    if not results:
        return None
    r = results[0]
    try:
        return {
            "lat": float(r["LATITUDE"]),
            "lng": float(r["LONGITUDE"]),
            "block": r.get("BLK_NO", ""),
            "road": r.get("ROAD_NAME", ""),
            "building": r.get("BUILDING", ""),
        }
    except (KeyError, ValueError):
        return None


def run() -> None:
    OUT_PATH.parent.mkdir(exist_ok=True)

    if not CENTRES_PATH.exists():
        raise RuntimeError(f"{CENTRES_PATH} is required but missing")

    with open(CENTRES_PATH) as f:
        centres = json.load(f)

    postals = sorted({c["postal_code"] for c in centres if c.get("postal_code")})
    console.print(f"Unique postal codes: {len(postals)}")

    existing = load_existing(EXISTING_PATH)
    to_fetch = [p for p in postals if p not in existing]
    console.print(f"Already cached: {len(existing)}, to fetch: {len(to_fetch)}")

    client = make_client()
    results: dict[str, dict] = dict(existing)
    misses = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Geocoding", total=len(to_fetch))

        for i, postal in enumerate(to_fetch):
            geo = geocode(client, postal)
            if geo:
                results[postal] = {"postal_code": postal, **geo}
            else:
                results[postal] = {"postal_code": postal, "lat": None, "lng": None}
                misses += 1

            progress.advance(task)

            if i < len(to_fetch) - 1:
                time.sleep(CRAWL_DELAY)

    records = list(results.values())
    matched = sum(1 for r in records if r.get("lat"))
    console.print(f"Geocoded: {matched}/{len(records)} ({misses} misses)")

    write_dataset(OUT_PATH, records)
    console.print(f"Saved to {OUT_PATH.stem}-latest.json")


if __name__ == "__main__":
    run()
