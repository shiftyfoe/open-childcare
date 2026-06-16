"""
Scrapes MOE Kindergarten data from the MOE SchoolFinder page.
Source: https://www.moe.gov.sg/schoolfinder/moe%20kindergarten
All kindergartens are embedded in the page's Next.js RSC payload as structured JSON.
Single HTTP request; no pagination.
Output: data/moe_kindergartens.json
"""
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from scrapers.utils import fetch, make_client, write_dataset

URL = "https://www.moe.gov.sg/schoolfinder/moe%20kindergarten"
OUT_PATH = Path("data/moe_kindergartens.json")

_PUSH_RE = re.compile(r"self\.__next_f\.push\(\[(\d+),(\")", re.DOTALL)


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


def _extract_schools(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    decoder = json.JSONDecoder()

    for script in soup.find_all("script"):
        text = script.string or ""
        if "school_name" not in text:
            continue

        # The data is inside self.__next_f.push([N, "...RSC payload..."])
        # Use JSONDecoder.raw_decode to properly parse the string argument
        for m in _PUSH_RE.finditer(text):
            str_start = m.start(2)
            try:
                payload, _ = decoder.raw_decode(text, str_start)
            except json.JSONDecodeError:
                continue

            if not isinstance(payload, str) or "school_name" not in payload:
                continue

            # Within the RSC payload, find and decode the schools JSON array
            idx = payload.find('"schools":')
            if idx < 0:
                continue
            arr_start = payload.index("[", idx)
            try:
                schools, _ = decoder.raw_decode(payload, arr_start)
            except json.JSONDecodeError:
                continue

            if isinstance(schools, list) and schools:
                return schools

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
    client = make_client()

    print("Fetching MOE SchoolFinder page...")
    resp = fetch(client, URL)

    raw_schools = _extract_schools(resp.text)
    if not raw_schools:
        raise RuntimeError("Could not find schools data in page — RSC payload format may have changed")

    results = [asdict(_parse(s)) for s in raw_schools]
    write_dataset(OUT_PATH, results)
    matched = sum(1 for r in results if r.get("postal_code"))
    print(f"Saved {len(results)} kindergartens ({matched} with postal code)")


if __name__ == "__main__":
    run()
