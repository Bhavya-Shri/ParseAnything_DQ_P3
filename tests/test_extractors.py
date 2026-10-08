"""Dispatcher and block-builder tests. These must not import Docling or PaddleOCR."""

import sys

from PIL import Image

from extractors import extract, register, unregister
from extractors.base import Extractor
from extractors.utils import crop_region, make_block, to_top_left


class _Boom(Extractor):
    name = "boom"

    def can_handle(self, region) -> bool:
        return True

    def extract(self, region, context) -> list:
        raise RuntimeError("engine blew up")


class _TextOnly(Extractor):
    name = "text-only"

    def can_handle(self, region) -> bool:
        return region.get("type") == "widget"

    def extract(self, region, context) -> list:
        return [
            make_block(
                extractor=self.name,
                bbox=region["bbox"],
                page_start=region["page"],
                extraction=0.9,
                content={"text": "hello"},
                region_id=region["id"],
            )
        ]


def test_skip_returns_no_blocks():
    blocks = extract({"id": "r1", "route": "skip", "page": 1, "bbox": [0, 0, 1, 1]})
    assert blocks == []


def test_unknown_route_returns_failed_block():
    blocks = extract({"id": "r2", "route": "not-a-route", "page": 3, "bbox": [1, 2, 3, 4]})
    assert len(blocks) == 1
    block = blocks[0]
    assert block.status == "failed"
    assert block.history[0]["error_code"] == "INTERNAL_ERROR"
    assert "not-a-route" in block.history[0]["note"]


def test_chart_route_without_a_file_fails():
    blocks = extract({"id": "r3", "route": "chart", "page": 1, "bbox": [0, 0, 10, 10]})
    assert blocks[0].status == "failed"
    assert blocks[0].history[0]["error_code"] == "CHART_FAILED"


def test_extractor_exception_does_not_escape():
    from extractors.ocr import OcrExtractor

    register("ocr", _Boom())
    try:
        blocks = extract({"id": "r4", "route": "ocr", "page": 2, "bbox": [0, 0, 5, 5]})
    finally:
        register("ocr", OcrExtractor())
    assert len(blocks) == 1
    assert blocks[0].status == "failed"
    assert "engine blew up" in blocks[0].history[0]["note"]


def test_missing_route_uses_can_handle():
    register("widget_probe", _TextOnly())
    try:
        blocks = extract(
            {
                "id": "r5",
                "type": "widget",
                "page": 1,
                "bbox": [10, 20, 30, 40],
            },
            {"file_path": "sample_docs/simple.pdf"},
        )
    finally:
        unregister("widget_probe")
    assert blocks[0].status == "accepted"
    assert blocks[0].extractor == "text-only"
    assert blocks[0].content == {"text": "hello"}


def _page_region(bbox):
    return {
        "id": "page1",
        "type": "text",
        "page": 1,
        "bbox": bbox,
        "route": "native_text",
        "is_scanned": False,
    }


def test_native_text_reads_simple_pdf():
    blocks = extract(
        _page_region([0, 0, 612, 792]),
        {"file_path": "sample_docs/simple.pdf", "format": "pdf"},
    )
    assert blocks
    assert all(block.status == "accepted" for block in blocks)
    heading = next(block for block in blocks if block.type == "heading")
    assert heading.content["text"] == "Annual Financial Report 2025"
    assert heading.content["level"] == 1
    assert heading.page_start == 1
    assert len(heading.bbox) == 4
    assert heading.bbox[0] < heading.bbox[2]
    assert heading.bbox[1] < heading.bbox[3]
    assert heading.bbox[2] <= 612
    assert heading.bbox[3] <= 792
    body = next(block for block in blocks if block.type == "paragraph")
    assert "FY2025" in body.content["text"]
    assert body.confidence.extraction == 0.90
    assert body.extractor == "pymupdf"


def test_native_text_respects_region_bbox():
    blocks = extract(
        _page_region([0, 50, 612, 95]),
        {"file_path": "sample_docs/simple.pdf", "format": "pdf"},
    )
    assert len(blocks) == 1
    assert blocks[0].type == "heading"
    assert blocks[0].content["text"] == "Annual Financial Report 2025"


def test_docling_agreement_raises_confidence():
    blocks = extract(
        _page_region([0, 0, 612, 792]),
        {
            "file_path": "sample_docs/simple.pdf",
            "docling_item": (
                "Annual Financial Report 2025 "
                "The company delivered strong financial performance during FY2025."
            ),
        },
    )
    assert all(block.confidence.extraction == 0.97 for block in blocks)
    assert all(block.status == "accepted" for block in blocks)
    assert any(entry["engine"] == "docling" for entry in blocks[0].history)


def test_docling_disagreement_needs_review():
    blocks = extract(
        _page_region([0, 0, 612, 792]),
        {
            "file_path": "sample_docs/simple.pdf",
            "docling_item": "This text is unrelated.",
        },
    )
    assert all(block.status == "needs_review" for block in blocks)
    assert blocks[0].content["text"] == "Annual Financial Report 2025"
    assert blocks[0].confidence.extraction < 0.97
    assert any(entry["engine"] == "docling" for entry in blocks[0].history)


def test_make_block_sets_required_fields():
    block = make_block(
        extractor="pymupdf",
        bbox=[72, 80, 520, 120],
        page_start=1,
        extraction=0.9,
        region_id="r12",
    )
    assert block.extractor == "pymupdf"
    assert block.bbox == [72.0, 80.0, 520.0, 120.0]
    assert block.page_start == 1
    assert block.page_end == 1
    assert block.confidence.extraction == 0.9
    assert block.confidence.final == 0.9
    assert block.reading_order == 0
    assert block.risk == "LOW"
    assert block.id == "blk_r12_0"


def test_bottom_left_bbox_flips_vertically():
    assert to_top_left([10, 20, 40, 50], page_height=100, origin="bottom-left") == [
        10.0,
        50.0,
        40.0,
        80.0,
    ]


def test_crop_uses_page_point_scale():
    image = Image.new("RGB", (200, 100), "white")
    crop = crop_region(image, [50, 10, 100, 40], {"width": 100, "height": 50})
    assert crop.size == (100, 60)


def test_suite_does_not_import_engines():
    assert "docling" not in sys.modules
    assert "paddleocr" not in sys.modules
