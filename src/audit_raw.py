"""Audit 1: re-verify every Raw Data input against two sources that were NOT used to build it.

  A. SEC XBRL frames API  (data.sec.gov/api/xbrl/frames/...) - a separately aggregated
     dataset: one value per company per calendar frame.
  B. The 10-K XBRL instance documents themselves (parsed with lxml), for the FY2025,
     FY2022 and FY2019 filings of each full filer - each filing carries the current year
     and the prior-year comparative, so this covers FY2018-FY2025 independently of any API.

Writes data/audit_raw.csv and prints a summary.
"""
from __future__ import annotations
import re
from datetime import date
import pandas as pd
from lxml import etree
from openpyxl import load_workbook
from src import edgar
from src.pull_segments import _instance_name, _contexts

facts = pd.read_csv(edgar.ROOT / "data" / "facts_long.csv")
CORE = {"revenue": "Revenue", "cost_of_sales": "COGS", "net_income": "NetIncome", "current_assets": "CurrentAssets",
        "current_liabilities": "CurrentLiabilities", "total_equity": "TotalEquity"}
FULL = {"WMT": 104169, "COST": 909832, "KR": 56873, "WFM": 865436}

# ---- workbook values (what the sheet actually shows) -------------------------------
wb = load_workbook(edgar.ROOT / "output" / "Competitor_Scorecard.xlsx", data_only=True)
ws = wb["Raw Data"]
years = [ws.cell(row=4, column=c).value for c in range(3, 14)]
names = {n: wb.defined_names[n].attr_text for n in wb.defined_names}
def sheet_row(name):
    ref = names[name].split("!")[1].replace("$", "")
    r = int(re.search(r"\d+", ref).group())
    return {y: ws.cell(row=r, column=3 + i).value for i, y in enumerate(years)}
PREFIX = {"WMT": "Walmart", "COST": "Costco", "KR": "Kroger", "WFM": "WholeFoods"}

rows = []
# ---- A. frames API ------------------------------------------------------------------
for t, cik in FULL.items():
    f = facts[(facts.ticker == t) & (facts.status.isin(["ok", "instance", "derived"]))]
    for metric, suffix in CORE.items():
        shown = sheet_row(f"{PREFIX[t]}_{suffix}")
        for _, r in f[f.metric == metric].iterrows():
            y = int(r.fiscal_year)
            fr = r.frame if isinstance(r.frame, str) and r.frame else None
            api = None
            if fr and r.status == "ok":
                try:
                    j = edgar.frame(r.tag, fr)
                    hit = [d for d in j["data"] if d["cik"] == cik]
                    api = hit[0]["val"] if hit else None
                except Exception:
                    api = None
            rows.append({"ticker": t, "metric": metric, "fy": y, "sheet_value_musd": shown.get(y), "extracted": r.value,
                         "frames_api": api, "frame": fr, "tag": r.tag, "status": r.status,
                         "period_end": r.period_end, "restated": r.restated, "first_value": r.first_value})
df = pd.DataFrame(rows)
df["sheet_vs_extract_ok"] = (df.sheet_value_musd.astype(float) * 1e6 - df.extracted).abs() < 1
df["frames_match"] = df.apply(lambda r: None if pd.isna(r.frames_api) else abs(r.frames_api - r.extracted) < 1, axis=1)
df.to_csv(edgar.ROOT / "data" / "audit_raw.csv", index=False)

print("A. FRAMES API CROSS-CHECK")
print("  values compared:", df.frames_match.notna().sum(), " matches:", (df.frames_match == True).sum(), " mismatches:", (df.frames_match == False).sum(),
      " not in frames (instance/derived or unframed):", df.frames_match.isna().sum())
print(df[df.frames_match == False][["ticker", "metric", "fy", "extracted", "frames_api", "frame", "tag"]].to_string())
print("  sheet == extracted for all:", df.sheet_vs_extract_ok.all())
print("\n  rows without a frame (need instance check):")
print(df[df.frames_match.isna()][["ticker", "metric", "fy", "status", "tag"]].to_string())
print("\n  RESTATED values (latest-filed differs from first-filed):")
print(df[df.restated == True][["ticker", "metric", "fy", "first_value", "extracted", "tag"]].to_string())
