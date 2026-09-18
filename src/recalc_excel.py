"""
Recalculate a workbook in Excel (via COM) so every formula has a cached
value, then report any cells showing an error.

openpyxl writes formulas as text with no results; Excel computes them on
open. Running this after build_workbook.py means the saved file opens with
values already present (previewers, pandas, and the tie-out test all read
cached values) and gives a real "zero formula errors" check.

Run:  .venv\\Scripts\\python -m src.recalc_excel output/Competitor_Scorecard.xlsx
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import win32com.client

XL_CELL_TYPE_FORMULAS = -4123
XL_ERRORS = 16


XL_VALUE, XL_CATEGORY, XL_PRIMARY, XL_SECONDARY, XL_NONE = 2, 1, 1, 2, -4142


def polish_charts(wb) -> int:
    """Finish the Trend combo charts inside Excel.

    openpyxl writes the shaded FY2020-23 band and the ratio lines on shared axes.
    Here the band series is moved to a secondary value axis fixed at 0-1 and that
    axis is hidden, so the band always fills the plot height without touching
    the ratio scale. Done in Excel because Excel reads openpyxl's own
    secondary-axis XML as a deleted primary axis.
    """
    n = 0
    try:
        ws = wb.Worksheets("Trend")
    except Exception:
        return 0
    for i in range(1, ws.ChartObjects().Count + 1):
        ch = ws.ChartObjects(i).Chart
        band = ch.SeriesCollection(1)
        for k in range(2, ch.SeriesCollection().Count + 1):
            ch.SeriesCollection(k).AxisGroup = XL_PRIMARY
        band.AxisGroup = XL_SECONDARY
        ax2 = ch.Axes(XL_VALUE, XL_SECONDARY)
        ax2.MinimumScale, ax2.MaximumScale = 0, 1
        ax2.TickLabelPosition = XL_NONE
        ax2.MajorTickMark = XL_NONE
        ax2.Format.Line.Visible = 0
        ax2.HasMajorGridlines = False
        ax1 = ch.Axes(XL_VALUE, XL_PRIMARY)
        ax1.HasMajorGridlines = True
        ax1.MajorGridlines.Format.Line.ForeColor.RGB = 0xD9D9D9
        n += 1
    return n


def recalc(path: Path) -> dict:
    path = path.resolve()
    xl = win32com.client.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    try:
        wb = xl.Workbooks.Open(str(path))
        n_charts = polish_charts(wb)
        xl.CalculateFullRebuild()
        errors: dict[str, list[str]] = {}
        intentional: list[str] = []
        n_formulas = 0
        for ws in wb.Worksheets:
            try:
                formulas = ws.UsedRange.SpecialCells(XL_CELL_TYPE_FORMULAS)
            except Exception:
                continue  # no formulas on this sheet
            n_formulas += formulas.Count
            try:
                bad = formulas.SpecialCells(XL_CELL_TYPE_FORMULAS, XL_ERRORS)
            except Exception:
                continue
            for cell in bad:
                if str(cell.Text) == "#N/A" and "NA()" in str(cell.Formula):
                    intentional.append(f"{ws.Name}!{cell.GetAddress(False, False)}")  # chart helper: NA() makes Excel skip the point
                    continue
                errors.setdefault(str(cell.Text), []).append(f"{ws.Name}!{cell.GetAddress(False, False)}")
        wb.Save()
        wb.Close(SaveChanges=False)
    finally:
        xl.Quit()
    total_errors = sum(len(v) for v in errors.values())
    return {
        "status": "errors_found" if total_errors else "success",
        "charts_polished": n_charts,
        "total_formulas": n_formulas,
        "total_errors": total_errors,
        "error_summary": {k: v[:50] for k, v in errors.items()},
        "intentional_na_chart_gaps": len(intentional),
    }


if __name__ == "__main__":
    result = recalc(Path(sys.argv[1]))
    print(json.dumps(result, indent=1))
    sys.exit(0)
