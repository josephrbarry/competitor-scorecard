"""Audit 1B: independent re-read of every core input from the 10-K XBRL instance documents.

For each full filer, every 10-K filed 2017-2026 is parsed with lxml. For each core
tag, the undimensioned fact whose period matches the fiscal year is compared with the
value on the sheet. Because each 10-K carries the prior year as a comparative, most
years are checked in two different filings.
"""
from __future__ import annotations
import pandas as pd
from lxml import etree
from src import edgar
from src.pull_segments import _instance_name, _contexts

facts = pd.read_csv(edgar.ROOT / "data" / "facts_long.csv")
CORE = ["revenue", "cost_of_sales", "net_income", "current_assets", "current_liabilities", "total_equity"]
TAGS = {  # every tag the filers have used for each line, so the check is tag-agnostic
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet", "Revenues"],
    "cost_of_sales": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization", "CostOfGoodsSoldExcludingDepreciationDepletionAndAmortization"],
    "net_income": ["NetIncomeLoss"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "total_equity": ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"],
}
FULL = {"WMT": 104169, "COST": 909832, "KR": 56873, "WFM": 865436}
US = "http://fasb.org/us-gaap/"

rows = []
for t, cik in FULL.items():
    f = facts[(facts.ticker == t) & facts.metric.isin(CORE) & facts.status.isin(["ok", "derived"])]
    periods = {int(r.fiscal_year): (r.period_start if isinstance(r.period_start, str) else None, r.period_end) for _, r in f[f.metric == "revenue"].iterrows()}
    for filing in edgar.list_filings(cik, "10-K"):
        if filing["filingDate"] < "2017-01-01":
            continue
        acc = filing["accessionNumber"]
        name = _instance_name(cik, acc)
        if not name:
            continue
        root = etree.fromstring(edgar.filing_document(cik, acc, name))
        ctxs = _contexts(root)
        found = {}
        for el in root.iter():
            if not isinstance(el.tag, str) or not el.tag.startswith("{" + US):
                continue
            local = el.tag.split("}")[1]
            metric = next((m for m, tags in TAGS.items() if local in tags), None)
            if metric is None or el.text is None:
                continue
            c = ctxs.get(el.get("contextRef"))
            if not c or c["dims"]:
                continue
            for fy, (start, end) in periods.items():
                dur = metric in ("revenue", "cost_of_sales", "net_income")
                if c["end"] == end and ((dur and c["start"] == start) or (not dur and c["start"] is None)):
                    # prefer the total-equity tag incl. NCI when both present
                    key = (metric, fy)
                    pref = TAGS[metric].index(local)
                    if key not in found or pref < found[key][1]:
                        found[key] = (float(el.text), pref, local)
        for (metric, fy), (val, _, tag) in found.items():
            sheet = f[(f.metric == metric) & (f.fiscal_year == fy)]
            if sheet.empty:
                continue
            rows.append({"ticker": t, "metric": metric, "fy": fy, "filing": acc, "filed": filing["filingDate"],
                         "instance_value": val, "instance_tag": tag, "sheet_value": float(sheet.value.iloc[0]), "sheet_tag": sheet.tag.iloc[0]})
df = pd.DataFrame(rows)
df["match"] = (df.instance_value - df.sheet_value).abs() < 1
df.to_csv(edgar.ROOT / "data" / "audit_instances.csv", index=False)
print("B. INSTANCE DOCUMENT CROSS-CHECK")
print("  comparisons:", len(df), " filings parsed:", df.filing.nunique(), " matches:", df.match.sum(), " mismatches:", (~df.match).sum())
cov = df.groupby(["ticker", "metric", "fy"]).match.agg(["count", "all"]).reset_index()
print("  (ticker, metric, year) combinations checked:", len(cov), " of which agree in every filing:", cov["all"].sum())
mm = df[~df.match].sort_values(["ticker", "metric", "fy", "filed"])
print("\n  MISMATCHES (a later filing restated the number - sheet uses latest-filed):")
print(mm[["ticker", "metric", "fy", "filed", "instance_value", "sheet_value", "instance_tag"]].to_string())
# which core (ticker,metric,fy) rows in the sheet were NOT covered by any instance check
core_rows = facts[facts.ticker.isin(FULL) & facts.metric.isin(CORE) & facts.status.isin(["ok", "derived"])]
checked = set(zip(cov.ticker, cov.metric, cov.fy))
missing = [(r.ticker, r.metric, int(r.fiscal_year)) for _, r in core_rows.iterrows() if (r.ticker, r.metric, int(r.fiscal_year)) not in checked]
print("\n  core rows not covered by instance check:", missing)
