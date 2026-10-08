"""Find ruled tables, bar charts, and formula lines from the PDF itself.

These signals decide the route before a layout model is asked to look.
"""

import re

from routing.layout_checks import valid_bbox
from routing.route_models import PageProfile, Region


def _clean(text: str) -> str:
    return " ".join(str(text).split())


def _is_formula(text: str) -> bool:
    compact = _clean(text)
    if not compact or len(compact) > 60 or len(compact.split()) > 8:
        return False
    return bool(re.search(r"\^|_|\\[A-Za-z]+", compact))


def _drawing_rects(page) -> list[dict]:
    rects = []
    try:
        drawings = page.get_drawings()
    except Exception:
        return rects
    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None or rect.width < 8 or rect.height < 8:
            continue
        box = [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]
        if not valid_bbox(box):
            continue
        rects.append({"bbox": box, "filled": drawing.get("fill") is not None})
    return rects


def _cluster_rows(rects: list[dict]) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for rect in sorted(rects, key=lambda item: (item["bbox"][1], item["bbox"][0])):
        placed = False
        for row in rows:
            if abs(rect["bbox"][1] - row[0]["bbox"][1]) <= 3:
                row.append(rect)
                placed = True
                break
        if not placed:
            rows.append([rect])
    return rows


def _union(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _table_box(rects: list[dict]) -> list[float] | None:
    unfilled = [rect for rect in rects if not rect["filled"]]
    rows = [row for row in _cluster_rows(unfilled) if len(row) >= 2]
    if len(rows) < 2:
        return None
    widths = [row[0]["bbox"][2] - row[0]["bbox"][0] for row in rows]
    if max(widths) - min(widths) > 4:
        return None
    return _union([rect["bbox"] for row in rows for rect in row])


def _chart_box(rects: list[dict]) -> list[float] | None:
    filled = [rect for rect in rects if rect["filled"]]
    bars = [
        rect
        for rect in filled
        if (rect["bbox"][3] - rect["bbox"][1]) > (rect["bbox"][2] - rect["bbox"][0])
        and (rect["bbox"][3] - rect["bbox"][1]) >= 20
    ]
    if len(bars) < 2:
        return None
    baseline = max(rect["bbox"][3] for rect in bars)
    standing = [rect for rect in bars if abs(rect["bbox"][3] - baseline) <= 2]
    if len(standing) < 2:
        return None
    heights = [rect["bbox"][3] - rect["bbox"][1] for rect in standing]
    if max(heights) - min(heights) < 8:
        return None
    return _union([rect["bbox"] for rect in standing])


def _text_blocks(page) -> list[tuple[str, list[float]]]:
    found = []
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return found
    for block in blocks:
        if len(block) < 5:
            continue
        text = _clean(block[4])
        if not text:
            continue
        box = [float(value) for value in block[:4]]
        if valid_bbox(box):
            found.append((text, box))
    return found


def inspect_page(page) -> dict:
    rects = _drawing_rects(page)
    texts = _text_blocks(page)
    return {
        "has_tables": _table_box(rects) is not None,
        "has_chart": _chart_box(rects) is not None,
        "has_formula": any(_is_formula(text) for text, _box in texts),
    }


def _center_inside(box: list[float], outer: list[float]) -> bool:
    cx = (box[0] + box[2]) / 2
    cy = (box[1] + box[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def _furniture(box: list[float], page_height: float) -> tuple[bool, bool]:
    if page_height <= 0:
        return False, False
    center_y = (box[1] + box[3]) / 2
    return center_y <= page_height * 0.07, center_y >= page_height * 0.93


def structural_regions(page, profile: PageProfile) -> list[Region]:
    """Table and chart regions. Formula lines stay with the text detector."""
    rects = _drawing_rects(page)
    regions = []
    table_box = _table_box(rects)
    if table_box is not None:
        regions.append(
            Region(
                region_id=f"p{profile.page_number}_table_0",
                page_number=profile.page_number,
                region_type="table",
                bbox=table_box,
                confidence=0.9,
                source="pymupdf",
                is_full_width=False,
            )
        )
    chart_box = _chart_box(rects)
    if chart_box is not None:
        extra = []
        for text, box in _text_blocks(page):
            center_x = (box[0] + box[2]) / 2
            above = 0 <= chart_box[1] - box[3] <= 40
            below = 0 <= box[1] - chart_box[3] <= 40
            caption = (
                re.search(r"\bfigure\b", text, re.I)
                and box[3] <= chart_box[1]
                and chart_box[1] - box[3] <= 220
            )
            in_span = chart_box[0] - 20 <= center_x <= chart_box[2] + 20
            if in_span and (above or below or caption):
                extra.append(box)
        if extra:
            chart_box = _union([chart_box, *extra])
        regions.append(
            Region(
                region_id=f"p{profile.page_number}_chart_0",
                page_number=profile.page_number,
                region_type="chart",
                bbox=chart_box,
                confidence=0.9,
                source="pymupdf",
                is_full_width=False,
            )
        )
    return regions


def covered_by_structure(box: list[float], regions: list[Region]) -> bool:
    return any(
        region.region_type in {"table", "chart"} and _center_inside(box, region.bbox)
        for region in regions
    )


def formula_or_furniture(text: str, box: list[float], page_height: float) -> tuple[str, bool, bool]:
    is_header, is_footer = _furniture(box, page_height)
    if _is_formula(text):
        return "formula", is_header, is_footer
    return "", is_header, is_footer
