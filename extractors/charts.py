"""Chart regions become series values. A slide uses the embedded series. A PDF bar chart uses the drawn bars and the numbers printed on them."""

import re
from pathlib import Path

import pymupdf

from extractors.base import Extractor
from extractors.utils import failed_block, make_block, region_field

_FIGURE = re.compile(r"Figure\s+\d+\s*(.*)", re.IGNORECASE)


class ChartExtractor(Extractor):
    name = "chart"

    def can_handle(self, region) -> bool:
        return region_field(region, "route") == "chart"

    def extract(self, region, context) -> list:
        context = context or {}
        path = context.get("file_path")
        if not path:
            return [_fail(region, "Chart extraction needs a file")]
        suffix = Path(path).suffix.lower()
        try:
            if suffix == ".pptx":
                return _pptx_charts(region, path)
            if suffix != ".pdf":
                return [_fail(region, f"No chart reader for {suffix or 'this file'}")]
            return _pdf_chart(region, path, context)
        except Exception as exc:
            return [_fail(region, f"{type(exc).__name__}: {exc}")]


def _pdf_chart(region, path, context) -> list:
    page_number = int(region_field(region, "page", 1) or 1)
    document = pymupdf.open(path)
    try:
        index = page_number - 1 if page_number >= 1 else 0
        if index < 0 or index >= document.page_count:
            raise ValueError(f"Page {page_number} is outside the PDF")
        page = document[index]
        box = _region_box(region, page.rect.width, page.rect.height)
        words = [
            word
            for word in page.get_text("words")
            if _point_inside(((word[0] + word[2]) / 2, (word[1] + word[3]) / 2), box)
        ]
        bars = _vertical_bars(page, box)
    finally:
        document.close()

    points, boxes = _points_from_bars(bars, words)
    caption, caption_box = _caption(words, bars)
    if len(points) >= 2:
        if caption_box:
            boxes.append(caption_box)
        name = _series_name(caption)
        return [
            make_block(
                extractor="chart",
                bbox=_union(boxes),
                page_start=page_number,
                extraction=0.9,
                block_type="chart",
                content={
                    "chart_type": "bar",
                    "title": caption or None,
                    "x_axis": {"label": None, "ticks": [point["label"] for point in points]},
                    "y_axis": {"label": name, "unit": None},
                    "series": [{"name": name, "points": points, "method": "geometry"}],
                    "agreement": None,
                    "candidates": [],
                },
                region_id=str(region_field(region, "id", "region")),
                source_file=str(path),
                history=[{"engine": "geometry", "confidence": 0.9, "note": caption or "bar chart"}],
            )
        ]
    if caption:
        return [_unreadable_figure(region, path, context, caption, page_number)]
    return [_fail(region, "Chart values could not be established")]


def _pptx_charts(region, path) -> list:
    from extractors.office import extract_document

    charts = [block for block in extract_document(path) if block.type == "chart"]
    if charts:
        return charts
    return [_fail(region, "No native chart series in the presentation")]


def _vertical_bars(page, region_box) -> list:
    rects = []
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is None or drawing.get("fill") is None:
            continue
        if rect.height < 20 or rect.width < 8 or rect.height < rect.width:
            continue
        if not _point_inside(((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2), region_box):
            continue
        rects.append(rect)
    if len(rects) < 2:
        return []
    best = []
    for bottom in {round(rect.y1, 1) for rect in rects}:
        group = [rect for rect in rects if abs(rect.y1 - bottom) <= 2]
        if len(group) > len(best):
            best = group
    if len(best) < 2:
        return []
    best.sort(key=lambda rect: rect.x0)
    return best


def _points_from_bars(bars, words) -> tuple[list[dict], list[list[float]]]:
    points = []
    boxes = []
    for index, rect in enumerate(bars):
        value_word = _word_near(words, rect, above=True, numeric=True)
        if value_word is None:
            continue
        label_word = _word_near(words, rect, above=False, numeric=False)
        label = label_word[4] if label_word else str(index + 1)
        points.append({"label": label, "value": _number(value_word[4])})
        boxes.append([float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)])
        boxes.append(_word_box(value_word))
        if label_word:
            boxes.append(_word_box(label_word))
    return points, boxes


def _word_near(words, rect, *, above: bool, numeric: bool):
    found = []
    for word in words:
        cx = (word[0] + word[2]) / 2
        if cx < rect.x0 - 15 or cx > rect.x1 + 15:
            continue
        if above:
            gap = rect.y0 - word[3]
            if gap < -2 or gap > 40:
                continue
            if numeric and _number(word[4]) is None:
                continue
        else:
            gap = word[1] - rect.y1
            if gap < -2 or gap > 40:
                continue
        found.append((gap, word))
    if not found:
        return None
    found.sort(key=lambda item: item[0])
    return found[0][1]


def _caption(words, bars) -> tuple[str, list[float] | None]:
    ceiling = min(rect.y0 for rect in bars) - 8 if bars else 10**9
    grouped: dict[tuple, list] = {}
    for word in words:
        if word[3] >= ceiling:
            continue
        grouped.setdefault((word[5], word[6]), []).append(word)
    if not grouped:
        return "", None
    lines = []
    for line_words in grouped.values():
        line_words.sort(key=lambda item: item[0])
        text = " ".join(item[4] for item in line_words)
        box = _union([_word_box(item) for item in line_words])
        lines.append((text, box))
    lines.sort(key=lambda item: 0 if _FIGURE.search(item[0]) else 1)
    return lines[0]


def _series_name(caption: str):
    match = _FIGURE.search(caption or "")
    if not match:
        return None
    name = match.group(1).strip()
    return name or None


def _unreadable_figure(region, path, context, caption: str, page_number: int):
    crop = _crop_path(region, context)
    box = region_field(region, "bbox") or [0.0, 0.0, 0.0, 0.0]
    return make_block(
        extractor="chart",
        bbox=[float(value) for value in box],
        page_start=page_number if page_number >= 1 else 1,
        extraction=0.2,
        block_type="figure",
        content={"text": caption, "crop": crop},
        region_id=str(region_field(region, "id", "region")),
        status="needs_review",
        source_file=str(path),
        history=[{"engine": "geometry", "confidence": 0.2, "note": "caption without readable bars"}],
    )


def _crop_path(region, context):
    try:
        from extractors.ocr import _open_crop_source, _save_crop
        from extractors.utils import crop_region

        image, page_size, region_box = _open_crop_source(region, context)
        if image is None:
            return None
        return str(_save_crop(crop_region(image, region_box, page_size), region))
    except Exception:
        return None


def _region_box(region, width: float, height: float) -> list[float]:
    bbox = region_field(region, "bbox")
    if not bbox or len(bbox) != 4:
        return [0.0, 0.0, float(width), float(height)]
    return [float(value) for value in bbox]


def _point_inside(point, box) -> bool:
    x = point[0]
    y = point[1]
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _word_box(word) -> list[float]:
    return [float(word[0]), float(word[1]), float(word[2]), float(word[3])]


def _union(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _number(text: str):
    try:
        return float(str(text).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _fail(region, message: str):
    return failed_block(region, error_code="CHART_FAILED", message=message, extractor="chart")
