"""
SEC EDGAR / XBRL extraction: companyfacts JSON -> data/facts_long.csv.

One row per (ticker, metric, fiscal year). For each metric the script walks an
ordered list of us-gaap tags because tag names drift over time - most visibly
at ASC 606 adoption (2018), when SalesRevenueNet / SalesRevenueGoodsNet were
replaced by RevenueFromContractWithCustomerExcludingAssessedTax.

Period rules:
  * Fiscal-year label = SEC frame convention: the calendar year holding the
    midpoint of the period (CY2025 = Walmart "fiscal 2026" = Kroger "2025").
  * Duration metrics (revenue, cost of sales, net income) use 10-K facts that
    cover ~1 year (340-380 days, so 53-week years qualify).
  * Instant metrics (balance sheet) are matched to the fiscal year whose end
    date equals the instant date.
  * The same period is re-tagged in later filings as a comparative column.
    The LATEST-filed value wins (the restated figure); the first-filed value
    and filing are kept alongside so restatements are auditable.
  * A fact's `fy` field is the filing's fiscal year, not the fact's; ignored.

Total Debt is NOT a single tag. Its components are extracted separately and
combined in the workbook by formula under the policy in config/debt_policy.yaml
(ASC 842: operating lease liabilities are excluded from debt, finance leases
are included; the operating-lease liability is carried as a memo line).

Run:  .venv\\Scripts\\python -m src.pull_data
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from src import edgar

OUT = edgar.ROOT / "data" / "facts_long.csv"
OVERRIDES = edgar.ROOT / "data" / "overrides.csv"   # instance-level and derived facts, each with a citation

# metric -> kind + ordered tag candidates. "config:x" pulls the list from
# companies.yaml so per-company tag drift lives in configuration, not code.
METRIC_TAGS: dict[str, dict] = {
    # --- income statement (duration) ---
    "revenue":          {"kind": "duration", "tags": "config:revenue_tags"},
    "cost_of_sales":    {"kind": "duration", "tags": "config:cogs_tags"},
    "net_income":       {"kind": "duration", "tags": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]},
    "operating_income": {"kind": "duration", "tags": ["OperatingIncomeLoss"]},
    # --- balance sheet (instant) ---
    "current_assets":      {"kind": "instant", "tags": ["AssetsCurrent"]},
    "current_liabilities": {"kind": "instant", "tags": ["LiabilitiesCurrent"]},
    "total_equity":        {"kind": "instant", "tags": ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"]},
    "equity_parent_only":  {"kind": "instant", "tags": ["StockholdersEquity"]},
    "total_assets":        {"kind": "instant", "tags": ["Assets"]},
    "inventory":           {"kind": "instant", "tags": ["InventoryNet", "RetailRelatedInventoryMerchandise"]},
    "lifo_reserve":        {"kind": "instant", "tags": ["InventoryLIFOReserve"]},
    # --- debt components (instant); combined by formula, see debt_policy.yaml ---
    "short_term_borrowings":     {"kind": "instant", "tags": ["ShortTermBorrowings", "CommercialPaper"]},
    "ltd_current":               {"kind": "instant", "tags": ["LongTermDebtCurrent"]},
    "ltd_noncurrent":            {"kind": "instant", "tags": ["LongTermDebtNoncurrent"]},
    "ltd_and_leases_current":    {"kind": "instant", "tags": ["LongTermDebtAndCapitalLeaseObligationsCurrent", "LongTermDebtAndFinanceLeaseLiabilitiesCurrent"]},
    "ltd_and_leases_noncurrent": {"kind": "instant", "tags": ["LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndFinanceLeaseLiabilitiesNoncurrent", "LongTermDebtAndCapitalLeaseObligationsNoncurrent"]},
    "finance_lease_current":     {"kind": "instant", "tags": ["FinanceLeaseLiabilityCurrent", "CapitalLeaseObligationsCurrent"]},
    "finance_lease_noncurrent":  {"kind": "instant", "tags": ["FinanceLeaseLiabilityNoncurrent", "CapitalLeaseObligationsNoncurrent"]},
    "finance_lease_total":        {"kind": "instant", "tags": ["FinanceLeaseLiability", "CapitalLeaseObligations"]},
    "operating_lease_current":    {"kind": "instant", "tags": ["OperatingLeaseLiabilityCurrent"]},
    "operating_lease_noncurrent": {"kind": "instant", "tags": ["OperatingLeaseLiabilityNoncurrent"]},
    "operating_lease_total":      {"kind": "instant", "tags": ["OperatingLeaseLiability"]},
}

CORE = ["revenue", "cost_of_sales", "net_income", "current_assets", "current_liabilities", "total_equity"]


def _d(s: str) -> date:
    return date.fromisoformat(s)


def cy_label(start: str, end: str) -> int:
    """SEC frame convention: the calendar year holding the period midpoint."""
    a, b = _d(start), _d(end)
    return (a + (b - a) / 2).year


def _facts(cf: dict, tag: str) -> list[dict]:
    node = cf.get("facts", {}).get("us-gaap", {}).get(tag)
    if not node:
        return []
    out = []
    for unit, rows in node.get("units", {}).items():
        if unit != "USD":
            continue
        for r in rows:
            if r.get("form") in ("10-K", "10-K/A", "10-K405") and r.get("fp") == "FY":
                out.append(dict(r, tag=tag))
    return out


def annual_periods(facts: list[dict]) -> dict[int, tuple[str, str]]:
    """Map fiscal-year label -> (start, end) for ~1-year duration facts."""
    periods: dict[int, tuple[str, str]] = {}
    for f in facts:
        if "start" not in f:
            continue
        days = (_d(f["end"]) - _d(f["start"])).days
        if 340 <= days <= 380:
            periods.setdefault(cy_label(f["start"], f["end"]), (f["start"], f["end"]))
    return periods


def pick(facts: list[dict], start: str | None, end: str) -> dict | None:
    """Latest-filed value for a period; first-filed kept for restatement audit."""
    hits = [f for f in facts if f["end"] == end and (start is None or f.get("start") == start)]
    if not hits:
        return None
    hits.sort(key=lambda f: f["filed"])
    first, last = hits[0], hits[-1]
    return {
        "value": last["val"], "tag": last["tag"], "accession": last["accn"],
        "filed": last["filed"], "frame": last.get("frame", ""),
        "first_value": first["val"], "first_filed": first["filed"],
        "n_versions": len(hits), "restated": first["val"] != last["val"],
    }


def extract_company(ticker: str, cfg: dict, first_year: int, last_year: int) -> list[dict]:
    cf = edgar.companyfacts(cfg["cik"])
    # The fiscal calendar comes from revenue, the one series every filer tags.
    periods: dict[int, tuple[str, str]] = {}
    for t in cfg["revenue_tags"]:
        for y, p in annual_periods(_facts(cf, t)).items():
            periods.setdefault(y, p)
    rows = []
    for y in range(first_year, last_year + 1):
        if y not in periods:
            for metric in METRIC_TAGS:
                rows.append({"ticker": ticker, "cik": cfg["cik"], "metric": metric,
                             "fiscal_year": y, "status": "no 10-K period"})
            continue
        start, end = periods[y]
        for metric, spec in METRIC_TAGS.items():
            tags = spec["tags"]
            if isinstance(tags, str):
                tags = cfg.get(tags.split(":", 1)[1], [])
            found = None
            for t in tags:
                found = pick(_facts(cf, t), start if spec["kind"] == "duration" else None, end)
                if found:
                    break
            row = {"ticker": ticker, "cik": cfg["cik"], "metric": metric, "fiscal_year": y,
                   "period_start": start if spec["kind"] == "duration" else "", "period_end": end,
                   "status": "ok" if found else "not tagged"}
            if found:
                row.update(found)
            rows.append(row)
    return rows


def apply_overrides(df: pd.DataFrame) -> pd.DataFrame:
    """Replace rows the API could not supply with cited instance/derived values.

    An override never silently replaces an API value: it only fills rows whose
    status is 'not tagged', and it keeps its own status ('instance' or
    'derived') so the workbook's notes column shows exactly where it came from.
    """
    if not OVERRIDES.exists():
        return df
    ov = pd.read_csv(OVERRIDES)
    df = df.set_index(["ticker", "metric", "fiscal_year"]).sort_index()
    for _, o in ov.iterrows():
        key = (o.ticker, o.metric, int(o.fiscal_year))
        if key not in df.index:
            raise SystemExit(f"override for unknown row {key}")
        if df.loc[key, "status"] == "ok":
            raise SystemExit(f"override would overwrite an API value at {key}; remove it")
        for col in ["value", "tag", "accession", "filed", "status", "note", "period_end"]:
            df.loc[key, col] = o[col]
    return df.reset_index()


def main() -> None:
    cfg = edgar.load_config()
    y0 = int(cfg["window"]["first_frame"][2:])
    y1 = int(cfg["window"]["last_frame"][2:])
    rows: list[dict] = []
    for ticker, c in cfg["companies"].items():
        if c.get("coverage") == "segment":
            continue  # Sam's Club: dimensional (ASC 280) facts are not in companyfacts; see pull_segments.py
        rows += extract_company(ticker, c, y0, y1)
        print(f"{ticker:<5} {c['name']:<32} rows={sum(r['ticker'] == ticker for r in rows)}")
    df = pd.DataFrame(rows)
    df = apply_overrides(df)
    df.to_csv(OUT, index=False)
    print(f"\nwrote {OUT} ({len(df)} rows)")
    pv = df[df.metric.isin(CORE)].pivot_table(index=["ticker", "fiscal_year"], columns="metric",
                                              values="status", aggfunc="first")
    print("\nCore coverage:")
    print(pv[CORE].to_string())


if __name__ == "__main__":
    main()
