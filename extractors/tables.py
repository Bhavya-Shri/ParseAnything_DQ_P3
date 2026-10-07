"""Table regions become one block per table, with cells, spans, and cell boxes.

A ruled digital table is read from the PDF vector grid and filled with PyMuPDF
words. A digital table with no lines falls back to Docling. A scanned table
uses PaddleOCR table recognition. Cross-page merging belongs to P2.
"""

import os
from html.parser import HTMLParser
from pathlib import Path

import pymupdf

from extractors.base import Extractor
from extractors.utils import crop_region, failed_block, make_block, region_field

_TABLE_ENGINE = None


class TableExtractor(Extractor):
    def __init__(self, scanned: bool):
        self.scanned = scanned
        self.name = "paddleocr_table" if scanned else "docling_table"

    def can_handle(self, region) -> bool:
        route = region_field(region, "route")
        expected = "paddle_table" if self.scanned else "docling_table"
        if route == expected:
            return True
        if route not in (None, ""):
            return False
        if region_field(region, "type") != "table":
            return False
        return bool(region_field(region, "is_scanned")) == self.scanned

    def extract(self, region, context) -> list:
        context = context or {}
        path = context.get("file_path")
        if not path or not Path(path).is_file():
            return [_fail(region, f"Table extraction needs a file, got {path!r}", self.name)]
        try:
            if self.scanned:
                built = _from_paddle(region, context)
            else:
                built = _from_digital(region, context)
        except Exception as exc:
            return [_fail(region, f"{type(exc).__name__}: {exc}", self.name)]
        if not built:
            return [_fail(region, "Table structure could not be built", self.name)]
        return [_block(region, context, item) for item in built]


def assemble(cells: list[dict]) -> dict:
    """Turn positioned cells into the shared table content object."""
    grouped: dict[int, list[dict]] = {}
    for cell in cells:
        grouped.setdefault(int(cell["row"]), []).append(cell)
    grid = [sorted(grouped[key], key=lambda item: item["col"]) for key in sorted(grouped)]
    header_count = _header_count(grid)
    column_count = max(_width(row) for row in grid)
    header_rows = [_header_strings(row, column_count) for row in grid[:header_count]]
    body = grid[header_count:]
    paths = _column_paths(header_rows, column_count)
    rows = [{"cells": [_public_cell(cell) for cell in row]} for row in body]
    return {
        "header_rows": header_rows,
        "column_paths": paths,
        "rows": rows,
        "records": _records(rows, paths),
    }


def _from_digital(region, context) -> list[dict]:
    page_number = int(region_field(region, "page", 1) or 1)
    document = pymupdf.open(context["file_path"])
    try:
        index = page_number - 1 if page_number >= 1 else 0
        if index < 0 or index >= document.page_count:
            raise ValueError(f"Page {page_number} is outside the PDF")
        page = document[index]
        region_box = _region_box(region, page.rect.width, page.rect.height)
        cells = _vector_cells(page, region_box)
        engine = "pymupdf"
        if len(cells) < 2:
            cells = _docling_cells(context["file_path"], page_number, region_box, page)
            engine = "docling"
    finally:
        document.close()
    if len(cells) < 2:
        return []
    return [{"cells": cells, "engine": engine}]


def _vector_cells(page, region_box) -> list[dict]:
    rects = []
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is None or rect.width < 8 or rect.height < 8:
            continue
        if not _center_inside(rect, region_box):
            continue
        rects.append(rect)
    rects = [rect for rect in rects if not _contains_others(rect, rects)]
    if len(rects) < 2:
        return []
    xs = _cluster([edge for rect in rects for edge in (rect.x0, rect.x1)])
    ys = _cluster([edge for rect in rects for edge in (rect.y0, rect.y1)])
    words = page.get_text("words")
    cells = []
    for rect in rects:
        col = _index_of(xs, rect.x0)
        row = _index_of(ys, rect.y0)
        text = _words_inside(words, rect)
        cells.append(
            {
                "row": row,
                "col": col,
                "row_span": max(_index_of(ys, rect.y1) - row, 1),
                "col_span": max(_index_of(xs, rect.x1) - col, 1),
                "text": text,
                "bbox": [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)],
                "confidence": 0.95 if text else 0.5,
            }
        )
    unique = {}
    for cell in cells:
        unique[(cell["row"], cell["col"])] = cell
    return list(unique.values())


def _docling_cells(path, page_number, region_box, page) -> list[dict]:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = False
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    result = converter.convert(str(path))
    words = page.get_text("words")
    cells = []
    for table in result.document.tables:
        provenance = table.prov[0] if table.prov else None
        if provenance is not None and provenance.page_no != page_number:
            continue
        for cell in table.data.table_cells:
            bbox = _docling_bbox(cell.bbox, page.rect.height) if cell.bbox is not None else None
            if bbox is not None and not _boxes_overlap(bbox, region_box):
                continue
            text = cell.text or ""
            if bbox is not None:
                native = _words_inside(words, _box_rect(bbox))
                if native:
                    text = native
            cells.append(
                {
                    "row": cell.start_row_offset_idx,
                    "col": cell.start_col_offset_idx,
                    "row_span": cell.row_span or 1,
                    "col_span": cell.col_span or 1,
                    "text": text.strip(),
                    "bbox": bbox or list(region_box),
                    "confidence": 0.9 if text else 0.5,
                }
            )
    return cells


def _from_paddle(region, context) -> list[dict]:
    from extractors.ocr import _open_crop_source, _save_crop

    image, page_size, region_box = _open_crop_source(region, context)
    if image is None:
        raise ValueError("Scanned table needs a page image or a PDF")
    crop = crop_region(image, region_box, page_size)
    crop_path = _save_crop(crop, region)
    scale_x = image.width / float(page_size["width"])
    scale_y = image.height / float(page_size["height"])
    raw = _table_engine().predict(str(crop_path))
    built = []
    for item in raw if isinstance(raw, list) else [raw]:
        tables = _paddle_value(item, "table_res_list") or []
        if not tables and _paddle_value(item, "pred_html"):
            tables = [item]
        for table in tables:
            html = _paddle_value(table, "pred_html") or ""
            boxes = _paddle_value(table, "cell_box_list") or []
            cells = _html_cells(str(html), boxes, region_box, scale_x, scale_y)
            if cells:
                built.append({"cells": cells, "engine": "paddleocr_table"})
    return built


def _table_engine():
    global _TABLE_ENGINE
    if _TABLE_ENGINE is None:
        os.environ["FLAGS_use_mkldnn"] = "0"
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        from paddleocr import TableRecognitionPipelineV2

        _TABLE_ENGINE = TableRecognitionPipelineV2(
            enable_mkldnn=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
        )
    return _TABLE_ENGINE


def _html_cells(html: str, boxes, region_box, scale_x, scale_y) -> list[dict]:
    parser = _HtmlTable()
    parser.feed(html)
    flat = [cell for row in parser.rows for cell in row]
    pixel_boxes = [_as_box(box) for box in _as_sequence(boxes)]
    cells = []
    cursor_row = 0
    for row_index, row in enumerate(parser.rows):
        col = 0
        for cell in row:
            bbox = list(region_box)
            if cursor_row < len(pixel_boxes):
                bbox = _pixel_to_page(pixel_boxes[cursor_row], region_box, scale_x, scale_y)
            cells.append(
                {
                    "row": row_index,
                    "col": col,
                    "row_span": cell["row_span"],
                    "col_span": cell["col_span"],
                    "text": cell["text"],
                    "bbox": bbox,
                    "confidence": 0.8 if cell["text"] else 0.4,
                }
            )
            col += cell["col_span"]
            cursor_row += 1
    return cells


class _HtmlTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[dict]] = []
        self._row: list[dict] | None = None
        self._cell: dict | None = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = {
                "text": "",
                "row_span": int(attributes.get("rowspan", 1) or 1),
                "col_span": int(attributes.get("colspan", 1) or 1),
            }

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"] += data

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._cell["text"] = " ".join(self._cell["text"].split())
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def _block(region, context, item) -> object:
    content = assemble(item["cells"])
    boxes = [cell["bbox"] for cell in item["cells"]]
    confidences = [cell["confidence"] for cell in item["cells"]]
    page_number = int(region_field(region, "page", 1) or 1)
    return make_block(
        extractor=item["engine"],
        bbox=_union(boxes),
        page_start=page_number if page_number >= 1 else 1,
        extraction=sum(confidences) / len(confidences),
        block_type="table",
        content=content,
        region_id=str(region_field(region, "id", "region")),
        source_file=str(context.get("file_path") or ""),
        history=[{"engine": item["engine"], "confidence": sum(confidences) / len(confidences), "note": "table"}],
    )


def _public_cell(cell: dict) -> dict:
    text = cell["text"]
    return {
        "text": text,
        "value": _number(text),
        "unit": None,
        "scale": None,
        "row_span": int(cell["row_span"]),
        "col_span": int(cell["col_span"]),
        "bbox": [float(value) for value in cell["bbox"]],
        "confidence": float(cell["confidence"]),
        "repaired": False,
    }


def _header_count(grid: list[list[dict]]) -> int:
    count = 0
    for row in grid:
        texts = [cell["text"] for cell in row]
        if texts and all(_number(text) is None for text in texts):
            count += 1
            continue
        break
    if count == len(grid) and len(grid) > 1:
        return 1
    return count


def _header_strings(row: list[dict], column_count: int) -> list[str]:
    values = [""] * column_count
    for cell in row:
        for offset in range(cell["col_span"]):
            index = cell["col"] + offset
            if index < column_count:
                values[index] = cell["text"]
    return values


def _column_paths(header_rows: list[list[str]], column_count: int) -> list[str]:
    paths = []
    for col in range(column_count):
        parts = []
        for row in header_rows:
            text = row[col].strip() if col < len(row) else ""
            if text and (not parts or parts[-1] != text):
                parts.append(text)
        paths.append(" > ".join(parts) if parts else f"col_{col + 1}")
    return paths


def _records(rows: list[dict], paths: list[str]) -> list[dict]:
    records = []
    for row in rows:
        record = {}
        col = 0
        for cell in row["cells"]:
            key = paths[col] if col < len(paths) else f"col_{col + 1}"
            if key in record:
                key = f"{key}#{col}"
            record[key] = cell["text"]
            col += cell["col_span"]
        records.append(record)
    return records


def _width(row: list[dict]) -> int:
    return sum(cell["col_span"] for cell in row)


def _number(text: str):
    cleaned = text.replace(",", "").strip()
    if not cleaned or cleaned in {"-", "—", "N/A", "n/a", "NA"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _fail(region, message: str, extractor: str):
    block = failed_block(region, error_code="TABLE_FAILED", message=message, extractor=extractor)
    return block


def _region_box(region, width, height) -> list[float]:
    bbox = region_field(region, "bbox")
    if not bbox or len(bbox) != 4:
        return [0.0, 0.0, float(width), float(height)]
    return [float(value) for value in bbox]


def _center_inside(rect, region_box) -> bool:
    cx = (rect.x0 + rect.x1) / 2
    cy = (rect.y0 + rect.y1) / 2
    return region_box[0] <= cx <= region_box[2] and region_box[1] <= cy <= region_box[3]


def _contains_others(rect, rects) -> bool:
    contained = 0
    for other in rects:
        if other is rect:
            continue
        if (
            rect.x0 <= other.x0 + 1
            and rect.y0 <= other.y0 + 1
            and rect.x1 >= other.x1 - 1
            and rect.y1 >= other.y1 - 1
            and rect.get_area() > other.get_area() * 1.5
        ):
            contained += 1
    return contained >= 2


def _cluster(values, tolerance: float = 2.0) -> list[float]:
    groups: list[list[float]] = []
    for value in sorted(float(item) for item in values):
        if not groups or value - groups[-1][-1] > tolerance:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [sum(group) / len(group) for group in groups]


def _index_of(lines: list[float], value: float) -> int:
    return min(range(len(lines)), key=lambda index: abs(lines[index] - value))


def _words_inside(words, rect) -> str:
    chosen = []
    for word in words:
        cx = (word[0] + word[2]) / 2
        cy = (word[1] + word[3]) / 2
        if rect.x0 - 1 <= cx <= rect.x1 + 1 and rect.y0 - 1 <= cy <= rect.y1 + 1:
            chosen.append(word)
    chosen.sort(key=lambda word: (word[1], word[0]))
    return " ".join(word[4] for word in chosen)


def _docling_bbox(bbox, page_height: float) -> list[float]:
    if str(bbox.coord_origin).endswith("BOTTOMLEFT") or getattr(bbox.coord_origin, "value", "") == "BOTTOMLEFT":
        bbox = bbox.to_top_left_origin(page_height)
    return [float(bbox.l), float(bbox.t), float(bbox.r), float(bbox.b)]


def _box_rect(bbox: list[float]):
    return pymupdf.Rect(bbox)


def _boxes_overlap(a, b) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _pixel_to_page(box, region_box, scale_x, scale_y) -> list[float]:
    return [
        region_box[0] + box[0] / scale_x,
        region_box[1] + box[1] / scale_y,
        region_box[0] + box[2] / scale_x,
        region_box[1] + box[3] / scale_y,
    ]


def _as_box(box) -> list[float]:
    if hasattr(box, "tolist"):
        box = box.tolist()
    if len(box) == 4 and not isinstance(box[0], (list, tuple)):
        return [float(value) for value in box]
    xs = [float(point[0]) for point in box]
    ys = [float(point[1]) for point in box]
    return [min(xs), min(ys), max(xs), max(ys)]


def _as_sequence(value):
    if value is None:
        return []
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        value = value.tolist()
    return list(value)


def _paddle_value(item, key):
    try:
        if isinstance(item, dict):
            return item.get(key)
        return item[key]
    except Exception:
        return None


def _union(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]
