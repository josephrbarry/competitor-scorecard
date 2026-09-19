"""
Export reader-facing copies of the workbook for people who will not open Excel:
  docs/Retail_Peer_Benchmarking_summary.pdf  - Cover, Executive Summary, Scorecard, Trend
  docs/*.png                             - page images used in README.md
Run after build + recalc:  .venv\Scripts\python -m src.export_docs
"""
from __future__ import annotations
import os
from pathlib import Path
import fitz  # pymupdf
import win32com.client

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "output" / "Retail_Peer_Benchmarking.xlsx"
DOCS = ROOT / "docs"
XL_TYPE_PDF = 0

def main() -> None:
    xl = win32com.client.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    try:
        wb = xl.Workbooks.Open(str(XLSX))
        # combined reader PDF
        wb.Worksheets(["Cover", "Executive Summary", "Scorecard", "Trend"]).Select()
        wb.ActiveSheet.ExportAsFixedFormat(XL_TYPE_PDF, str(DOCS / "Retail_Peer_Benchmarking_summary.pdf"))
        # single-sheet PDFs -> PNG
        for sheet, stem in [("Cover", "cover"), ("Executive Summary", "executive_summary"), ("Scorecard", "scorecard"), ("Trend", "trend")]:
            tmp = DOCS / f"_{stem}.pdf"
            wb.Worksheets(sheet).Select()
            wb.Worksheets(sheet).ExportAsFixedFormat(XL_TYPE_PDF, str(tmp))
            doc = fitz.open(str(tmp))
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=110)
                out = DOCS / (f"{stem}.png" if len(doc) == 1 else f"{stem}_p{i + 1}.png")
                pix.save(str(out))
                print("wrote", out.name, f"{pix.width}x{pix.height}")
            doc.close()
            tmp.unlink()
        wb.Close(SaveChanges=False)
    finally:
        xl.Quit()

if __name__ == "__main__":
    main()
