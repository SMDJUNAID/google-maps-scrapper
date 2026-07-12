"""Export helpers for scraped business listings."""

from __future__ import annotations

import io
import json
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

from scraper.models import BusinessListing

FIELD_LABELS = {
    "name": "Name",
    "address": "Address",
    "phone": "Phone",
    "website": "Website",
    "rating": "Rating",
    "reviews_count": "Reviews",
    "category": "Category",
    "place_url": "Google Maps URL",
    "search_query": "Search Query",
    "country": "Country",
    "industry": "Industry",
    "email": "Email",
    "linkedin": "LinkedIn",
    "instagram": "Instagram",
    "whatsapp": "WhatsApp",
}

FIELDNAMES = list(BusinessListing.__dataclass_fields__.keys())


def listings_to_dicts(listings: list[BusinessListing]) -> list[dict[str, Any]]:
    return [item.to_dict() for item in listings]


def to_json_bytes(listings: list[BusinessListing]) -> bytes:
    return json.dumps(listings_to_dicts(listings), indent=2, ensure_ascii=False).encode("utf-8")


def to_json_bytes_from_dicts(data: list[dict[str, Any]]) -> io.BytesIO:
    payload = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    buffer = io.BytesIO(payload)
    buffer.seek(0)
    return buffer


def _write_excel_sheet(sheet, data: list[dict[str, Any]]) -> None:
    headers = [FIELD_LABELS.get(field, field) for field in FIELDNAMES]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for row in data:
        sheet.append([row.get(field, "") for field in FIELDNAMES])

    for column_cells in sheet.columns:
        max_length = 0
        column_letter = column_cells[0].column_letter
        for cell in column_cells:
            value = str(cell.value) if cell.value is not None else ""
            max_length = max(max_length, len(value))
        sheet.column_dimensions[column_letter].width = min(max_length + 2, 50)


def to_excel_bytes(listings: list[BusinessListing]) -> bytes:
    return to_excel_bytes_from_dicts(listings_to_dicts(listings)).read()


def to_excel_bytes_from_dicts(data: list[dict[str, Any]]) -> io.BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Results"
    _write_excel_sheet(sheet, data)

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer
