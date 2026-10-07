"""Native text for a digital PDF region. PyMuPDF reads the words. Docling is a cross-read."""

from difflib import SequenceMatcher
from pathlib import Path

import pymupdf

from extractors.base import Extractor
from extractors.utils import failed_block, make_block, region_field

_AGREE = 0.98
_HEADING_SIZE = 16.0


class NativeTextExtractor(Extractor):
    name = "pymupdf"

    def can_handle(self, region) -> bool:
        route = region_field(region, "route")
        if route not in (None, "", "native_text"):
            return False
        return not bool(region_field(region, "is_scanned"))

    def extract(self, region, context) -> list:
        context = context or {}
        path = context.get("file_path")
        if not path or not Path(path).is_file():
            return [
                failed_block(
                    region,
                    error_code="INTERNAL_ERROR",
                    message=f"Native text needs a PDF file, got {path!r}",
                    extractor=self.name,
                )
            ]
        page_number = int(region_field(region, "page", 1) or 1)
        try:
            document = pymupdf.open(path)
        except Exception as exc:
            return [
                failed_block(
                    region,
                    error_code="INTERNAL_ERROR",
                    message=f"Could not open PDF: {exc}",
                    extractor=self.name,
                )
            ]
        try:
            index = page_number - 1 if page_number >= 1 else 0
            if index < 0 or index >= document.page_count:
                return [
                    failed_block(
                        region,
                        error_code="INTERNAL_ERROR",
                        message=f"Page {page_number} is outside the PDF",
                        extractor=self.name,
                    )
                ]
            page = document[index]
            region_box = _region_box(region, page)
            lines = _lines_in_region(page, region_box)
        finally:
            document.close()

        if not lines:
            return [
                failed_block(
                    region,
                    error_code="INTERNAL_ERROR",
                    message="No native text in region",
                    extractor=self.name,
                )
            ]

        blocks = []
        region_id = str(region_field(region, "id", "region"))
        source_file = str(path)
        for index, line in enumerate(_merge_paragraphs(lines)):
            content = {"text": line["text"]}
            if line["kind"] == "heading":
                content["level"] = 1
            blocks.append(
                make_block(
                    extractor=self.name,
                    bbox=line["bbox"],
                    page_start=page_number if page_number >= 1 else 1,
                    extraction=0.90,
                    block_type=line["kind"],
                    content=content,
                    region_id=region_id,
                    index=index,
                    source_file=source_file,
                    history=[{"engine": self.name, "confidence": 0.90, "note": "native text"}],
                )
            )
        _apply_docling(blocks, context)
        return blocks


def _region_box(region, page) -> list[float]:
    bbox = region_field(region, "bbox")
    if not bbox or len(bbox) != 4:
        rect = page.rect
        return [rect.x0, rect.y0, rect.x1, rect.y1]
    return [float(value) for value in bbox]


def _lines_in_region(page, region_box: list[float]) -> list[dict]:
    grouped: dict[tuple[int, int], list] = {}
    for word in page.get_text("words"):
        if _center_inside(word[:4], region_box):
            grouped.setdefault((word[5], word[6]), []).append(word)
    spans = _spans(page)
    lines = []
    for key in sorted(grouped, key=lambda item: (grouped[item][0][1], grouped[item][0][0])):
        words = sorted(grouped[key], key=lambda word: word[0])
        bbox = _union([word[:4] for word in words])
        size = _line_size(bbox, spans)
        lines.append(
            {
                "text": " ".join(word[4] for word in words),
                "bbox": bbox,
                "size": size,
                "block_no": key[0],
                "kind": "heading" if size >= _HEADING_SIZE else "paragraph",
            }
        )
    return lines


def _spans(page) -> list[dict]:
    spans = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                spans.append({"bbox": span["bbox"], "size": float(span["size"])})
    return spans


def _line_size(bbox, spans) -> float:
    sizes = [span["size"] for span in spans if _overlaps(bbox, span["bbox"])]
    if not sizes:
        return 12.0
    return sum(sizes) / len(sizes)


def _merge_paragraphs(lines: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for line in lines:
        previous = merged[-1] if merged else None
        gap = line["bbox"][1] - previous["bbox"][3] if previous else 0
        line_height = max(line["bbox"][3] - line["bbox"][1], 1)
        if (
            previous
            and previous["kind"] == "paragraph"
            and line["kind"] == "paragraph"
            and previous["block_no"] == line["block_no"]
            and gap < line_height * 1.5
        ):
            previous["text"] = f"{previous['text']} {line['text']}"
            previous["bbox"] = _union([previous["bbox"], line["bbox"]])
            continue
        merged.append(dict(line))
    return merged


def _apply_docling(blocks: list, context: dict) -> None:
    other = _docling_text(context)
    if other is None:
        return
    ours = " ".join(block.content["text"] for block in blocks)
    score = _similarity(ours, other)
    if score >= _AGREE:
        extraction = 0.97
        status = "accepted"
    else:
        extraction = score
        status = "needs_review"
    for block in blocks:
        block.confidence.extraction = extraction
        block.confidence.final = extraction
        block.status = status
        block.history.append(
            {"engine": "docling", "confidence": score, "note": other[:500]}
        )


def _docling_text(context: dict) -> str | None:
    item = context.get("docling_item")
    if item is None:
        item = context.get("docling_document")
    if item is None:
        return None
    if isinstance(item, str):
        return item.strip() or None
    if isinstance(item, dict):
        for key in ("text", "markdown"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
    for attr in ("text", "export_to_markdown"):
        value = getattr(item, attr, None)
        if callable(value):
            value = value()
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _similarity(left: str, right: str) -> float:
    a = " ".join(left.lower().split())
    b = " ".join(right.lower().split())
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _center_inside(bbox, region_box) -> bool:
    cx = (float(bbox[0]) + float(bbox[2])) / 2
    cy = (float(bbox[1]) + float(bbox[3])) / 2
    return (
        region_box[0] - 0.5 <= cx <= region_box[2] + 0.5
        and region_box[1] - 0.5 <= cy <= region_box[3] + 0.5
    )


def _overlaps(a, b) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _union(boxes) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]
