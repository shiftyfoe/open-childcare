"""Generate slim JSON for the GitHub Pages site from merged-latest.json."""

import json
from pathlib import Path


def _vacancy(v: str) -> str:
    if v == "Available":
        return "A"
    if v == "Full":
        return "F"
    return "N"


def run() -> None:
    src = Path("data/merged-latest.json")
    dst = Path("docs/data/centres.json")
    dst.parent.mkdir(parents=True, exist_ok=True)

    data: list[dict] = json.loads(src.read_text())

    slim = []
    for c in data:
        slim.append(
            {
                "id": c.get("centre_code", ""),
                "n": c.get("centre_name", ""),
                "o": c.get("organisation_description", ""),
                "sm": c.get("service_model", ""),
                "a": c.get("centre_address", ""),
                "p": str(c.get("postal_code", "")),
                "ph": c.get("centre_contact_no") or c.get("contactno_lifesg") or "",
                "w": c.get("centre_website") or c.get("website_lifesg") or "",
                "sp": 1 if c.get("spark_certified") == "Yes" else 0,
                "eoh": 1 if c.get("extended_operating_hours") == "Yes" else 0,
                "tr": 1 if c.get("provision_of_transport") == "Yes" else 0,
                "wh": c.get("weekday_full_day") or "",
                "sh": c.get("saturday") or "",
                "fo": c.get("food_offered") or "",
                "l2": c.get("second_languages_offered") or "",
                "lat": c.get("lat"),
                "lng": c.get("lng"),
                "fi": c.get("fee_ceiling_infant"),
                "fn": c.get("fee_ceiling_non_infant"),
                "vi": _vacancy(c.get("infant_vacancy_current_month", "")),
                "vpg": _vacancy(c.get("pg_vacancy_current_month", "")),
                "vn1": _vacancy(c.get("n1_vacancy_current_month", "")),
                "vn2": _vacancy(c.get("n2_vacancy_current_month", "")),
                "vk1": _vacancy(c.get("k1_vacancy_current_month", "")),
                "vk2": _vacancy(c.get("k2_vacancy_current_month", "")),
            }
        )

    dst.write_text(json.dumps(slim, separators=(",", ":")))
    print(f"Exported {len(slim)} centres → {dst} ({dst.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    run()
