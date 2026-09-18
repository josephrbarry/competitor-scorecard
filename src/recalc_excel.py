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


def recalc(path: Path) -> dict:
    path = path.resolve()
    xl = win32com.client.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    try:
        wb = xl.Workbooks.Open(str(path))
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
        "total_formulas": n_formulas,
        "total_errors": total_errors,
        "error_summary": {k: v[:50] for k, v in errors.items()},
        "intentional_na_chart_gaps": len(intentional),
    }


if __name__ == "__main__":
    result = recalc(Path(sys.argv[1]))
    print(json.dumps(result, indent=1))
    sys.exit(0)
