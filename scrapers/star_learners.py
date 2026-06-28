"""
Scrapes all Star Learners preschool centre pages.
Source:
  - Slug list: https://www.starlearners.com.sg/wp-json/wp/v2/wpsl_stores?per_page=100
  - Centre pages: https://starlearners.com.sg/our-centres/{slug}/

robots.txt: allows all crawlers. Crawl delay: 2s.

Fields extracted: url, name, address, postal_code,
  fees_citizen_monthly, fees_pr_monthly

Join key to ecda_centres: postal_code
Output: data/star_learners.json
"""
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from scrapers.utils import fetch, make_client, write_dataset

STORES_API = "https://www.starlearners.com.sg/wp-json/wp/v2/wpsl_stores?per_page=100&_fields=slug"
CENTRE_URL = "https://starlearners.com.sg/our-centres/{slug}/"
CRAWL_DELAY = 2
OUT_PATH = Path("data/star_learners.json")

_POSTAL_RE = re.compile(r"Singapore\s+(\d{6})", re.I)


@dataclass
class Centre:
    url: str
    name: str | None
    address: str | None
    postal_code: str | None
    fees_citizen_monthly: int | None
    fees_pr_monthly: int | None


def get_slugs(client) -> list[str]:
    resp = fetch(client, STORES_API)
    return [s["slug"] for s in resp.json() if s.get("slug")]


def _parse_fee(text: str, label: str) -> int | None:
    # Match e.g. "Singaporeans — $650" or "PRs/ Foreigners — $1230"
    # Label is a regex fragment matching the preamble word(s)
    m = re.search(rf"{label}[^$\d]{{0,40}}\$\s*(\d{{3,4}})", text, re.I)
    return int(m.group(1)) if m else None


def parse_centre(url: str, html: str) -> Centre:
    soup = BeautifulSoup(html, "lxml")

    h1 = soup.select_one("h1")
    name = h1.get_text(strip=True) if h1 else None

    addr_el = soup.select_one(".iwt-text")
    address = addr_el.get_text(strip=True) if addr_el else None

    postal_code = None
    if address:
        m = _POSTAL_RE.search(address)
        if m:
            postal_code = m.group(1)

    for t in soup.find_all(["script", "style"]):
        t.decompose()
    text = soup.get_text(" ", strip=True)

    fees_citizen = _parse_fee(text, r"Singaporeans?")
    fees_pr = _parse_fee(text, r"PRs?/\s*Foreigners?")

    return Centre(
        url=url,
        name=name,
        address=address,
        postal_code=postal_code,
        fees_citizen_monthly=fees_citizen,
        fees_pr_monthly=fees_pr,
    )


def run() -> None:
    OUT_PATH.parent.mkdir(exist_ok=True)
    client = make_client()

    print("Fetching Star Learners store list from WP REST API...")
    slugs = get_slugs(client)
    print(f"Found {len(slugs)} stores")

    results: list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Scraping centres", total=len(slugs))

        for i, slug in enumerate(slugs):
            url = CENTRE_URL.format(slug=slug)
            try:
                resp = fetch(client, url)
                centre = parse_centre(url, resp.text)
                results.append(asdict(centre))
            except Exception as e:
                results.append({"url": url, "error": str(e)})

            progress.advance(task)
            if i < len(slugs) - 1:
                time.sleep(CRAWL_DELAY)

    matched = sum(1 for r in results if r.get("postal_code"))
    print(f"Saved {len(results)} centres ({matched} with postal code)")
    write_dataset(OUT_PATH, results)
    print(f"Saved to {OUT_PATH.stem}-latest.json")


if __name__ == "__main__":
    run()
