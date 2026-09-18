"""Tie the recalculated workbook back to an independent pandas computation."""
import pandas as pd
import pytest
from openpyxl import load_workbook

from src import edgar

WB = edgar.ROOT / "output" / "Competitor_Scorecard.xlsx"
pytestmark = pytest.mark.skipif(not WB.exists(), reason="workbook not built")


@pytest.fixture(scope="module")
def wb():
    return load_workbook(WB, data_only=True)


def ratio_rows(ws, title):
    """Return {company: [FY2016..FY2025 values]} for one ratio block."""
    out, active = {}, False
    for r in range(5, ws.max_row + 1):
        a = ws[f"A{r}"].value
        if a and str(a).startswith(title):
            active = True
            continue
        if active:
            if a is None:
                break
            out[a] = [ws.cell(row=r, column=c).value for c in range(2, 12)]
    return out


def test_walmart_fy2018_capital_leases_in_total_debt():
    f = pd.read_csv(edgar.ROOT / "data" / "facts_long.csv")
    w = f[(f.ticker == "WMT") & (f.fiscal_year == 2018)].set_index("metric").value
    assert w["finance_lease_current"] + w["finance_lease_noncurrent"] == w["finance_lease_total"] == 7_412_000_000


def test_gross_margin_ties_to_pandas(wb):
    f = pd.read_csv(edgar.ROOT / "data" / "facts_long.csv")
    gm = ratio_rows(wb["Ratio Calculations"], "Gross profit margin")
    for t, name in [("WMT", "Walmart"), ("COST", "Costco"), ("KR", "Kroger")]:
        w = f[f.ticker == t].pivot(index="fiscal_year", columns="metric", values="value")
        expected = ((w.revenue - w.cost_of_sales) / w.revenue).loc[2016:2025].tolist()
        assert gm[name] == pytest.approx(expected, abs=1e-9), name


def test_debt_to_equity_ties_to_policy(wb):
    de = ratio_rows(wb["Ratio Calculations"], "Debt-to-equity")
    # spot values computed by hand from the 10-K balance sheets (USD millions)
    assert de["Walmart"][-1] == pytest.approx((6596 + 3542 + 34624 + 856 + 5905) / 105887, abs=1e-4)
    assert de["Kroger"][-1] == pytest.approx((1366 + 14509 + 436 + 1255) / 5936, abs=1e-4)
    assert de["Costco"][-1] == pytest.approx((75 + 5713 + 78 + 1401) / 29164, abs=1e-4)
    assert de["Kroger"][0] == pytest.approx((2252 + 11825) / 6710, abs=1e-4)   # FY2016 combined LTD+capital lease lines


def test_no_error_values_anywhere(wb):
    bad = [f"{ws.title}!{c.coordinate}" for ws in wb.worksheets for row in ws.iter_rows() for c in row
           if isinstance(c.value, str) and c.value in ("#REF!", "#DIV/0!", "#NAME?", "#VALUE!", "#NUM!", "#NULL!")]
    assert bad == []


def test_missing_data_is_flagged_not_zero(wb):
    gm = ratio_rows(wb["Ratio Calculations"], "Gross profit margin")
    assert gm["Whole Foods"][2:] == ["n/a"] * 8
    assert gm["Sam's Club"][:6] == ["n/a"] * 6
