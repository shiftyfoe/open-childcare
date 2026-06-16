"""
Fetches the official ECDA childcare centre dataset from data.gov.sg.
Dataset: d_696c994c50745b079b3684f0e90ffc53
API: https://data.gov.sg/api/action/datastore_search
No authentication required. Open data, updated daily by ECDA.

Fields captured (65 total):
  Centre info: tp_code, centre_code, centre_name, organisation_code,
    organisation_description, service_model, centre_contact_no,
    centre_email_address, centre_address, postal_code, centre_website,
    contactno_lifesg, emailaddress_lifesg, website_lifesg
  Vacancies (current + next 6 months) per level: infant, pg, n1, n2, k1, k2
    Values: "Available" | "Full" | "Not Applicable"
  Features: food_offered, second_languages_offered, spark_certified,
    weekday_full_day, saturday, extended_operating_hours, provision_of_transport
  Admin: scheme_type, government_subsidy, gst_regisration, last_updated, remarks

Output: data/ecda_centres.json
"""
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

from scrapers.utils import make_client, fetch, write_dataset

RESOURCE_ID = "d_696c994c50745b079b3684f0e90ffc53"
API_BASE = "https://data.gov.sg/api/action/datastore_search"
PAGE_SIZE = 100
OUT_PATH = Path("data/ecda_centres.json")

_VACANCY_LEVELS = ("infant", "pg", "n1", "n2", "k1", "k2")
_VACANCY_MONTHS = ("current_month", "next_month", "third_month", "fourth_month", "fifth_month", "sixth_month", "seventh_month")

EXPECTED_FIELDS = {
    "tp_code", "centre_code", "centre_name", "organisation_code",
    "organisation_description", "service_model", "centre_contact_no",
    "centre_email_address", "centre_address", "postal_code", "centre_website",
    "food_offered", "second_languages_offered", "spark_certified",
    "weekday_full_day", "saturday", "scheme_type", "extended_operating_hours",
    "provision_of_transport", "government_subsidy", "gst_regisration",
    "last_updated", "remarks", "contactno_lifesg", "emailaddress_lifesg", "website_lifesg",
    *{f"{level}_vacancy_{month}" for level in _VACANCY_LEVELS for month in _VACANCY_MONTHS},
}


def validate_record(record: dict) -> list[str]:
    warnings = []
    if not record.get("centre_code"):
        warnings.append("missing centre_code")
    if not record.get("centre_name"):
        warnings.append("missing centre_name")
    if not record.get("postal_code"):
        warnings.append("missing postal_code")
    if not record.get("last_updated"):
        warnings.append("missing last_updated")
    return warnings


def run() -> None:
    OUT_PATH.parent.mkdir(exist_ok=True)
    client = make_client()

    # First request to get total count
    resp = fetch(client, f"{API_BASE}?resource_id={RESOURCE_ID}&limit=1")
    payload = resp.json()

    if not payload.get("success"):
        raise RuntimeError(f"API error: {payload.get('error', payload)}")

    total = payload["result"]["total"]
    print(f"Total records: {total}")

    if total == 0:
        raise RuntimeError("API returned 0 records — page structure may have changed")

    # Validate field names match expectations
    result_fields = {f["id"] for f in payload["result"].get("fields", [])}
    missing = EXPECTED_FIELDS - result_fields
    if missing:
        print(f"WARNING: expected fields missing from API response: {missing}")
        print("The dataset schema may have changed. Proceeding with available fields.")

    records: list[dict] = []
    warn_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Fetching records", total=total)

        offset = 0
        while offset < total:
            url = f"{API_BASE}?resource_id={RESOURCE_ID}&limit={PAGE_SIZE}&offset={offset}"
            resp = fetch(client, url)
            payload = resp.json()

            if not payload.get("success"):
                raise RuntimeError(f"API error at offset {offset}: {payload.get('error')}")

            batch = payload["result"]["records"]
            if not batch:
                print(f"\nWARNING: empty batch at offset {offset}, stopping early")
                break

            for rec in batch:
                warnings = validate_record(rec)
                if warnings:
                    warn_count += 1
                records.append(rec)

            progress.advance(task, len(batch))
            offset += PAGE_SIZE

    if len(records) == 0:
        raise RuntimeError("No records fetched — something went wrong")

    if len(records) < total * 0.9:
        print(f"WARNING: only fetched {len(records)}/{total} records (< 90%). Data may be incomplete.")

    print(f"\nFetched {len(records)} records ({warn_count} with validation warnings)")
    write_dataset(OUT_PATH, records)
    print(f"Saved to {OUT_PATH.parent}/{OUT_PATH.stem}-latest.json")


if __name__ == "__main__":
    run()
