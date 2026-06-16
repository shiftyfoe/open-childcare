"""
Merges all scraped datasets into a single denormalized file.

Spine: ecda_centres.json (one record per licensed centre)
  + lifesg_fees.json    → joined on centre_code; added as nested fees: {IC: {min, max}, …}
  + myfirstskool.json   → joined on postal_code; added as mfs_* fields
  + pcf_sparkletots.json → joined on postal_code; added as pcf_* fields
  + geocoded.json       → joined on postal_code; added as lat/lng fields

Static enrichment:
  + MSF fee ceilings    → derived from scheme_type (Anchor/Partner Operator caps)

ecda_upcoming.json contains future centres not yet in the spine and is left separate.

Output: data/merged.json
"""
import json
from pathlib import Path

from scrapers.utils import write_dataset

CENTRES_PATH = Path("data/ecda_centres-latest.json")
FEES_PATH = Path("data/lifesg_fees-latest.json")
MFS_PATH = Path("data/myfirstskool-latest.json")
PCF_PATH = Path("data/pcf_sparkletots-latest.json")
GEOCODED_PATH = Path("data/geocoded-latest.json")
OUT_PATH = Path("data/merged.json")

# MSF fee ceilings (SGD/month, before subsidy) by scheme_type and level group.
# Source: MSF/ECDA fee cap guidelines. Verify at msf.gov.sg before updating.
# Last verified: 2024. Anchor caps: infant S$1,370, non-infant S$800.
# Partner and private operators set their own fees; no cap applies.
_FEE_CEILINGS: dict[str, dict] = {
    "Anchor Operator Scheme": {"infant": 1370, "non_infant": 800},
    "Partner Operator Scheme": {"infant": None, "non_infant": None},
    "na": {"infant": None, "non_infant": None},
}

MFS_FIELDS = ("url", "name", "principal", "programmes", "operating_hours",
              "spark_accredited", "year_established", "mother_tongue")

PCF_FIELDS = ("url", "name", "principal", "programme_type", "operating_hours",
              "phone", "email")


def load(path: Path) -> list[dict]:
    if not path.exists():
        print(f"WARNING: {path} not found — skipping")
        return []
    with open(path) as f:
        return json.load(f)


def build_fees_index(fees: list[dict]) -> dict[str, dict]:
    """centre_code → {level: {min, max}}"""
    index: dict[str, dict] = {}
    for row in fees:
        code = row.get("centre_code")
        level = row.get("level")
        if not code or not level:
            continue
        index.setdefault(code, {})[level] = {
            "min": row.get("fee_min"),
            "max": row.get("fee_max"),
        }
    return index


def build_postal_index(records: list[dict]) -> dict[str, dict]:
    """postal_code → record (last writer wins on collision)"""
    index: dict[str, dict] = {}
    for row in records:
        postal = row.get("postal_code")
        if postal:
            index[postal] = row
    return index


def build_geocode_index(records: list[dict]) -> dict[str, dict]:
    """postal_code → {lat, lng}"""
    index: dict[str, dict] = {}
    for row in records:
        postal = row.get("postal_code")
        if postal:
            index[postal] = row
    return index


def fee_ceilings_for(scheme_type: str) -> dict:
    caps = _FEE_CEILINGS.get(scheme_type, {"infant": None, "non_infant": None})
    return {
        "fee_ceiling_infant": caps["infant"],
        "fee_ceiling_non_infant": caps["non_infant"],
    }


def run() -> None:
    centres = load(CENTRES_PATH)
    if not centres:
        raise RuntimeError(f"{CENTRES_PATH} is required but missing")

    fees_index = build_fees_index(load(FEES_PATH))
    mfs_index = build_postal_index(load(MFS_PATH))
    pcf_index = build_postal_index(load(PCF_PATH))
    geo_index = build_geocode_index(load(GEOCODED_PATH))

    merged: list[dict] = []
    fees_matched = mfs_matched = pcf_matched = geo_matched = 0

    for centre in centres:
        record = dict(centre)

        code = centre.get("centre_code", "")
        if code in fees_index:
            record["fees"] = fees_index[code]
            fees_matched += 1
        else:
            record["fees"] = None

        postal = centre.get("postal_code", "")

        mfs = mfs_index.get(postal)
        if mfs:
            for field in MFS_FIELDS:
                record[f"mfs_{field}"] = mfs.get(field)
            mfs_matched += 1
        else:
            for field in MFS_FIELDS:
                record[f"mfs_{field}"] = None

        pcf = pcf_index.get(postal)
        if pcf:
            for field in PCF_FIELDS:
                record[f"pcf_{field}"] = pcf.get(field)
            pcf_matched += 1
        else:
            for field in PCF_FIELDS:
                record[f"pcf_{field}"] = None

        geo = geo_index.get(postal)
        if geo:
            record["lat"] = geo.get("lat")
            record["lng"] = geo.get("lng")
            geo_matched += 1
        else:
            record["lat"] = None
            record["lng"] = None

        record.update(fee_ceilings_for(centre.get("scheme_type", "na")))

        merged.append(record)

    print(f"Centres:             {len(merged)}")
    print(f"Fees joined:         {fees_matched}/{len(merged)}")
    print(f"MFS joined:          {mfs_matched}/{len(merged)}")
    print(f"PCF joined:          {pcf_matched}/{len(merged)}")
    print(f"Geocoded:            {geo_matched}/{len(merged)}")
    print(f"Fee ceilings (AOS):  {sum(1 for r in merged if r['fee_ceiling_infant'])}/{len(merged)}")

    write_dataset(OUT_PATH, merged)
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    run()
