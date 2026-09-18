"""
ASC 280 segment extraction from 10-K XBRL instance documents -> data/segments_long.csv.

Sam's Club is not a filer; it is a reportable segment inside Walmart's 10-K.
After Amazon acquired Whole Foods (2017-08-28) the only public Whole Foods
figure is Amazon's "Physical stores" net sales line (disaggregated revenue
under ASC 606, Note 10). Both are DIMENSIONAL facts - a value qualified by an
axis/member such as StatementBusinessSegmentsAxis = wmt:SamsClubUSMember - and
the companyfacts API only returns undimensioned facts, so this script parses
the instance document of each 10-K directly.

Rules mirror pull_data.py: fiscal-year label by SEC frame convention, ~1-year
periods only, latest-filed value wins with the first-filed value retained.

Run:  .venv\Scripts\python -m src.pull_segments
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from lxml import etree

from src import edgar
from src.pull_data import cy_label

OUT = edgar.ROOT / "data" / "segments_long.csv"

NS = {
    "xbrli": "http://www.xbrl.org/2003/instance",
    "xbrldi": "http://xbrl.org/2006/xbrldi",
}

# What to pull: (ticker label, parent CIK, axis, member, {metric: [tags]}, first filing year)
TARGETS = [
    {
        "ticker": "SAMS", "cik": 104169, "parent": "WMT",
        "axis": "us-gaap:StatementBusinessSegmentsAxis",
        "members": ["wmt:SamsClubUSMember", "wmt:SamsClubMember"],   # renamed in the FY2024 10-K
        "metrics": {
            "revenue": ["us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap:SalesRevenueNet", "us-gaap:Revenues"],
            "cost_of_sales": ["us-gaap:CostOfRevenue"],        # disclosed only from the FY2024 10-K (ASU 2023-07)
            "operating_income": ["us-gaap:OperatingIncomeLoss"],
            "total_assets": ["us-gaap:Assets"],
        },
    },
    {
        # Costco NET SALES (merchandise) - its total-revenue tag includes membership fees,
        # which Walmart's and Sam's Club's net sales exclude. Dimensional from FY2018
        # (ASC 606 disaggregation); the undimensioned SalesRevenueNet tag before that.
        "ticker": "COST", "cik": 909832, "parent": "COST",
        "axis": "srt:ProductOrServiceAxis", "members": ["us-gaap:ProductMember"],
        "metrics": {"net_sales": ["us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"]},
        "undimensioned": {"net_sales": ["us-gaap:SalesRevenueNet"]},
    },
    {
        "ticker": "WFM", "cik": 1018724, "parent": "AMZN",
        "axis": "srt:ProductOrServiceAxis", "members": ["amzn:PhysicalStoresMember"],
        "metrics": {
            "revenue": ["us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap:Revenues"],
        },
    },
]


def _instance_name(cik: int, accession: str) -> str | None:
    idx = edgar.filing_index(cik, accession)
    docs = [d["name"] for d in idx["directory"]["item"]]
    for d in docs:
        if d.endswith("_htm.xml"):
            return d
    # pre-inline-XBRL filings: the instance is <ticker>-<date>.xml
    for d in docs:
        if d.endswith(".xml") and not any(s in d for s in ("_cal", "_def", "_lab", "_pre", "FilingSummary", "_htm")):
            return d
    return None


def _contexts(root) -> dict[str, dict]:
    out = {}
    for ctx in root.findall(".//xbrli:context", NS):
        cid = ctx.get("id")
        per = ctx.find("xbrli:period", NS)
        start = per.findtext("xbrli:startDate", None, NS)
        end = per.findtext("xbrli:endDate", None, NS) or per.findtext("xbrli:instant", None, NS)
        dims = {m.get("dimension"): (m.text or "").strip() for m in ctx.findall(".//xbrldi:explicitMember", NS)}
        out[cid] = {"start": start, "end": end, "dims": dims}
    return out


def _qname(tag: str, root) -> str:
    prefix, local = tag.split(":")
    uri = root.nsmap.get(prefix)
    return f"{{{uri}}}{local}" if uri else None


def extract_filing(cik: int, accession: str, filed: str, target: dict) -> list[dict]:
    name = _instance_name(cik, accession)
    if not name:
        return []
    root = etree.fromstring(edgar.filing_document(cik, accession, name))
    ctxs = _contexts(root)
    rows = []
    for metric, tags in target["metrics"].items():
        for tag in tags:
            q = _qname(tag, root)
            if q is None:
                continue
            hits = []
            for el in root.iter(q):
                c = ctxs.get(el.get("contextRef"))
                if not c or c["dims"].get(target["axis"]) not in target["members"]:
                    continue
                # ASU 2023-07 filings add ConsolidationItemsAxis=OperatingSegmentsMember;
                # any other extra dimension (product line, channel) is a sub-split, skip it.
                extra = {k: v for k, v in c["dims"].items() if k != target["axis"]}
                if extra and extra not in ({"srt:ConsolidationItemsAxis": "us-gaap:OperatingSegmentsMember"}, {"us-gaap:ConsolidationItemsAxis": "us-gaap:OperatingSegmentsMember"}):
                    continue
                if el.text is None:
                    continue
                if c["start"]:
                    days = (date.fromisoformat(c["end"]) - date.fromisoformat(c["start"])).days
                    if not 340 <= days <= 380:
                        continue
                    fy = cy_label(c["start"], c["end"])
                else:
                    fy = None  # instants are matched to fiscal years below
                hits.append({"ticker": target["ticker"], "cik": cik, "metric": metric, "fiscal_year": fy,
                             "period_start": c["start"] or "", "period_end": c["end"], "value": float(el.text),
                             "tag": tag, "axis": target["axis"], "member": c["dims"][target["axis"]],
                             "accession": accession, "filed": filed, "instance": name})
            if hits:
                rows += hits
                break
        else:
            # no dimensional fact in this filing: fall back to the plain (pre-ASC 606) tag
            for tag in target.get("undimensioned", {}).get(metric, []):
                q = _qname(tag, root)
                if q is None:
                    continue
                for el in root.iter(q):
                    c = ctxs.get(el.get("contextRef"))
                    if not c or c["dims"] or el.text is None or not c["start"]:
                        continue
                    days = (date.fromisoformat(c["end"]) - date.fromisoformat(c["start"])).days
                    if not 340 <= days <= 380:
                        continue
                    rows.append({"ticker": target["ticker"], "cik": cik, "metric": metric, "fiscal_year": cy_label(c["start"], c["end"]),
                                 "period_start": c["start"], "period_end": c["end"], "value": float(el.text),
                                 "tag": tag, "axis": "", "member": "", "accession": accession, "filed": filed, "instance": name})
    return rows


def main() -> None:
    cfg = edgar.load_config()
    y0 = int(cfg["window"]["first_frame"][2:])
    y1 = int(cfg["window"]["last_frame"][2:])
    all_rows: list[dict] = []
    for t in TARGETS:
        filings = [f for f in edgar.list_filings(t["cik"], "10-K") if f["filingDate"] >= f"{y0 + 1}-01-01"]
        for f in filings:
            all_rows += extract_filing(t["cik"], f["accessionNumber"], f["filingDate"], t)
        print(f"{t['ticker']:<5} {t['members'][0]:<28} filings={len(filings)} facts={sum(r['ticker'] == t['ticker'] for r in all_rows)}")
    df = pd.DataFrame(all_rows)
    # instants: assign fiscal year from the duration facts' period ends
    ends = df[df.fiscal_year.notna()].groupby(["ticker", "period_end"]).fiscal_year.first().to_dict()
    df["fiscal_year"] = df.apply(lambda r: r.fiscal_year if pd.notna(r.fiscal_year) else ends.get((r.ticker, r.period_end)), axis=1)
    df = df[df.fiscal_year.notna()]
    df["fiscal_year"] = df.fiscal_year.astype(int)
    df = df[(df.fiscal_year >= y0) & (df.fiscal_year <= y1)]
    # latest-filed wins; keep first-filed for the audit trail
    df = df.sort_values("filed")
    g = df.groupby(["ticker", "metric", "fiscal_year"])
    out = g.last().reset_index()
    out["first_value"] = g.value.first().values
    out["first_filed"] = g.filed.first().values
    out["n_versions"] = g.size().values
    out["restated"] = out.first_value != out.value
    out["status"] = "ok"
    out.to_csv(OUT, index=False)
    print(f"\nwrote {OUT} ({len(out)} rows)")
    print(out.pivot_table(index="fiscal_year", columns=["ticker", "metric"], values="value", aggfunc="first").div(1e9).round(2).to_string())


if __name__ == "__main__":
    main()
