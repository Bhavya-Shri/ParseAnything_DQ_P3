"""OCR on a scanned page. The first run loads PaddleOCR; later runs reuse it."""

import pymupdf

from extractors import extract


def _region(page_box):
    return {
        "id": "scan1",
        "type": "text",
        "page": 1,
        "bbox": page_box,
        "route": "ocr",
        "is_scanned": True,
    }


def test_ocr_reads_scanned_pdf():
    blocks = extract(
        _region([0, 0, 612, 792]),
        {"file_path": "sample_docs/scanned.pdf", "format": "pdf"},
    )
    assert len(blocks) == 1
    block = blocks[0]
    assert block.status == "accepted"
    assert block.extractor == "paddleocr"
    assert "128.5" in block.content["text"]
    assert "crore" in block.content["text"].lower()
    assert len(block.bbox) == 4
    assert block.bbox[0] < block.bbox[2]
    assert block.bbox[1] < block.bbox[3]
    assert 0 <= block.confidence.extraction <= 1
    assert block.history[0]["crop"]
    assert block.content["lines"]
    assert len(block.content["lines"][0]["bbox"]) == 4


def test_blank_crop_returns_ocr_failed(tmp_path):
    path = tmp_path / "blank.pdf"
    document = pymupdf.open()
    document.new_page(width=612, height=792)
    document.save(path)
    document.close()

    blocks = extract(
        _region([0, 0, 612, 792]),
        {"file_path": str(path), "format": "pdf"},
    )
    assert len(blocks) == 1
    assert blocks[0].status == "failed"
    assert blocks[0].history[0]["error_code"] == "OCR_FAILED"
