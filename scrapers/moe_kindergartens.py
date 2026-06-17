"""
Scrapes MOE Kindergarten data from the MOE SchoolFinder Next.js RSC endpoint.
Source: https://www.moe.gov.sg/schoolfinder/moe%20kindergarten
The RSC: 1 header requests the raw component payload instead of the full HTML page,
bypassing Cloudflare's browser challenge. The payload contains all kindergartens
as structured JSON embedded in the RSC stream.
Single HTTP request; no pagination.
Output: data/moe_kindergartens.json
"""
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from scrapers.utils import fetch_plain, write_dataset

URL = "https://www.moe.gov.sg/schoolfinder/moe%20kindergarten"
OUT_PATH = Path("data/moe_kindergartens.json")


@dataclass
class Kindergarten:
    slug: str | None
    name: str | None
    area: str | None
    address: str | None
    postal_code: str | None
    phone: str | None
    email: str | None
    website: str | None
    active: bool
    is_enrolling: bool


def _extract_schools(text: str) -> list[dict]:
    decoder = json.JSONDecoder()
    idx = text.find('"schools":')
    if idx < 0:
        return []
    arr_start = text.index('[', idx)
    try:
        schools, _ = decoder.raw_decode(text, arr_start)
        return schools if isinstance(schools, list) else []
    except json.JSONDecodeError:
        return []


def _parse(raw: dict) -> Kindergarten:
    area_obj = raw.get("school_area") or {}
    return Kindergarten(
        slug=raw.get("slug"),
        name=raw.get("school_name"),
        area=area_obj.get("name") if isinstance(area_obj, dict) else None,
        address=raw.get("school_address"),
        postal_code=raw.get("school_address_postal_code"),
        phone=raw.get("school_telephone_number"),
        email=raw.get("school_email"),
        website=raw.get("school_website_url"),
        active=bool(raw.get("school_active")),
        is_enrolling=bool(raw.get("is_enrolling")),
    )


def run() -> None:
    OUT_PATH.parent.mkdir(exist_ok=True)

    print("Fetching MOE SchoolFinder RSC payload...")
    text = fetch_plain(URL, headers={"RSC": "1"})

    raw_schools = _extract_schools(text)
    if not raw_schools:
        raise RuntimeError("Could not find schools data — RSC payload format may have changed")

    results = [asdict(_parse(s)) for s in raw_schools]
    write_dataset(OUT_PATH, results)
    matched = sum(1 for r in results if r.get("postal_code"))
    print(f"Saved {len(results)} kindergartens ({matched} with postal code)")


if __name__ == "__main__":
    run()
