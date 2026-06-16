"""
Scrapes all PCF Sparkletots preschool centre pages using their sitemap.
Source: https://www.pcfsparkletots.org.sg/our-preschools-sitemap.xml
robots.txt: only /orientation/ is disallowed. No crawl-delay specified.

Fields extracted: name, postal_code, phone, email, operating_hours,
  principal, programme_type (EY/CC/DS/MOE etc.)

Join key to ecda_centres: postal_code
Output: data/pcf_sparkletots.json
"""
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from scrapers.utils import fetch, make_client, write_dataset

SITEMAP_URL = "https://www.pcfsparkletots.org.sg/our-preschools-sitemap.xml"
CRAWL_DELAY = 2  # seconds; robots.txt has no explicit delay, 2s is conservative
OUT_PATH = Path("data/pcf_sparkletots.json")

_POSTAL_RE = re.compile(r"\b(\d{6})\b")
_PROG_RE = re.compile(r"\(([^)]+)\)\s*$")
_PRINCIPAL_RE = re.compile(r"[Pp]rincipal\s+(.+)")


@dataclass
class Centre:
    url: str
    name: str | None
    postal_code: str | None
    phone: str | None
    email: str | None
    operating_hours: str | None
    principal: str | None
    programme_type: str | None


def get_centre_urls(client: httpx.Client) -> list[str]:
    resp = fetch(client, SITEMAP_URL)
    soup = BeautifulSoup(resp.text, "xml")
    locs = [loc.text.strip() for loc in soup.find_all("loc")]
    return [
        l for l in locs
        if "/our-preschools/" in l
        and not l.endswith((".jpeg", ".jpg", ".png", ".webp", ".gif"))
    ]


def parse_centre(url: str, html: str) -> Centre:
    soup = BeautifulSoup(html, "lxml")

    h1 = soup.select_one("h1") or soup.select_one(".entry-title")
    name = h1.get_text(strip=True) if h1 else None

    prog_m = _PROG_RE.search(name or "")
    programme_type = prog_m.group(1).strip() if prog_m else None

    addr_el = soup.select_one(".s_address")
    addr_text = addr_el.get_text(" ", strip=True) if addr_el else ""
    postal_m = _POSTAL_RE.search(addr_text)
    postal_code = postal_m.group(1) if postal_m else None

    phone_el = soup.select_one(".s_phone") or soup.select_one('a[href^="tel:"]')
    if phone_el:
        digits = re.sub(r"\D", "", phone_el.get_text())
        phone = f"+{digits}" if digits.startswith("65") else f"+65{digits}"
    else:
        phone = None

    email_el = soup.select_one(".s_email") or soup.select_one('a[href^="mailto:"]')
    email = email_el.get_text(strip=True) if email_el else None

    hours_el = soup.select_one(".s_hours")
    if hours_el:
        hours_text = hours_el.get_text(" ", strip=True)
        # Strip the "Operating Hours:" label
        operating_hours = re.sub(r"^Operating Hours:\s*", "", hours_text).strip()
    else:
        operating_hours = None

    principal = None
    for h2 in soup.find_all("h2"):
        m = _PRINCIPAL_RE.search(h2.get_text(strip=True))
        if m:
            principal = m.group(1).strip()
            break

    return Centre(
        url=url,
        name=name,
        postal_code=postal_code,
        phone=phone,
        email=email,
        operating_hours=operating_hours,
        principal=principal,
        programme_type=programme_type,
    )


def run() -> None:
    OUT_PATH.parent.mkdir(exist_ok=True)
    client = make_client()

    print("Fetching centre URLs from sitemap...")
    urls = get_centre_urls(client)
    print(f"Found {len(urls)} centres")

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
    print(f"Saved {len(results)} centres ({matched} with postal code) to {OUT_PATH.stem}-latest.json")
    write_dataset(OUT_PATH, results)


if __name__ == "__main__":
    run()
