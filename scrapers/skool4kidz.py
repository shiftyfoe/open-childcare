"""
Scrapes all Skool4Kidz centre pages via the page sitemap.
Source: https://skool4kidz.com.sg/page-sitemap.xml → /our-centres/{slug}/
robots.txt: allows all crawlers, no crawl-delay; using 2s to be polite.
Fields: name (h1), address, postal_code (.fusion-content-boxes first box).
Output: data/skool4kidz.json
"""
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from scrapers.utils import fetch, make_client, write_dataset

SITEMAP_URL = "https://skool4kidz.com.sg/page-sitemap.xml"
CRAWL_DELAY = 2
OUT_PATH = Path("data/skool4kidz.json")

_POSTAL_RE = re.compile(r"Singapore\s*[\(\s](\d{6})[\)\s]?", re.I)


@dataclass
class Centre:
    url: str
    name: str | None
    address: str | None
    postal_code: str | None


def get_centre_urls(client: httpx.Client) -> list[str]:
    resp = fetch(client, SITEMAP_URL)
    soup = BeautifulSoup(resp.text, "xml")
    return [
        loc.text.strip()
        for loc in soup.find_all("loc")
        if re.search(r"/our-centres/[^/]+/?$", loc.text)
    ]


def parse_centre(url: str, html: str) -> Centre:
    soup = BeautifulSoup(html, "lxml")

    h1 = soup.select_one("h1")
    name = h1.get_text(strip=True) if h1 else None

    address = postal_code = None
    for box in soup.select(".fusion-content-boxes"):
        text = box.get_text(" ", strip=True)
        if "Singapore" in text and len(text) < 400:
            address = " ".join(text.split())
            m = _POSTAL_RE.search(address)
            if m:
                postal_code = m.group(1)
            break

    return Centre(url=url, name=name, address=address, postal_code=postal_code)


def run() -> None:
    OUT_PATH.parent.mkdir(exist_ok=True)
    client = make_client()

    print("Fetching Skool4Kidz page sitemap...")
    urls = get_centre_urls(client)
    print(f"Found {len(urls)} centre pages")

    results: list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Scraping centres", total=len(urls))

        for i, url in enumerate(urls):
            try:
                resp = fetch(client, url)
                centre = parse_centre(url, resp.text)
                results.append(asdict(centre))
            except Exception as e:
                results.append({"url": url, "error": str(e)})

            progress.advance(task)

            if i < len(urls) - 1:
                time.sleep(CRAWL_DELAY)

    matched = sum(1 for r in results if r.get("postal_code"))
    print(f"Saved {len(results)} centres ({matched} with postal code)")
    write_dataset(OUT_PATH, results)


if __name__ == "__main__":
    run()
