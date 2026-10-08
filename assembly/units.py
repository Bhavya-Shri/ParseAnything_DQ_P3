"""Attach crore, lakh, million, billion, and percent onto numeric content.

P3 leaves unit and scale empty. This runs after extraction, before P4.
"""

import re


_UNITS = (
    (re.compile(r"\bcrores?\b", re.I), "crore"),
    (re.compile(r"\blakhs?\b", re.I), "lakh"),
    (re.compile(r"\bmillions?\b", re.I), "million"),
    (re.compile(r"\bbillions?\b", re.I), "billion"),
    (re.compile(r"\bpercent\b|%", re.I), "percent"),
)

_YEAR_HEADER = re.compile(r"year|date|\bfy\b", re.I)


def _unit_in_text(text: str) -> str | None:
    for pattern, name in _UNITS:
        if pattern.search(text or ""):
            return name
    return None


def _text_of(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        parts = [str(content.get("text") or ""), str(content.get("title") or "")]
        return " ".join(part for part in parts if part)
    return ""


def _is_year(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return 1900 <= float(value) <= 2100 and float(value).is_integer()


def _write_unit(target: dict, unit: str) -> None:
    if target.get("unit") is None:
        target["unit"] = unit
        target["scale"] = unit


def _apply_table(block: dict, page_unit: str | None) -> None:
    content = block.get("content")
    if not isinstance(content, dict):
        return
    headers = content.get("header_rows") or []
    header = headers[0] if headers else []
    for row in content.get("rows") or []:
        for index, cell in enumerate(row.get("cells") or []):
            if not isinstance(cell, dict) or cell.get("value") is None:
                continue
            column = header[index] if index < len(header) else ""
            column_unit = _unit_in_text(str(column))
            if _YEAR_HEADER.search(str(column)) or _is_year(cell.get("value")):
                if column_unit is None:
                    continue
            unit = column_unit or page_unit
            if unit:
                _write_unit(cell, unit)


def _apply_chart(block: dict, page_unit: str | None) -> None:
    content = block.get("content")
    if not isinstance(content, dict):
        return
    axis = content.get("y_axis")
    title_unit = _unit_in_text(str(content.get("title") or ""))
    unit = title_unit or page_unit
    if isinstance(axis, dict) and unit:
        _write_unit(axis, unit)


def stamp_table_columns(blocks: list[dict]) -> list[dict]:
    """Give the merger a column count so unrelated tables stay apart."""
    for block in blocks:
        if block.get("type") != "table":
            continue
        content = block.get("content") or {}
        headers = content.get("header_rows") or []
        if not headers:
            continue
        metadata = dict(block.get("metadata") or {})
        metadata["column_count"] = len(headers[0])
        block["metadata"] = metadata
    return blocks


def apply_units(blocks: list[dict]) -> list[dict]:
    page_units: dict = {}
    for block in blocks:
        if block.get("type") not in {"paragraph", "heading", "caption", "list", "header", "footer"}:
            continue
        unit = _unit_in_text(_text_of(block))
        if unit is None:
            continue
        page_units.setdefault(block.get("page_start"), unit)
        content = block.get("content")
        if isinstance(content, dict):
            _write_unit(content, unit)
    for block in blocks:
        unit = page_units.get(block.get("page_start"))
        if block.get("type") == "table":
            _apply_table(block, unit)
        elif block.get("type") == "chart":
            _apply_chart(block, unit)
    return blocks
