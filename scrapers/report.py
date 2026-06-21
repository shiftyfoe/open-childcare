"""
Generate short-term (1–3 month) and long-term (6–7 month) value-for-money
childcare reports for Singapore parents, broken down by URA planning region.

Output files (committed daily to docs/):
  docs/report-short-term.md
  docs/report-long-term.md

Vacancy slots  : current → next → third → fourth → fifth → sixth → seventh month
Short-term view: Now (current) vs Month 3 (third)
Long-term view : Now (current) vs Month 6 (sixth) and Month 7 (seventh)
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

MERGED_PATH = Path("data/merged-latest.json")
UPCOMING_PATH = Path("data/ecda_upcoming-latest.json")
DOCS_DIR = Path("docs")

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# URA planning region → ordered keyword list (longer/more specific terms first).
# Source: https://en.wikipedia.org/wiki/Subzones_of_Singapore
REGION_KEYWORDS: dict[str, list[str]] = {
    "Central": [
        # Bishan PA
        "bishan", "sin ming",
        # Bukit Merah PA
        "bukit merah", "tiong bahru", "telok blangah", "redhill", "henderson", "alexandra",
        "lengkok bahru", "stirling", "depot road",
        # Bukit Timah PA
        "bukit timah", "ghim moh", "holland", "dunearn",
        # Geylang PA
        "geylang", "aljunied", "macpherson", "mcnair", "ubi",
        # Kallang PA
        "kallang", "bendemeer", "boon keng", "lavender", "potong pasir",
        "bidadari", "whampoa", "alkaff", "jalan satu",
        # Marine Parade PA (Central Region per URA)
        "marine parade", "katong", "joo chiat", "amber road", "mountbatten",
        # Newton PA
        "newton", "cairnhill",
        # Novena PA
        "novena", "moulmein", "balestier", "upper thomson", "thomson road",
        # Orchard / Tanglin PAs
        "orchard", "tanglin", "river valley",
        # Outram PA
        "outram", "tanjong pagar", "havelock",
        # Queenstown PA
        "queenstown", "commonwealth",
        # Rochor / Downtown Core / Outram (cont.)
        "rochor", "kitchener", "little india", "bras basah",
        "shenton way", "temasek boulevard", "clemenceau", "raffles",
        "indus road", "chwee chian", "tanjong pagar plaza",
        # Toa Payoh PA (incl Farrer Park, Whampoa, Woodleigh subzones)
        "toa payoh", "farrer park", "woodleigh", "shunfu", "ah hood",
        # Bishan PA extras
        "jalan pemimpin",
        # Bukit Timah / Newton / Tanglin extras
        "hindhede", "namly", "linden drive", "dunearn", "dover",
        "kay siang", "vanda", "flower road", "st. anne",
        # Kallang / Marine Parade extras
        "circuit road", "lorong l telok", "tembeling", "jalan pari burong",
        "wellington circle",
        # Cecil / Downtown extras
        "cecil street",
    ],
    "North": [
        # Sembawang PA (incl. Canberra, Gambas subzones)
        "sembawang", "canberra", "gambas",
        # Woodlands PA
        "woodlands", "marsiling", "admiralty", "kranji", "woodgrove",
        # Yishun PA
        "yishun",
        # Others
        "sungei kadut", "mandai",
    ],
    "North-East": [
        # Ang Mo Kio PA
        "ang mo kio", "amk", "teck ghee", "lentor", "yio chu kang",
        # Hougang PA (incl. Buangkok, Jalan Merdu area)
        "hougang", "kovan", "buangkok", "jalan merdu",
        # Punggol PA
        "punggol", "northshore", "edgefield", "edgedale", "sumang",
        # Sengkang PA
        "sengkang", "fernvale", "rivervale", "compassvale", "anchorvale",
        # Serangoon PA
        "serangoon", "lorong chuan", "upper serangoon",
        # Seletar PA
        "seletar",
    ],
    "East": [
        # Bedok PA
        "bedok", "kembangan", "chai chee", "upper east coast", "eunos", "east coast",
        "kaki bukit", "frankel",
        # Changi PA
        "changi", "loyang", "elias",
        # Pasir Ris PA
        "pasir ris",
        # Paya Lebar PA
        "paya lebar",
        # Tampines PA
        "tampines", "simei",
    ],
    "West": [
        # Bukit Batok PA
        "bukit batok",
        # Bukit Panjang PA (incl. Segar subzone)
        "bukit panjang", "fajar", "segar", "petir", "bangkit", "pending", "senja",
        # Choa Chu Kang PA
        "choa chu kang", "chua chu kang", "yew tee", "teck whye", "keat hong",
        # Clementi PA (incl. Pasir Panjang, West Coast subzones)
        "clementi", "west coast", "pandan", "pasir panjang", "teban",
        # Jurong East PA
        "jurong east", "toh guan", "international business park",
        # Jurong West PA
        "jurong west", "jurong", "yung ho", "yung an", "westlake",
        "corporation drive",
        # Boon Lay / Pioneer PAs
        "boon lay", "gek poh", "pioneer",
        # Tengah PA
        "tengah", "plantation crescent",
        # Other West subzones
        "zhenghua", "cashew", "hillview",
    ],
}

REGION_ORDER = ["Central", "East", "North", "North-East", "West", "Other"]

# (vacancy_field_prefix, fee_level_key, display_label)
LEVELS: list[tuple[str, str, str]] = [
    ("infant", "Infant", "Infant Care (0–18 months)"),
    ("n1",     "N1",     "Nursery N1/N2 (18 months – 4 years)"),
    ("k1",     "K1",     "Kindergarten K1/K2 (4–6 years)"),
]

VACANCY_ICON: dict[str | None, str] = {
    "Available": "✅",
    "Limited":   "⚠️",
    "Full":      "❌",
}

ANCHOR_CAPS = {"infant": 1_370, "n1": 800, "k1": 800}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def month_label(offset: int) -> str:
    d = date.today()
    idx = (d.month - 1 + offset) % 12
    yr = d.year + (d.month - 1 + offset) // 12
    return f"{MONTH_ABBR[idx]} {yr}"


def assign_region(texts: list[str]) -> str:
    haystack = " ".join(t.lower() for t in texts if t)
    for region, keywords in REGION_KEYWORDS.items():
        for kw in keywords:
            if kw in haystack:
                return region
    return "Other"


def value_score(c: dict, lvl: str) -> float:
    score = 0.0
    scheme = c.get("scheme_type", "na")
    if scheme == "Anchor Operator Scheme":
        score += 100
    elif scheme == "Partner Operator Scheme":
        score += 60
    if c.get("spark_certified") == "Yes":
        score += 40
    fee_key = {"infant": "Infant", "n1": "N1", "k1": "K1"}[lvl]
    fd = (c.get("fees") or {}).get(fee_key) or {}
    max_fee = fd.get("max") or 0
    if max_fee > 0:
        score += max(0.0, (2_500 - max_fee) / 2_500 * 30)
    return score


def vi(v: str | None) -> str:
    return VACANCY_ICON.get(v or "", "—")


def fmt_fee(c: dict, lvl: str) -> str:
    fee_key = {"infant": "Infant", "n1": "N1", "k1": "K1"}[lvl]
    fd = (c.get("fees") or {}).get(fee_key) or {}
    max_fee = fd.get("max") or 0
    if not max_fee:
        return "—"
    scheme = c.get("scheme_type", "na")
    if scheme == "Anchor Operator Scheme":
        cap = ANCHOR_CAPS[lvl]
        if max_fee > cap:
            return f"~~${max_fee:,.0f}~~ ≤${cap}"
    return f"${max_fee:,.0f}"


def fmt_scheme(c: dict) -> str:
    s = c.get("scheme_type", "na")
    return {"Anchor Operator Scheme": "ANC", "Partner Operator Scheme": "PRT"}.get(s, "—")


def fmt_spark(c: dict) -> str:
    return "✓" if c.get("spark_certified") == "Yes" else ""


def fmt_contact(c: dict) -> str:
    ph = c.get("centre_contact_no") or c.get("contactno_lifesg") or ""
    w = c.get("centre_website") or c.get("website_lifesg") or ""
    if w and not w.startswith("http"):
        w = f"https://{w}"
    parts: list[str] = []
    if ph:
        parts.append(ph)
    if w:
        parts.append(f"[↗]({w})")
    return " · ".join(parts) if parts else "—"


def urgency(curr: str | None, third: str | None) -> str:
    if curr == "Limited" and third == "Full":
        return "🔴 Act this week"
    if curr == "Available" and third == "Full":
        return "🟠 Act this month"
    if curr == "Limited":
        return "🟡 Filling fast"
    return "🟢 Available"


def offers_level(c: dict, lvl: str) -> bool:
    v = c.get(f"{lvl}_vacancy_current_month")
    return v not in (None, "", "Not Applicable")


def has_vacancy_now(c: dict, lvl: str) -> bool:
    return c.get(f"{lvl}_vacancy_current_month") in ("Available", "Limited")


def has_vacancy_long(c: dict, lvl: str) -> bool:
    return (
        c.get(f"{lvl}_vacancy_sixth_month") in ("Available", "Limited")
        or c.get(f"{lvl}_vacancy_seventh_month") in ("Available", "Limited")
    )


# ---------------------------------------------------------------------------
# Table renderers
# ---------------------------------------------------------------------------

def short_table(pool: list[dict], lvl: str, m3_label: str, top_n: int = 5) -> str:
    eligible = sorted(
        [c for c in pool if offers_level(c, lvl) and has_vacancy_now(c, lvl)],
        key=lambda c: value_score(c, lvl),
        reverse=True,
    )[:top_n]

    if not eligible:
        return "_No centres with current availability in this region for this level._\n\n"

    rows = [
        f"| Centre | Sch | ★ | Max fee | Now | {m3_label} | Action | Contact |",
        "|---|:---:|:---:|---:|:---:|:---:|---|---|",
    ]
    for c in eligible:
        curr = c.get(f"{lvl}_vacancy_current_month") or ""
        third = c.get(f"{lvl}_vacancy_third_month") or ""
        rows.append(
            f"| {c['centre_name']} "
            f"| {fmt_scheme(c)} | {fmt_spark(c)} | {fmt_fee(c, lvl)} "
            f"| {vi(curr)} | {vi(third)} "
            f"| {urgency(curr, third)} | {fmt_contact(c)} |"
        )
    return "\n".join(rows) + "\n\n"


def long_table(pool: list[dict], lvl: str, m6_label: str, m7_label: str, top_n: int = 5) -> str:
    eligible = sorted(
        [c for c in pool if offers_level(c, lvl) and has_vacancy_long(c, lvl)],
        key=lambda c: value_score(c, lvl),
        reverse=True,
    )[:top_n]

    if not eligible:
        return "_No centres projected to have availability in 6–7 months for this level._\n\n"

    rows = [
        f"| Centre | Sch | ★ | Max fee | Now | {m6_label} | {m7_label} | Contact |",
        "|---|:---:|:---:|---:|:---:|:---:|:---:|---|",
    ]
    for c in eligible:
        curr = c.get(f"{lvl}_vacancy_current_month") or ""
        sixth = c.get(f"{lvl}_vacancy_sixth_month") or ""
        seventh = c.get(f"{lvl}_vacancy_seventh_month") or ""
        rows.append(
            f"| {c['centre_name']} "
            f"| {fmt_scheme(c)} | {fmt_spark(c)} | {fmt_fee(c, lvl)} "
            f"| {vi(curr)} | {vi(sixth)} | {vi(seventh)} "
            f"| {fmt_contact(c)} |"
        )
    return "\n".join(rows) + "\n\n"


def upcoming_table(centres: list[dict]) -> str:
    if not centres:
        return ""
    rows = [
        "| Centre | Est. Opening | Register? | Address | Contact |",
        "|---|:---:|:---:|---|---|",
    ]
    for u in sorted(centres, key=lambda x: x.get("estimated_commencement_date", "Q4")):
        reg = "✅ Open" if u.get("open_for_registration") == "Yes" else "Not yet"
        ph = u.get("contact_number") or ""
        if ph == "-":
            ph = "TBC"
        addr = u.get("address", "")
        name = u.get("name", "")
        rows.append(f"| {name} | {u.get('estimated_commencement_date', '')} | {reg} | {addr} | {ph} |")
    return "\n".join(rows) + "\n\n"


# ---------------------------------------------------------------------------
# Report builders
# ---------------------------------------------------------------------------

LEGEND = """\
| Column | Meaning |
|---|---|
| **Sch** | `ANC` = Anchor Operator — MSF fee ceiling applies ($800/mo non-infant, $1,370/mo infant, **before** subsidies) · `PRT` = Partner Operator · `—` = Private (no cap) |
| **★** | SPARK-accredited quality mark from ECDA |
| **Max fee** | Published maximum from LifeSG. For ANC centres where the published fee exceeds the cap, shown as ~~nominal~~ ≤cap. |
| **Now / Month** | ✅ Available · ⚠️ Limited (act fast) · ❌ Full |
"""


def build_short_report(
    by_region: dict[str, list[dict]],
    upcoming_by_region: dict[str, list[dict]],
    today: date,
) -> str:
    m3 = month_label(2)

    lines = [
        "# Singapore Childcare Value Report — Short-Term (1–3 Months)",
        "",
        f"_Updated: {today.strftime('%d %b %Y')}. "
        f"Vacancy data covers **{month_label(0)}** through **{m3}**. "
        f"Top 5 best-value picks per level per region._",
        "",
        "## Legend",
        "",
        LEGEND,
        "**Action column:** 🔴 Act this week (Limited now, Full in 3 months) "
        "· 🟠 Act this month (Available now, Full in 3 months) "
        "· 🟡 Filling fast (Limited, not yet Full) · 🟢 Still available",
        "",
        "---",
        "",
    ]

    for region in REGION_ORDER:
        pool = by_region.get(region, [])
        upcoming_here = [
            u for u in upcoming_by_region.get(region, [])
            if u.get("estimated_commencement_date", "Q4") <= "Q2"
        ]
        if not pool and not upcoming_here:
            continue

        lines.append(f"## {region} Region")
        lines.append("")

        if pool:
            for lvl, _, lvl_label in LEVELS:
                n_offers = sum(1 for c in pool if offers_level(c, lvl))
                n_avail = sum(1 for c in pool if has_vacancy_now(c, lvl) and offers_level(c, lvl))
                if n_offers == 0:
                    continue
                lines.append(f"### {lvl_label}")
                lines.append(f"_{n_avail} of {n_offers} centres with availability now._")
                lines.append("")
                lines.append(short_table(pool, lvl, m3))

        if upcoming_here:
            lines.append("### New Centres Opening This Quarter (Q2 2026)")
            lines.append(
                "_Brand-new centres with no existing waitlist — "
                "register now to be first in queue._"
            )
            lines.append("")
            lines.append(upcoming_table(upcoming_here))

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def build_long_report(
    by_region: dict[str, list[dict]],
    upcoming_by_region: dict[str, list[dict]],
    today: date,
) -> str:
    m6 = month_label(5)
    m7 = month_label(6)

    lines = [
        "# Singapore Childcare Value Report — Long-Term (6–7 Months)",
        "",
        f"_Updated: {today.strftime('%d %b %Y')}. "
        f"Vacancy projections for **{m6}** and **{m7}**. "
        f"New openings pipeline: Q3–Q4 2026. "
        f"Top 5 best-value picks per level per region._",
        "",
        "## Legend",
        "",
        LEGEND,
        "",
        "---",
        "",
    ]

    for region in REGION_ORDER:
        pool = by_region.get(region, [])
        upcoming_here = [
            u for u in upcoming_by_region.get(region, [])
            if u.get("estimated_commencement_date", "Q4") > "Q2"
        ]
        if not pool and not upcoming_here:
            continue

        lines.append(f"## {region} Region")
        lines.append("")

        if pool:
            for lvl, _, lvl_label in LEVELS:
                n_offers = sum(1 for c in pool if offers_level(c, lvl))
                n_long = sum(1 for c in pool if has_vacancy_long(c, lvl) and offers_level(c, lvl))
                if n_offers == 0:
                    continue
                lines.append(f"### {lvl_label}")
                lines.append(
                    f"_{n_long} of {n_offers} centres projected to have availability "
                    f"by {m6}._"
                )
                lines.append("")
                lines.append(long_table(pool, lvl, m6, m7))

        if upcoming_here:
            lines.append("### Upcoming New Centres Pipeline")
            lines.append(
                "_New centres starting fresh — register as soon as registration opens "
                "to skip existing waitlists._"
            )
            lines.append("")
            lines.append(upcoming_table(upcoming_here))

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> None:
    merged: list[dict] = json.loads(MERGED_PATH.read_text())
    upcoming: list[dict] = json.loads(UPCOMING_PATH.read_text())
    today = date.today()

    # Group merged centres by region
    by_region: dict[str, list[dict]] = defaultdict(list)
    unmatched = 0
    for c in merged:
        texts = [
            c.get("centre_name", ""),
            c.get("centre_address", ""),
            c.get("moe_area") or "",
        ]
        region = assign_region(texts)
        if region == "Other":
            unmatched += 1
        by_region[region].append(c)

    # Group upcoming centres by region
    upcoming_by_region: dict[str, list[dict]] = defaultdict(list)
    for u in upcoming:
        texts = [u.get("name", ""), u.get("address", "")]
        region = assign_region(texts)
        upcoming_by_region[region].append(u)

    if unmatched:
        print(f"WARNING: {unmatched} centres could not be assigned to a region (→ 'Other')")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    short_path = DOCS_DIR / "report-short-term.md"
    short_path.write_text(build_short_report(by_region, upcoming_by_region, today))
    print(f"Written: {short_path}")

    long_path = DOCS_DIR / "report-long-term.md"
    long_path.write_text(build_long_report(by_region, upcoming_by_region, today))
    print(f"Written: {long_path}")

    # Print region distribution for diagnostics
    print("\nRegion distribution:")
    for region in REGION_ORDER:
        print(f"  {region}: {len(by_region.get(region, []))} centres")


if __name__ == "__main__":
    run()
