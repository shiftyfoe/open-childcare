"""
Scrapes the ECDA upcoming preschools table (static HTML, no JS needed).
Source: https://www.ecda.gov.sg/parents/preschool-search/upcoming-preschools
Output: data/ecda_upcoming.json
"""
import json
from pathlib import Path

from bs4 import BeautifulSoup

from scrapers.utils import make_client, fetch, write_dataset

URL = "https://www.ecda.gov.sg/parents/preschool-search/upcoming-preschools"
OUT_PATH = Path("data/ecda_upcoming.json")


def parse_table(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        raise ValueError("No table found on page")

    all_rows = table.find_all("tr")
    if not all_rows:
        raise ValueError("Table has no rows")

    # First row is the header (no <thead>, all inside <tbody>)
    headers = [
        cell.get_text(" ", strip=True).lower().replace(" ", "_")
        for cell in all_rows[0].find_all(["td", "th"])
    ]

    rows = []
    for tr in all_rows[1:]:
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def run() -> None:
    OUT_PATH.parent.mkdir(exist_ok=True)
    client = make_client()

    print(f"Fetching {URL}")
    try:
        resp = fetch(client, URL)
        rows = parse_table(resp.text)
    except Exception as e:
        cached = OUT_PATH.parent / f"{OUT_PATH.stem}-latest.json"
        if cached.exists():
            print(f"WARNING: fetch failed ({e}) — reusing cached data from {cached.name}")
            rows = json.loads(cached.read_text())
        else:
            raise

    write_dataset(OUT_PATH, rows)
    print(f"Saved {len(rows)} upcoming preschools to {OUT_PATH.parent}/{OUT_PATH.stem}-latest.json")


if __name__ == "__main__":
    run()
