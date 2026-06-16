"""
Scrapes all E-Bridge Pre-School location pages.
Source: https://www.e-bridge.edu.sg/directory/ (index) + /locations/{slug}/ (detail)
robots.txt: allows all crawlers, no crawl-delay specified; using 2s to be polite.
Output: data/ebridge.json
"""
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from scrapers.utils import fetch, make_client, write_dataset

DIRECTORY_URL = "https://www.e-bridge.edu.sg/directory/"
CRAWL_DELAY = 2
OUT_PATH = Path("data/ebridge.json")

_POSTAL_RE = re.compile(r"SINGAPORE\s+(\d{6})", re.I)


def _decode_cf_email(enc: str) -> str:
    key = int(enc[:2], 16)
    return "".join(chr(int(enc[i : i + 2], 16) ^ key) for i in range(2, len(enc), 2))


@dataclass
class Centre:
    url: str
    name: str | None
    address: str | None
    postal_code: str | None
    operating_hours: str | None
    phone: str | None
    email: str | None


def get_location_urls(client: httpx.Client) -> list[str]:
    resp = fetch(client, DIRECTORY_URL)
    soup = BeautifulSoup(resp.text, "lxml")
    return sorted({
        str(a["href"])
        for a in soup.find_all("a", href=True)
        if "/locations/" in str(a["href"])
    })


def parse_location(url: str, html: str) -> Centre:
    soup = BeautifulSoup(html, "lxml")

    h1 = soup.select_one("h1")
    raw_name = h1.get_text(strip=True) if h1 else None
    # Strip brand prefix: "E-Bridge Pre-School" followed by the location name
    name = re.sub(r"^E-Bridge Pre-School\s*", "", raw_name or "").strip() or raw_name

    # Location contact is in the FIRST elementor-icon-list--layout-traditional
    # (the second one is the head office footer)
    icon_lists = soup.select(".elementor-icon-list--layout-traditional")
    location_list = icon_lists[0] if icon_lists else None

    address = postal_code = operating_hours = phone = email = None

    if location_list:
        items = location_list.select(".elementor-icon-list-item")
        for item in items:
            text = item.get_text(" ", strip=True)

            if _POSTAL_RE.search(text):
                address = text
                m = _POSTAL_RE.search(text)
                if m:
                    postal_code = m.group(1)

            elif any(day in text for day in ("Monday", "Tuesday", "Mondays", "Friday", "7am", "7pm")):
                operating_hours = text

            elif re.search(r"\+65|\b6\d{7}\b|\b8\d{7}\b|\b9\d{7}\b", text):
                digits = re.sub(r"[^\d]", "", text)
                if digits:
                    phone = f"+{digits}" if digits.startswith("65") else f"+65{digits}"

        # CF-protected email
        for cf in location_list.select(".__cf_email__"):
            enc = cf.get("data-cfemail")
            if isinstance(enc, str) and enc:
                email = _decode_cf_email(enc)
                break

    return Centre(
        url=url,
        name=name,
        address=address,
        postal_code=postal_code,
        operating_hours=operating_hours,
        phone=phone,
        email=email,
    )


def run() -> None:
    OUT_PATH.parent.mkdir(exist_ok=True)
    client = make_client()

    print("Fetching E-Bridge location index...")
    urls = get_location_urls(client)
    print(f"Found {len(urls)} locations")

    results: list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Scraping locations", total=len(urls))

        for i, url in enumerate(urls):
            try:
                resp = fetch(client, url)
                centre = parse_location(url, resp.text)
                results.append(asdict(centre))
            except Exception as e:
                results.append({"url": url, "error": str(e)})

            progress.advance(task)

            if i < len(urls) - 1:
                time.sleep(CRAWL_DELAY)

    matched = sum(1 for r in results if r.get("postal_code"))
    print(f"Saved {len(results)} locations ({matched} with postal code)")
    write_dataset(OUT_PATH, results)


if __name__ == "__main__":
    run()
