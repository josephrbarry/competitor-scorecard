"""Sanity checks on the extracted data before anything reaches the workbook."""
import pandas as pd
import pytest

from src import edgar

FACTS = pd.read_csv(edgar.ROOT / "data" / "facts_long.csv")
SEGS = pd.read_csv(edgar.ROOT / "data" / "segments_long.csv")
CORE = ["revenue", "cost_of_sales", "net_income", "current_assets", "current_liabilities", "total_equity"]


def wide(ticker):
    f = FACTS[FACTS.ticker == ticker]
    return f.pivot(index="fiscal_year", columns="metric", values="value")


@pytest.mark.parametrize("ticker", ["WMT", "COST", "KR"])
def test_full_filers_have_every_core_input_every_year(ticker):
    f = FACTS[(FACTS.ticker == ticker) & FACTS.metric.isin(CORE)]
    assert set(f.fiscal_year) == set(range(2015, 2026))
    assert (f.status == "ok").all(), f[f.status != "ok"]


def test_whole_foods_standalone_years_only():
    f = FACTS[(FACTS.ticker == "WFM") & FACTS.metric.isin(CORE)]
    assert set(f[f.status.isin(["ok", "derived"])].fiscal_year) == {2015, 2016, 2017}
    assert (f[f.fiscal_year >= 2018].status == "no 10-K period").all()


@pytest.mark.parametrize("ticker", ["WMT", "COST", "KR", "WFM"])
def test_accounting_identities(ticker):
    w = wide(ticker).dropna(subset=["revenue"])
    assert (w.cost_of_sales < w.revenue).all()
    assert (w.current_assets < w.total_assets).all()
    assert (w.total_equity < w.total_assets).all()
    assert (w.net_income.abs() < w.revenue * 0.2).all()


def test_overrides_are_flagged_not_hidden():
    o = FACTS[FACTS.status.isin(["instance", "derived"])]
    assert len(o) == 7
    assert o.note.notna().all() and o.accession.notna().all()


def test_whole_foods_cogs_derivation_ties():
    w = wide("WFM")
    # COGS was derived as Sales - GrossProfit; Sales - COGS must equal the tagged gross profit
    assert w.loc[2017, "revenue"] - w.loc[2017, "cost_of_sales"] == 5_397_000_000
    assert w.loc[2016, "revenue"] - w.loc[2016, "cost_of_sales"] == 5_411_000_000


def test_sams_club_segment_complete():
    s = SEGS[SEGS.ticker == "SAMS"].pivot(index="fiscal_year", columns="metric", values="value")
    assert set(s.index) == set(range(2015, 2026))
    assert s.revenue.notna().all() and s.operating_income.notna().all()
    assert s.cost_of_sales.dropna().index.min() == 2022   # ASU 2023-07 comparatives only
    # Sam's Club is a segment of Walmart: its sales must be a minority of Walmart's
    wmt = wide("WMT")
    assert ((s.revenue / wmt.revenue) < 0.25).all()


def test_amazon_physical_stores_post_acquisition():
    a = SEGS[(SEGS.ticker == "WFM") & (SEGS.metric == "revenue")].set_index("fiscal_year").value
    assert a.loc[2016] == 0                     # pre-acquisition: nothing to report
    assert a.loc[2017] < a.loc[2018] * 0.5      # partial year from 2017-08-28
    assert (a.loc[2018:] > 15e9).all()
