"""
Scrapes all My First Skool centre pages using their published sitemap.
robots.txt: allows all crawlers, crawl-delay 10s.
Output: data/myfirstskool.json
"""
import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict

import httpx
from bs4 import BeautifulSoup
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

from scrapers.utils import make_client, fetch

SITEMAP_URL = "https://www.myfirstskool.com/centre-sitemap.xml"
CRAWL_DELAY = 10  # seconds, as specified in robots.txt
OUT_PATH = Path("data/myfirstskool.json")


@dataclass
class Centre:
    url: str
    name: str | None
    address: str | None
    postal_code: str | None
    phone: str | None
    principal: str | None
    programmes: list[str]
    operating_hours: str | None
    spark_accredited: bool
    year_established: str | None
    mother_tongue: list[str]


def get_centre_urls(client: httpx.Client) -> list[str]:
    resp = fetch(client, SITEMAP_URL)
    soup = BeautifulSoup(resp.text, "xml")
    return [loc.text.strip() for loc in soup.find_all("loc")]


def parse_centre(url: str, html: str) -> Centre:
    import re

    soup = BeautifulSoup(html, "lxml")
    details = soup.select_one("#centre-details")

    # Name: first h2 on the page is the centre name (no h1 present)
    h2_first = soup.select_one("h2")
    name = h2_first.get_text(strip=True) if h2_first else None

    # Address: the <span> inside the address sub-block of #centre-details
    address_span = None
    if details:
        for span_label in details.select("span.text-lg.font-700"):
            if span_label.get_text(strip=True) == "Address":
                address_span = span_label.find_next_sibling("span")
                break
    raw_address = " ".join(address_span.get_text(" ", strip=True).split()) if address_span else None

    # Postal code: trailing 6-digit number in address
    postal_code = None
    if raw_address:
        m = re.search(r"\b(\d{6})\b", raw_address)
        if m:
            postal_code = m.group(1)

    # Phone: first tel: link
    phone_el = soup.select_one('a[href^="tel:"]')
    if phone_el:
        phone = re.sub(r"\s+", "", phone_el.get_text())
        phone = re.sub(r"\(.*\)", "", phone).strip()  # strip "(Hotline)" suffix
    else:
        phone = None

    # Principal: name is in span.text-sm.font-700 inside .designation-info
    principal = None
    principal_section = soup.select_one(".principal-message")
    if principal_section:
        name_span = principal_section.select_one(".designation-info span.font-700")
        if name_span:
            principal = name_span.get_text(strip=True)

    # Programmes: list items inside the Centre Type block
    programmes: list[str] = []
    if details:
        for span_label in details.select("span.text-lg.font-700"):
            if span_label.get_text(strip=True) == "Centre type":
                ul = span_label.find_next_sibling("ul")
                if ul:
                    programmes = [li.get_text(strip=True) for li in ul.find_all("li")]
                break

    # Operating hours: the <li> items inside Operating hours block
    operating_hours = None
    if details:
        for span_label in details.select("span.text-lg.font-700"):
            if span_label.get_text(strip=True) == "Operating hours":
                ul = span_label.find_next_sibling("ul")
                if ul:
                    parts = []
                    for li in ul.find_all("li"):
                        parts.append(" ".join(li.get_text(" ", strip=True).split()))
                    operating_hours = "; ".join(parts)
                break

    # Mother tongue: <span class="text-xs"> inside Mother Tongue block
    mother_tongue: list[str] = []
    if details:
        for span_label in details.select("span.text-lg.font-700"):
            if span_label.get_text(strip=True) == "Mother Tongue":
                ul = span_label.find_next_sibling("ul")
                if ul:
                    mother_tongue = [s.get_text(strip=True) for s in ul.select("span.text-xs")]
                break

    # SPARK accreditation: look for the word SPARK anywhere in the page
    spark_accredited = bool(soup.find(string=re.compile(r"SPARK", re.I)))

    # Year established: look for "began in YYYY" or "Since YYYY" in principal section
    year_established = None
    if principal_section:
        text = principal_section.get_text()
        m = re.search(r"began in (\d{4})|[Ss]ince (\d{4})|[Ee]stablished.*?(\d{4})", text)
        if m:
            year_established = next(g for g in m.groups() if g)

    return Centre(
        url=url,
        name=name,
        address=raw_address,
        postal_code=postal_code,
        phone=phone,
        principal=principal,
        programmes=programmes,
        operating_hours=operating_hours,
        spark_accredited=spark_accredited,
        year_established=year_established,
        mother_tongue=mother_tongue,
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

            # Respect crawl-delay for all but the last request
            if i < len(urls) - 1:
                time.sleep(CRAWL_DELAY)

    OUT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"Saved {len(results)} centres to {OUT_PATH}")


if __name__ == "__main__":
    run()
