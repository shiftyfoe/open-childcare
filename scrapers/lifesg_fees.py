"""
Fetches estimated fee ranges per centre per preschool level from LifeSG.
API: https://www.life.gov.sg/coordinator/api/resources/v1
No auth required. robots.txt: preschool-search path not blocked.

Strategy: iterate over search terms (a-z + common words) × 6 levels,
paginate at 10/page, deduplicate by (centre_code, level).
The join key to ecda_centres.json is centre_code == LifeSG id field.

Output: data/lifesg_fees.json
"""
import re
import time
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.console import Console

from scrapers.utils import make_client, fetch, write_dataset

API_URL = "https://www.life.gov.sg/coordinator/api/resources/v1"
OUT_PATH = Path("data/lifesg_fees.json")
CRAWL_DELAY = 0.3  # seconds between requests

LEVELS = ["IC", "PG", "N1", "N2", "K1", "K2"]

# Search terms chosen to maximise coverage of Singapore preschool names.
# "a" alone hits ~1250 of ~1800 N1 centres. Common words cover the rest.
SEARCH_TERMS = list("abcdefghijklmnopqrstuvwxyz") + ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]

HEADERS = {
    "accept": "application/json",
    "referer": "https://www.life.gov.sg/listing/preschool/results",
}

FEE_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)\s*(?:-\s*\$([\d,]+(?:\.\d+)?))?")


def parse_fee(description: str | None) -> dict:
    """Extract fee_min and fee_max (SGD) from the markdown description string."""
    if not description:
        return {"fee_min": None, "fee_max": None}
    m = FEE_RE.search(description)
    if not m:
        return {"fee_min": None, "fee_max": None}
    fee_min = float(m.group(1).replace(",", ""))
    fee_max = float(m.group(2).replace(",", "")) if m.group(2) else fee_min
    return {"fee_min": fee_min, "fee_max": fee_max}


def fetch_page(client, term: str, level: str, page: int) -> dict:
    params = (
        f"serviceId=preschool&tabType=centreName"
        f"&centreName={term}&preschoolLevel={level}"
        f"&preschoolEnrolmentMonth=0&page={page}&limit=10"
    )
    resp = fetch(client, f"{API_URL}?{params}", )
    return resp.json()


def validate_response(data: dict, term: str, level: str, page: int) -> list[str]:
    warnings = []
    if "data" not in data:
        warnings.append(f"missing 'data' key for term={term} level={level} page={page}")
        return warnings
    d = data["data"]
    if "resources" not in d:
        warnings.append(f"missing 'resources' key for term={term} level={level} page={page}")
    if d.get("totalRows", 0) > 0 and not d.get("resources"):
        warnings.append(f"totalRows={d['totalRows']} but empty resources for term={term} level={level} page={page}")
    return warnings


def run() -> None:
    OUT_PATH.parent.mkdir(exist_ok=True)
    client = make_client()
    console = Console()

    # (centre_code, level) → fee dict
    seen: dict[tuple[str, str], dict] = {}
    warn_log: list[str] = []
    api_errors = 0

    total_combos = len(SEARCH_TERMS) * len(LEVELS)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
    ) as progress:
        combo_task = progress.add_task("Search combos", total=total_combos)

        for level in LEVELS:
            for term in SEARCH_TERMS:
                page = 1
                while True:
                    try:
                        data = fetch_page(client, term, level, page)
                    except Exception as e:
                        warn_log.append(f"Request error term={term} level={level} page={page}: {e}")
                        api_errors += 1
                        break

                    warnings = validate_response(data, term, level, page)
                    warn_log.extend(warnings)

                    if "data" not in data:
                        break

                    d = data["data"]
                    resources = d.get("resources", [])

                    for r in resources:
                        centre_code = r.get("id")
                        if not centre_code:
                            warn_log.append(f"Resource missing id: {r.get('title')} term={term} level={level}")
                            continue
                        key = (centre_code, level)
                        if key not in seen:
                            seen[key] = {
                                "centre_code": centre_code,
                                "centre_name": r.get("title"),
                                "level": level,
                                **parse_fee(r.get("description")),
                            }

                    total_pages = d.get("totalPages", 0)
                    if page >= total_pages or not resources:
                        break

                    page += 1
                    time.sleep(CRAWL_DELAY)

                progress.advance(combo_task)
                time.sleep(CRAWL_DELAY)

    results = list(seen.values())

    if not results:
        raise RuntimeError("No fee records collected — API may have changed structure")

    unique_centres = len({r["centre_code"] for r in results})
    console.print(f"\n[green]Collected {len(results)} (centre, level) fee records[/green]")
    console.print(f"Unique centres: {unique_centres}")
    console.print(f"API errors: {api_errors}")

    if warn_log:
        console.print(f"[yellow]{len(warn_log)} warnings — see data/lifesg_fees_warnings.txt[/yellow]")
        Path("data/lifesg_fees_warnings.txt").write_text("\n".join(warn_log))

    write_dataset(OUT_PATH, results)
    console.print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    run()
