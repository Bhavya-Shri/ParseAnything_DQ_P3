"""Equation crops become LaTeX. The parse check does not need a second model."""

import pymupdf

from extractors import extract
from extractors.equations import latex_parses


def test_known_equation_parses():
    assert latex_parses(r"E = mc^{2}") is True
    assert latex_parses(r"E = mc^{") is False


def test_equation_pdf_returns_latex():
    blocks = extract(
        {
            "id": "eq1",
            "type": "equation",
            "page": 1,
            "bbox": [50, 100, 450, 180],
            "route": "formula",
        },
        {"file_path": "sample_docs/equation.pdf", "format": "pdf"},
    )
    assert len(blocks) == 1
    block = blocks[0]
    assert block.type == "equation"
    assert block.content["latex"]
    assert isinstance(block.content["parsed"], bool)
    assert "E" in block.content["latex"]
    assert len(block.bbox) == 4


def test_garbage_crop_does_not_crash(tmp_path):
    path = tmp_path / "blank.pdf"
    document = pymupdf.open()
    document.new_page(width=612, height=792)
    document.save(path)
    document.close()
    blocks = extract(
        {
            "id": "blankeq",
            "type": "equation",
            "page": 1,
            "bbox": [0, 0, 612, 792],
            "route": "formula",
        },
        {"file_path": str(path), "format": "pdf"},
    )
    assert len(blocks) == 1
    block = blocks[0]
    if block.status == "failed":
        assert block.history[0]["error_code"] == "FORMULA_FAILED"
    else:
        assert block.content["parsed"] is False
        assert "formula_parse_fail" in block.flags
