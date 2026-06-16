"""
Merges all scraped datasets into a single denormalized file.

Spine: ecda_centres.json (one record per licensed centre)
  + lifesg_fees.json    → joined on centre_code; added as nested fees: {IC: {min, max}, …}
  + myfirstskool.json   → joined on postal_code; added as mfs_* fields

ecda_upcoming.json contains future centres not yet in the spine and is left separate.

Output: data/merged.json
"""
import json
from pathlib import Path

from scrapers.utils import write_dataset

CENTRES_PATH = Path("data/ecda_centres.json")
FEES_PATH = Path("data/lifesg_fees.json")
MFS_PATH = Path("data/myfirstskool.json")
OUT_PATH = Path("data/merged.json")

MFS_FIELDS = ("url", "name", "principal", "programmes", "operating_hours",
              "spark_accredited", "year_established", "mother_tongue")


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


def build_mfs_index(mfs: list[dict]) -> dict[str, dict]:
    """postal_code → mfs record (collisions already verified absent)"""
    index: dict[str, dict] = {}
    for row in mfs:
        postal = row.get("postal_code")
        if postal:
            index[postal] = row
    return index


def run() -> None:
    centres = load(CENTRES_PATH)
    if not centres:
        raise RuntimeError(f"{CENTRES_PATH} is required but missing")

    fees_index = build_fees_index(load(FEES_PATH))
    mfs_index = build_mfs_index(load(MFS_PATH))

    merged: list[dict] = []
    fees_matched = mfs_matched = 0

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

        merged.append(record)

    print(f"Centres:       {len(merged)}")
    print(f"Fees joined:   {fees_matched}/{len(merged)}")
    print(f"MFS joined:    {mfs_matched}/{len(merged)}")

    write_dataset(OUT_PATH, merged)
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    run()
