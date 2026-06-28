"""
Merges all scraped datasets into a single denormalized file.

Spine: ecda_centres.json (one record per licensed centre)
  + lifesg_fees.json         → joined on centre_code; added as nested fees: {IC: {min, max}, …}
  + myfirstskool.json        → joined on postal_code; added as mfs_* fields
  + pcf_sparkletots.json     → joined on postal_code; added as pcf_* fields
  + my_world_preschool.json  → joined on postal_code; added as myw_* fields
  + ebridge.json             → joined on postal_code; added as eb_* fields
  + skool4kidz.json          → joined on postal_code; added as s4k_* fields
  + moe_kindergartens.json   → joined on postal_code; added as moe_* fields
  + learning_vision.json     → joined on postal_code (+ spatial fallback); added as lv_* fields
  + star_learners.json       → joined on postal_code; added as sl_* fields
  + geocoded.json            → joined on postal_code; added as lat/lng fields

Derived fields:
  + operating_hours     → best human-readable hours from scrapers, else formatted weekday_full_day
  + MSF fee ceilings    → derived from scheme_type (Anchor/Partner Operator caps)

ecda_upcoming.json contains future centres not yet in the spine and is left separate.

Output: data/merged.json
"""
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from scrapers.utils import write_dataset

CENTRES_PATH = Path("data/ecda_centres-latest.json")
FEES_PATH = Path("data/lifesg_fees-latest.json")
MFS_PATH = Path("data/myfirstskool-latest.json")
PCF_PATH = Path("data/pcf_sparkletots-latest.json")
MYW_PATH = Path("data/my_world_preschool-latest.json")
EB_PATH = Path("data/ebridge-latest.json")
S4K_PATH = Path("data/skool4kidz-latest.json")
MOE_PATH = Path("data/moe_kindergartens-latest.json")
LV_PATH = Path("data/learning_vision-latest.json")
SL_PATH = Path("data/star_learners-latest.json")
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

MYW_FIELDS = ("name", "address", "phone", "email")

EB_FIELDS = ("url", "name", "address", "operating_hours", "phone", "email")

S4K_FIELDS = ("url", "name", "address")

MOE_FIELDS = ("slug", "name", "area", "address", "phone", "email", "website",
              "active", "is_enrolling")

LV_FIELDS = ("url", "name", "address")

SL_FIELDS = ("url", "name", "address", "fees_citizen_monthly", "fees_pr_monthly")


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    R = 6_371_000
    φ1, φ2 = radians(lat1), radians(lat2)
    dφ = radians(lat2 - lat1)
    dλ = radians(lng2 - lng1)
    a = sin(dφ / 2) ** 2 + cos(φ1) * cos(φ2) * sin(dλ / 2) ** 2
    return R * 2 * asin(sqrt(a))


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


def build_lv_index(
    lv_records: list[dict], geo_index: dict[str, dict], max_dist_m: float = 300
) -> dict[str, dict]:
    """postal_code → LV record.

    Centres with a postal code in their address use direct matching.
    Those without use a spatial fallback: find the nearest geocoded ECDA
    postal within max_dist_m metres of the LV lat/lng.
    """
    direct: dict[str, dict] = {}
    spatial: list[dict] = []

    for rec in lv_records:
        postal = rec.get("postal_code")
        if postal:
            direct[postal] = rec
        elif rec.get("lat") and rec.get("lng"):
            spatial.append(rec)

    if not spatial:
        return direct

    # Build (postal, lat, lng) list from geocoded data for spatial lookup
    geo_points: list[tuple[str, float, float]] = []
    for postal, geo in geo_index.items():
        if geo.get("lat") and geo.get("lng"):
            geo_points.append((postal, float(geo["lat"]), float(geo["lng"])))

    for rec in spatial:
        lv_lat, lv_lng = float(rec["lat"]), float(rec["lng"])
        best_postal, best_d = None, float("inf")
        for postal, glat, glng in geo_points:
            d = _haversine_m(lv_lat, lv_lng, glat, glng)
            if d < best_d:
                best_d = d
                best_postal = postal
        if best_postal and best_d <= max_dist_m:
            direct[best_postal] = rec

    return direct


def derive_operating_hours(record: dict) -> str | None:
    """Return the best available human-readable operating hours.

    Priority: scraper-sourced text fields (pcf, mfs, eb) first;
    fall back to ECDA's structured weekday_full_day + saturday fields.
    """
    for field in ("pcf_operating_hours", "mfs_operating_hours", "eb_operating_hours"):
        if record.get(field):
            return record[field]

    wfd = record.get("weekday_full_day")
    if wfd and wfd not in ("na", ""):
        text = f"Mon–Fri {wfd}"
        sat = record.get("saturday")
        if sat and sat not in ("na", "", "00:00-00:00"):
            text += f", Sat {sat}"
        return text

    return None


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
    myw_index = build_postal_index(load(MYW_PATH))
    eb_index = build_postal_index(load(EB_PATH))
    s4k_index = build_postal_index(load(S4K_PATH))
    moe_index = build_postal_index(load(MOE_PATH))
    sl_index = build_postal_index(load(SL_PATH))
    geo_index = build_geocode_index(load(GEOCODED_PATH))
    lv_index = build_lv_index(load(LV_PATH), geo_index)

    merged: list[dict] = []
    fees_matched = mfs_matched = pcf_matched = 0
    myw_matched = eb_matched = s4k_matched = moe_matched = geo_matched = 0
    lv_matched = sl_matched = 0

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

        myw = myw_index.get(postal)
        if myw:
            for field in MYW_FIELDS:
                record[f"myw_{field}"] = myw.get(field)
            myw_matched += 1
        else:
            for field in MYW_FIELDS:
                record[f"myw_{field}"] = None

        eb = eb_index.get(postal)
        if eb:
            for field in EB_FIELDS:
                record[f"eb_{field}"] = eb.get(field)
            eb_matched += 1
        else:
            for field in EB_FIELDS:
                record[f"eb_{field}"] = None

        s4k = s4k_index.get(postal)
        if s4k:
            for field in S4K_FIELDS:
                record[f"s4k_{field}"] = s4k.get(field)
            s4k_matched += 1
        else:
            for field in S4K_FIELDS:
                record[f"s4k_{field}"] = None

        moe = moe_index.get(postal)
        if moe:
            for field in MOE_FIELDS:
                record[f"moe_{field}"] = moe.get(field)
            moe_matched += 1
        else:
            for field in MOE_FIELDS:
                record[f"moe_{field}"] = None

        # LV join: only apply to ECDA centres that are actually Learning Vision
        # (multiple unrelated operators can share a postal code at the same building)
        lv = lv_index.get(postal) if "learning vision" in centre.get("centre_name", "").lower() else None
        if lv:
            for field in LV_FIELDS:
                record[f"lv_{field}"] = lv.get(field)
            lv_matched += 1
        else:
            for field in LV_FIELDS:
                record[f"lv_{field}"] = None

        # SL join: only apply to Star Learners ECDA centres
        sl = sl_index.get(postal) if "star learners" in centre.get("centre_name", "").lower() else None
        if sl:
            for field in SL_FIELDS:
                record[f"sl_{field}"] = sl.get(field)
            sl_matched += 1
        else:
            for field in SL_FIELDS:
                record[f"sl_{field}"] = None

        geo = geo_index.get(postal)
        if geo:
            record["lat"] = geo.get("lat")
            record["lng"] = geo.get("lng")
            geo_matched += 1
        else:
            record["lat"] = None
            record["lng"] = None

        record.update(fee_ceilings_for(centre.get("scheme_type", "na")))
        record["operating_hours"] = derive_operating_hours(record)

        merged.append(record)

    print(f"Centres:             {len(merged)}")
    print(f"Fees joined:         {fees_matched}/{len(merged)}")
    print(f"MFS joined:          {mfs_matched}/{len(merged)}")
    print(f"PCF joined:          {pcf_matched}/{len(merged)}")
    print(f"MYW joined:          {myw_matched}/{len(merged)}")
    print(f"E-Bridge joined:     {eb_matched}/{len(merged)}")
    print(f"Skool4Kidz joined:   {s4k_matched}/{len(merged)}")
    print(f"MOE KG joined:       {moe_matched}/{len(merged)}")
    print(f"Learning Vision:     {lv_matched}/{len(merged)}")
    print(f"Star Learners:       {sl_matched}/{len(merged)}")
    print(f"Geocoded:            {geo_matched}/{len(merged)}")
    print(f"Fee ceilings (AOS):  {sum(1 for r in merged if r['fee_ceiling_infant'])}/{len(merged)}")
    print(f"Operating hours:     {sum(1 for r in merged if r['operating_hours'])}/{len(merged)}")

    write_dataset(OUT_PATH, merged)
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    run()
