# Audit report – Competitor_Scorecard.xlsx

**Date:** 2026-09-18  **Scope:** every tab of `output/Competitor_Scorecard.xlsx` as built by
`src/build_workbook.py`, against the six areas requested. All checks are scripted
(`src/audit_raw.py`, `src/audit_instances.py`, and the ad-hoc checks reproduced in this report) so
they can be re-run after any rebuild. Findings are classified **FIXED** (changed in this revision),
**NOTED** (correct, but worth knowing), or **CLEAN**.

## Summary of findings

| # | Area | Finding | Status |
|---|---|---|---|
| 1 | Raw Data – definitions | Costco "revenue" was *total revenue including membership fees*; Walmart and Sam's Club use *net sales excluding membership income*. Inconsistent denominator for gross margin, net margin and growth. | **FIXED** – Costco moved to net sales (ProductMember disaggregated-revenue fact from FY2018, SalesRevenueNet before); total revenue and membership fees (formula) added as memo rows; Costco gross margin now 10.5–11.3% instead of 12.1–13.3%. |
| 2 | Raw Data – Walmart FY2018 | Walmart's FY2019 10-K tagged the prior-year ASC 842 comparatives as literal zeros; the extractor had taken those zeros ahead of the real capital-lease values under the older tag, understating FY2018 Total debt by $7,412M (D/E 0.64x instead of 0.73x). | **FIXED** in the previous revision (extractor now refuses a zero when a later candidate tag holds a value); regression test added. |
| 3 | Caveats – 53-week years | Workbook said only FY2023 had 53 weeks for Costco and Kroger. Period lengths show FY2017 was also a 53-week year for both. | **FIXED** in Executive Summary and Methodology. |
| 4 | Methodology – Walmart LIFO | Said Walmart "stopped quantifying its reserve after FY2020". 10-K text: "LIFO approximated FIFO" is stated through the 10-K for the year ended January 2022 (FY2021); sensitivity language only from the FY2022 10-K. | **FIXED** wording. |
| 5 | Methodology – Costco LIFO | Said Costco's LIFO effect is "immaterial". FY2022 10-K: LIFO charge cost 19 bp of gross margin (~$0.4B); FY2023 smaller, FY2024 immaterial benefit, FY2025 7 bp charge. | **FIXED** wording. |
| 6 | Executive Summary – Whole Foods | "34–35% gross margin" – actual FY2016–17 values are 34.4% and 33.7%. | **FIXED** to "~34%". |
| 7 | Scorecard takeaway | "Warehouse clubs run 11–13%" – on the corrected net-sales basis they run 10–12%. | **FIXED**. |
| 8 | Raw Data – restatements | Four values differ between first-filed and latest-filed 10-Ks (see §1.3). Sheet uses latest-filed, per the stated policy; both values are on Data Lineage. | **NOTED** |
| 9 | Raw Data – Kroger FY2017–18 | Kroger re-presented FY2017 and FY2018 revenue *and* cost of sales in its FY2019 10-K (revenue +$618M / +$690M; cost of sales +$149M / +$209M). Sheet uses the re-presented pair, so gross margin is internally consistent. | **NOTED** |

Everything else checked was clean. Detail follows.

## 1. Raw Data accuracy (Tab 3)

### 1.1 Re-verification against sources not used to build the sheet

**A. SEC XBRL frames API** (`data.sec.gov/api/xbrl/frames`, a separately aggregated dataset):
all six core inputs × four full filers × FY2015–FY2025 where the fact carries an SEC frame label.

- Values compared: **187** · matches: **187** · mismatches: **0**
- 29 values had no frame label (the SEC omits it on some duplicate-period facts) and were covered by check B.
- Sheet value (USD millions) equals extracted XBRL value ÷ 1e6 for all 216 core cells.

**B. 10-K XBRL instance documents**, parsed independently with lxml – every 10-K filed
2017-01-01 onward for Walmart, Costco, Kroger and Whole Foods (30 filings). Each filing carries the
current year and the prior-year comparative, so most years are checked in two different filings.

- Comparisons: **493** · agree with sheet: **484** · differ: **9**
- The 9 differences are all *earlier* filings whose numbers were later re-presented (Costco
  FY2015–17 "SalesRevenueNet" vs total revenue – the definitional issue in finding #1, now
  resolved; Kroger FY2017–18 revenue and cost of sales – finding #9). In every case the sheet
  holds the latest-filed value, as the policy states.
- Seven core cells not reachable by this check (Costco FY2015 current assets/liabilities –
  comparative only in a 2016 filing; Whole Foods derived COGS ×3 and FY2015 CA/CL) were verified by
  check A and by the derivation tie-out test (`test_whole_foods_cogs_derivation_ties`).

**C. Segment and successor lines** (Sam's Club, Amazon "Physical stores", Costco net sales):
parsed from the instance documents directly; spot-tied to 10-K text (Costco FY2022 net sales
$222,730M and membership fees $4,224M match the MD&A sentences verbatim; Sam's Club FY2025 net
sales $93,015M matches the segment note).

### 1.2 Fiscal-year labelling

- Every fact's SEC `frame` attribute was compared with the fiscal-year label on the sheet:
  127/127 duration facts and 408/408 instant facts agree (e.g. Walmart period ending 2026-01-31 is
  frame CY2025 and is labelled FY2025; Costco period ending 2025-08-31 is CY2025 → FY2025).
- Period-end dates per label are printed on each company block ("Fiscal year end" row).
- Period lengths: Walmart 364/365 days every year (fixed January 31 year-end). Costco and Kroger
  show 370-day spans in FY2017 and FY2023 (53-week years) – finding #3.

### 1.3 Restated figures (first-filed ≠ latest-filed)

| Company | Line | FY | First filed | Latest filed | Note |
|---|---|---|---|---|---|
| Costco | Current assets | 2015 | 17,299 | 16,779 | Deferred-tax reclassification (ASU 2015-17) in the FY2016 10-K |
| Costco | Current liabilities | 2015 | 16,540 | 16,539 | Rounding re-presentation |
| Kroger | Revenue | 2017 | 122,662 | 123,280 | Re-presented in FY2019 10-K (with cost of sales) |
| Kroger | Revenue | 2018 | 121,162 | 121,852 | Re-presented in FY2019 10-K (with cost of sales) |

The sheet uses the latest-filed value in each case. Both values and both accession numbers are on
Data Lineage with `Restated = yes`.

### 1.4 Units

All XBRL facts are in USD; the sheet stores value ÷ 1,000,000 with number format `#,##0` and states
"USD millions" in the tab header. Magnitudes checked for every company (e.g. Walmart FY2025 revenue
706,413 = $706.4B). No mixed units found.

### 1.5 Notes / citation column

For all 24 core rows the tag(s) listed in column B equal the set of tags recorded in
`data/facts_long.csv` for that row (0 mismatches). Every value's accession number, filing date and
EDGAR link are on Data Lineage (658 rows). Instance-derived and two-fact-derived values (7) are
shaded and carry their derivation in the notes column.

## 2. Formula integrity (Tab 4)

- **Definitions:** every one of the **360** ratio formulas was pattern-matched against its stated
  definition (e.g. gross margin `=IFERROR((XLOOKUP(y,Years,C_Revenue)-XLOOKUP(y,Years,C_COGS))/XLOOKUP(y,Years,C_Revenue),"n/a")`).
  360 match, 0 deviate. Every formula references the named range of the company on its own row and
  the year in its own column header.
- **Hand recalculation** from Raw Data: Kroger GM FY2022 0.214343, Walmart NM FY2018 0.013070,
  Costco CR FY2020 1.131863, Kroger D/E FY2025 2.959232, Walmart growth FY2016 0.005648, Sam's Club
  GM FY2025 0.113487 – all equal the sheet to 6 decimals.
- **IFERROR masking:** all **114** `n/a` cells were traced to their inputs; in every case at least one
  input is genuinely `n/a` on Raw Data (Sam's Club balance sheet, Whole Foods after FY2017, operating
  leases before ASC 842, FY2015 growth base). 0 cells hide a computable value.
- **Hardcodes:** no numeric constants on Ratio Calculations, Scorecard, Trend or Executive Summary
  other than the year headers and the Scorecard year input.

## 3. Scorecard logic (Tab 5)

- For all six metrics the Scorecard values equal the Ratio Calculations cells for the selected year,
  the `#n of N` ranks match an independent sort (direction-aware), and the leader/laggard cells name
  the correct companies.
- Conditional-formatting colour scales: red→green for the five "higher is better" metrics,
  **green→red for debt-to-equity and for the composite rank** (lower is better). All seven rules
  point the right way.
- Composite rank is computed only for the three full filers (note text corrected to say so).

## 4. Trend charts (Tab 6)

- All six charts reference helper rows spanning FY2016–FY2025 (10 category points, columns B:K), and
  each helper row was traced back to the Ratio Calculations row of the same company (0 mismatches).
- Series labels: Walmart, Costco, Kroger, Sam's Club (only on charts where it has data), Whole
  Foods, plus the "FY2020–23 window" band. Titles and axis titles name the metric; axis number
  formats match the metric (percent or "x").
- Chart layout overlap reported by the user was fixed (charts anchored at A/K on a 21-row pitch).

## 5. Cross-tab consistency

- Ratio tab ↔ Raw Data: all formulas read named ranges on Raw Data (no copied values).
- Scorecard ↔ Ratio tab: value-for-value equal (see §3).
- Executive Summary ↔ model: every number in the narrative is a formula into the same named ranges,
  so it cannot drift. Interpretive claims were checked against the data:
  - "Costco has de-levered every year since FY2021" – D/E 0.47, 0.40, 0.32, 0.31, 0.25 ✔
  - "Walmart D/E in a 0.47–0.73x band" – min 0.466 (FY2021), max 0.729 (FY2018, after fix #2) ✔
  - "Kroger revenue flat since FY2022" – 148.3, 150.0, 147.1, 147.6 ($B) ✔
  - "Walmart FY2022 gross and operating margins the lowest of the decade" – 23.5% and 3.4% are the
    decade minima ✔
  - "Costco led growth in nearly every year" – led 8 of 10 years (Kroger led FY2016; FY2024 tie
    with Walmart at 5.0%) ✔
  - Kroger drivers ($10.5B debt issued, $4.2B + $2.7B buybacks, $2.7B charges, equity $11.6B→$5.9B)
    – each is a cited XBRL fact on Raw Data "Supporting facts" ✔

## 6. Accounting comparability

Inventory-policy statements were checked against the 10-K text (Note 1 / MD&A):

| Company | Workbook statement | 10-K text | Result |
|---|---|---|---|
| Walmart | U.S. RIM/LIFO; Sam's Club weighted-average LIFO; International FIFO | FY2025 10-K Note 1 – identical | ✔ |
| Walmart | LIFO ≈ FIFO disclosure | "inventories valued at LIFO approximated … FIFO" appears through the FY2021 10-K (Jan-2022); FY2022+ give sensitivity language only | corrected (finding #4) |
| Costco | U.S. LIFO; Canada FIFO cost method; Other International FIFO retail method | FY2025 10-K Note 1 – identical | ✔ |
| Costco | LIFO effect | FY2022: 19 bp charge; FY2023 smaller charge; FY2024 immaterial benefit; FY2025 7 bp charge | corrected (finding #5) |
| Kroger | ~91% LIFO, link-chain dollar-value; fuel FIFO | "approximately 91% of inventories in 2025 and 92% in 2024 … LIFO"; LIFO charge $157M (2025) / $95M (2024); reserve $2,553M | ✔ |
| Whole Foods | LIFO | FY2017 10-K: LIFO reserves $47M; LIFO expense $5M | ✔ |

**Distortion assessment.** Kroger is the only filer with a LIFO reserve large enough to move a ratio:
restating to FIFO would raise FY2025 inventory (and current assets) by $2.55B, lifting its current
ratio from 0.80x to ~0.94x – still the lowest of the three, so the ranking is unaffected – and would
lift FY2021–FY2023 gross margin by roughly 0.2–0.4 pp in the years the reserve grew. Costco's FY2022
LIFO charge (19 bp) explains about a third of that year's 60 bp gross-margin dip; the resilience
conclusion (Costco absorbed inflation best) survives because its operating and net margins still rose.
Walmart's LIFO reserve was nil through FY2021 and is undisclosed since, so no adjustment is possible;
the workbook says so. Whole Foods' cost line includes occupancy costs, so its gross-margin level is
excluded from cross-company comparison and only its own two-year trend is used.

Other policy items verified: total equity includes NCI (Walmart $6,270M FY2025, tagged
MinorityInterest); net income is parent-attributable (NetIncomeLoss); ASC 842 adoption dates
(FY2019; Costco FY2020) are consistent with the first non-zero operating-lease facts; Sam's Club cost
of revenue first appears with the FY2024 10-K comparatives (ASU 2023-07).

## Re-running the audit

```
.venv\Scripts\python -m src.audit_raw          # frames API cross-check -> data/audit_raw.csv
.venv\Scripts\python -m src.audit_instances    # instance-document cross-check -> data/audit_instances.csv
.venv\Scripts\python -m pytest -q              # 18 checks incl. workbook tie-outs
```
