"""
Scrapes all Skool4Kidz centre pages via the WordPress REST API.
Source: https://skool4kidz.com.sg/wp-json/wp/v2/pages?parent=157 (our-centres child pages)
Uses stdlib urllib to avoid curl_cffi TLS fingerprint blocked by site's Cloudflare config.
Addresses are in fusion-content-boxes with format "Blk N St Name S(XXXXXX)".
robots.txt: allows all crawlers, no crawl-delay; using 2s to be polite.
Output: data/skool4kidz.json
"""
import json
import re
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from scrapers.utils import fetch_plain, write_dataset

WP_API = "https://skool4kidz.com.sg/wp-json/wp/v2/pages"
CENTRES_PARENT_ID = 157
CRAWL_DELAY = 2
OUT_PATH = Path("data/skool4kidz.json")

# Matches both "Singapore (570533)" and "S(570533)"
_POSTAL_RE = re.compile(r"(?:Singapore\s*[\(\s]|S\()(\d{6})\)?", re.I)


@dataclass
class Centre:
    url: str
    name: str | None
    address: str | None
    postal_code: str | None


def get_centre_urls() -> list[str]:
    urls = []
    page = 1
    while True:
        req = urllib.request.Request(
            f"{WP_API}?parent={CENTRES_PARENT_ID}&per_page=100&page={page}&_fields=link",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        if not data:
            break
        urls.extend(r["link"] for r in data)
        if len(data) < 100:
            break
        page += 1
    return urls


def parse_centre(url: str, html: str) -> Centre:
    soup = BeautifulSoup(html, "lxml")

    h1 = soup.select_one("h1")
    name = h1.get_text(strip=True) if h1 else None

    address = postal_code = None
    for box in soup.select(".fusion-content-boxes"):
        text = box.get_text(" ", strip=True)
        m = _POSTAL_RE.search(text)
        if m and len(text) < 400:
            postal_code = m.group(1)
            address = " ".join(text.split())
            break

    return Centre(url=url, name=name, address=address, postal_code=postal_code)


def run() -> None:
    OUT_PATH.parent.mkdir(exist_ok=True)

    print("Fetching Skool4Kidz centre list from WP REST API...")
    urls = get_centre_urls()
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
                html = fetch_plain(url)
                centre = parse_centre(url, html)
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
