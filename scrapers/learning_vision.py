"""
Scrapes all Learning Vision preschool centre data.
Source: embedded JSON on https://learningvision.com/centres/

The page embeds a JS variable with all centre records including name, slug,
address, and lat/lng coordinates. Individual centre pages do not expose
per-centre contact info so we only scrape the index page.

Fields extracted: url, name, address, postal_code, lat, lng

Join key to ecda_centres: postal_code (when present in address text)
  or spatial proximity using lat/lng (see merge.py)
Output: data/learning_vision.json
"""
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from curl_cffi import requests as curl_requests

from scrapers.utils import write_dataset

CENTRES_URL = "https://learningvision.com/centres/"
OUT_PATH = Path("data/learning_vision.json")

_POSTAL_RE = re.compile(r"\b(\d{6})\b")
_NAME_CLEAN_RE = re.compile(r"<br\s*/?>", re.I)


@dataclass
class Centre:
    url: str
    name: str | None
    address: str | None
    postal_code: str | None
    lat: float | None
    lng: float | None


def parse_centres(html: str) -> list[Centre]:
    # The page embeds: [{"name":"all","posts":[...]},{"name":"central","posts":[...]},...]
    # Use JSONDecoder.raw_decode to parse from the start of the array
    start = html.find('[{"name":"all"')
    if start == -1:
        return []
    decoder = json.JSONDecoder()
    groups, _ = decoder.raw_decode(html, start)
    all_group = next((g for g in groups if g.get("name") == "all"), None)
    posts = all_group["posts"] if all_group else []

    results = []
    for post in posts:
        slug = post.get("slug", "")
        url = f"https://learningvision.com/centres/{slug}/"

        raw_name = post.get("name", "")
        name = _NAME_CLEAN_RE.sub(" ", raw_name)
        name = re.sub(r"\s+", " ", name).strip()

        address = (post.get("address") or "").strip()

        postal_m = _POSTAL_RE.search(address)
        postal_code = postal_m.group(1) if postal_m else None

        loc = post.get("location") or {}
        try:
            lat = float(loc["lat"]) if loc.get("lat") else None
            lng = float(loc["lng"]) if loc.get("lng") else None
        except (TypeError, ValueError):
            lat = lng = None

        results.append(Centre(
            url=url,
            name=name,
            address=address,
            postal_code=postal_code,
            lat=lat,
            lng=lng,
        ))

    return results


def run() -> None:
    OUT_PATH.parent.mkdir(exist_ok=True)

    # LV blocks the default session UA — use clean curl_cffi impersonation
    print("Fetching Learning Vision centres page...")
    resp = curl_requests.get(CENTRES_URL, impersonate="chrome136")
    centres = parse_centres(resp.text)

    with_postal = sum(1 for c in centres if c.postal_code)
    print(f"Found {len(centres)} centres ({with_postal} with postal in address text)")

    write_dataset(OUT_PATH, [asdict(c) for c in centres])
    print(f"Saved to {OUT_PATH.stem}-latest.json")


if __name__ == "__main__":
    run()
