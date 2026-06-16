"""
Scrapes all M.Y World Preschool centre listings.
Source: https://myworld.org.sg/our-centres/ (all centres on a single page)
robots.txt: Content-Signal based AI policy; public factual directory.
No crawl-delay. Centres appear twice (region tabs + Show All); deduplicated by postal_code.
Output: data/my_world_preschool.json
"""
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from scrapers.utils import fetch, make_client, write_dataset

URL = "https://myworld.org.sg/our-centres/"
OUT_PATH = Path("data/my_world_preschool.json")

_POSTAL_RE = re.compile(r"S\((\d{6})\)")
_PHONE_CLEAN_RE = re.compile(r"[^\d+]")


def _decode_cf_email(enc: str) -> str:
    key = int(enc[:2], 16)
    return "".join(chr(int(enc[i : i + 2], 16) ^ key) for i in range(2, len(enc), 2))


@dataclass
class Centre:
    name: str | None
    address: str | None
    postal_code: str | None
    phone: str | None
    email: str | None


def _parse_card(wrapper: Tag) -> Centre:
    lines = [l.strip() for l in wrapper.get_text("\n", strip=True).split("\n") if l.strip()]

    name = next((l for l in lines if l != "*"), None)

    address = None
    postal_code = None
    for l in lines:
        m = _POSTAL_RE.search(l)
        if m:
            postal_code = m.group(1)
            address = l
            break

    phone = None
    for l in lines:
        if l.startswith("Tel:"):
            digits = _PHONE_CLEAN_RE.sub("", l[4:])
            if digits:
                phone = f"+65{digits}" if not digits.startswith("65") else f"+{digits}"
            break

    email = None
    for cf in wrapper.select(".__cf_email__"):
        enc = cf.get("data-cfemail")
        if isinstance(enc, str) and enc:
            email = _decode_cf_email(enc)
            break

    return Centre(name=name, address=address, postal_code=postal_code, phone=phone, email=email)


def run() -> None:
    OUT_PATH.parent.mkdir(exist_ok=True)
    client = make_client()

    print("Fetching M.Y World Preschool centres page...")
    resp = fetch(client, URL)
    soup = BeautifulSoup(resp.text, "lxml")

    seen: set[str] = set()
    results: list[dict] = []

    for wrapper in soup.find_all("div", class_="wpb_wrapper"):
        text = wrapper.get_text()
        if "Tel:" not in text or not _POSTAL_RE.search(text):
            continue
        if len(text) > 600:
            continue

        centre = _parse_card(wrapper)
        if not centre.postal_code or centre.postal_code in seen:
            continue
        seen.add(centre.postal_code)
        results.append(asdict(centre))

    write_dataset(OUT_PATH, results)
    matched = sum(1 for r in results if r.get("postal_code"))
    print(f"Saved {len(results)} centres ({matched} with postal code)")


if __name__ == "__main__":
    run()
