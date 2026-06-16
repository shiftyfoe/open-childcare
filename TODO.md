# TODO

## 2. PCF Sparkletots scraper ✓

- [x] `scrapers/pcf_sparkletots.py` — scrapes 356 centre pages via `our-preschools-sitemap.xml`
  - Fields: name, postal_code, phone, email, operating_hours, principal, programme_type (EY/CC/DS)
  - Join key: postal_code → merged as `pcf_*` fields
  - Crawl delay: 2s; robots.txt: only /orientation/ disallowed
- [x] `pcf_*` fields added to `scrapers/merge.py`
- [x] `pcf_sparkletots` added to GHA scraper matrix
- Expected lift: 9% → ~27% operator-field coverage (~280 of 341 PCF ECDA centres)

## 3. OneMap geocoding ✓

- [x] `scrapers/geocode.py` — geocodes all postal codes via OneMap API (no auth)
  - Caches existing `geocoded-latest.json` to skip unchanged postals on repeat runs
  - Output: `data/geocoded.json` → `geocoded-YYYY-MM-DD.json` + `geocoded-latest.json`
  - Fields added to merge: `lat`, `lng`
- [x] `lat`/`lng` merged into `scrapers/merge.py` (join on postal_code)
- [x] `Geocode centres` step added to GHA commit job (runs before merge)
- Expected: ~95%+ coverage (sample hit rate: 19/20; 1,747 unique postals)

## 4. MSF fee ceilings (static lookup) ✓

- [x] `FEE_CEILINGS` lookup in `scrapers/merge.py` keyed on `scheme_type`
  - Anchor Operator: S$1,370 infant / S$800 non-infant (before subsidy)
  - Partner Operator / private: no cap (null)
- [x] `fee_ceiling_infant` / `fee_ceiling_non_infant` emitted in merged output
- [x] Fix merge.py input paths to use `-latest.json` (matches `write_dataset` output)
