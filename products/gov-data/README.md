# `product_id: gov-data`

U.S. federal open data — the **mixed-format** product that exercises the Phase-1.5 loader
seam (spec Part B's acceptance gate wants one product ingesting end-to-end across several
formats). `product_id` is derived from this folder's name.

Every file here is a **U.S. Government work → public domain** (17 U.S.C. §105), downloaded
2026-08-19. Frozen like the Phase-1 corpus: re-downloading a newer edition would shift
chunk ids and break the golden set.

| File | Format | Source | Notes |
|---|---|---|---|
| `nasa-global-temperature.csv` | CSV | [NASA GISS GISTEMP v4](https://data.giss.nasa.gov/gistemp/) | Land-ocean global mean temperature anomalies, 1880–2024. 149 lines. |
| `us-population-by-state.xlsx` | XLSX | [U.S. Census Bureau, NST-EST2023-POP](https://www2.census.gov/programs-surveys/popest/tables/2020-2023/state/totals/) | State population estimates 2020–2023. One sheet, 68 rows × 6 cols. |
| `nist-cloud-computing-definition.pdf` | PDF (text layer) | [NIST SP 800-145](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-145.pdf) | 7 pages, real embedded text layer — verified with `pypdf` (522 chars extracted from p.2). |

## ⚠️ Both tabular files are realistically messy — that is the point

Neither is a clean `header,row,row` CSV, and step 2's row→text serialization has to cope:

- **`nasa-global-temperature.csv`** — line 1 is a *title* (`Land-Ocean: Global Means`); the
  real header is line 2. Missing values are the sentinel `***`, not empty.
- **`us-population-by-state.xlsx`** — rows 1–4 are title text and a *split* header (the
  year labels sit on a different row from the column names) before real data begins.

A naive `csv.DictReader` / `openpyxl` read produces garbage from both. Good: the whole
reason step 2 measures its serialization choice on the eval harness is that this decision
is not obvious.

## Still to add

A **scanned / image-only PDF** for the step-4 OCR fork. Plan: rasterize the NIST PDF
ourselves rather than hunt for one — that makes the text-layer version the **ground truth**,
so OCR error becomes directly measurable instead of guessed at.
