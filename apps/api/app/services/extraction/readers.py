"""PDF text and XLSX BOQ readers. No macros, formulas or embedded code are executed."""

from __future__ import annotations

import io
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.extraction.nit import PageText
from app.services.money import rupees_to_paise

MAX_PDF_PAGES = 300
MAX_BOQ_ROWS = 5000


def pdf_pages(data: bytes) -> list[PageText]:
    import pymupdf

    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("Password-protected PDFs are not supported.")
        return [PageText(i + 1, page.get_text("text")) for i, page in enumerate(doc) if i < MAX_PDF_PAGES]


_HEADER_HINTS = {
    "item": ("item no", "s.no", "sl", "sr", "item", "क्र"),
    "description": ("description", "particular", "विवरण", "item of work"),
    "unit": ("unit", "इकाई"),
    "quantity": ("qty", "quantity", "मात्रा"),
    "rate": ("rate", "दर"),
    "amount": ("amount", "total", "राशि"),
}


def _num(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v).replace(",", "").strip())
    except InvalidOperation:
        return None


def read_boq(data: bytes) -> dict[str, Any]:
    """Summarise the first sheet that looks like a BOQ. Formulas are read as cached values only."""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_vba=False, keep_links=False)
    try:
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True, max_row=MAX_BOQ_ROWS)
            header_idx: dict[str, int] | None = None
            items: list[dict[str, Any]] = []
            total = Decimal(0)
            for row in rows:
                cells = [str(c).strip().lower() if c is not None else "" for c in row]
                if header_idx is None:
                    found = {
                        key: i
                        for key, hints in _HEADER_HINTS.items()
                        for i, c in enumerate(cells)
                        if c and any(c.startswith(h) for h in hints)
                    }
                    if "description" in found and ("quantity" in found or "amount" in found):
                        header_idx = found
                    continue
                desc = row[header_idx["description"]] if header_idx["description"] < len(row) else None
                if not desc:
                    continue
                qty = _num(row[header_idx["quantity"]]) if "quantity" in header_idx else None
                rate = _num(row[header_idx["rate"]]) if "rate" in header_idx else None
                amount = _num(row[header_idx["amount"]]) if "amount" in header_idx else None
                if amount is None and qty is not None and rate is not None:
                    amount = qty * rate
                if amount is not None and "total" not in str(desc).lower():
                    total += amount
                items.append(
                    {
                        "item": str(row[header_idx["item"]]) if "item" in header_idx and row[header_idx["item"]] is not None else None,
                        "description": str(desc)[:300],
                        "unit": str(row[header_idx["unit"]]) if "unit" in header_idx and row[header_idx["unit"]] is not None else None,
                        "quantity": str(qty) if qty is not None else None,
                        "rate": str(rate) if rate is not None else None,
                        "amount": str(amount) if amount is not None else None,
                    }
                )
            if header_idx is not None:
                return {
                    "sheet": ws.title,
                    "item_count": len(items),
                    "total_paise": rupees_to_paise(total) if total else None,
                    "items_preview": items[:25],
                }
        return {"sheet": None, "item_count": 0, "total_paise": None, "items_preview": [],
                "warning": "No BOQ header row (description + quantity/amount) found."}
    finally:
        wb.close()
