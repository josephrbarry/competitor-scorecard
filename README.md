# Competitor Scorecard: Walmart, Costco, Kroger & Sam's Club

**A personal portfolio project by Ryan Barry.** Built from public SEC filings
only; not an H-E-B work product.

**Deliverable:** `output/Competitor_Scorecard.xlsx` - a live-formula Excel
workbook comparing Walmart, Costco and Kroger (full 10-K coverage, fiscal
2016-2025) with Sam's Club and Whole Foods on a best-effort basis.

## The three questions it answers

1. **Capital structure** - who is financed most conservatively (debt-to-equity
   since 2016), and is anyone levering up for growth or buybacks?
2. **Resilience 2020-2023** - how did margins and the current ratio hold
   through COVID and the inflation spike; who absorbed the shock best?
3. **Margin pressure** - who has shown the most margin pressure since 2016,
   and is it cost, pricing, or mix?

## Workbook tabs

| Tab | Purpose |
|---|---|
| Cover | Title page |
| Executive Summary | Findings against the three questions, trend shifts, caveats |
| Raw Data | Revenue, COGS, Net Income, Current Assets/Liabilities, Total Debt, Equity - with SEC citation per cell, named ranges per block |
| Ratio Calculations | Gross margin, net margin, current ratio, D/E, revenue growth - XLOOKUP + IFERROR against named ranges |
| Scorecard | Latest-year ranking per metric with conditional formatting and takeaways |
| Trend | Native Excel line charts 2016-2025 with the 2020-2023 window highlighted |
| Methodology & Tools | Sources, techniques, assumptions, accounting comparability (LIFO vs FIFO) |

## Data coverage

| Company | Coverage | Note |
|---|---|---|
| Walmart, Costco, Kroger | Full | Standalone 10-Ks, all seven inputs, FY2016-FY2025 |
| Sam's Club | Segment only | Net sales and operating income from Walmart's segment note; no balance sheet |
| Whole Foods | Partial | Standalone 10-Ks FY2016-FY2017 only; Amazon acquired it 2017-08-28. FY2018+ only "Physical stores" net sales from Amazon's 10-K |

Missing years are flagged in the workbook, never estimated.

## Build

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env        # then set SEC_USER_AGENT="Name email"
.venv\Scripts\python -m src.pull_data
.venv\Scripts\python -m src.build_workbook
```

## Pipeline

- `src/edgar.py` - throttled, cached, manifest-logged SEC EDGAR client
- `src/pull_data.py` - companyfacts XBRL -> `data/inputs.csv` with tag, accession and filing date per value
- `src/build_workbook.py` - openpyxl build of the seven tabs; every downstream cell is a formula
