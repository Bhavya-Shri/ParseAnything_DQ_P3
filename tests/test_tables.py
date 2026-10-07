"""Table structure for a ruled digital PDF, plus span handling without a model."""

from extractors import extract
from extractors.tables import _html_cells, assemble


def test_table_pdf_keeps_cells():
    blocks = extract(
        {
            "id": "t1",
            "type": "table",
            "page": 1,
            "bbox": [0, 0, 612, 792],
            "route": "docling_table",
            "is_scanned": False,
        },
        {"file_path": "sample_docs/table.pdf", "format": "pdf"},
    )
    assert len(blocks) == 1
    block = blocks[0]
    assert block.type == "table"
    assert block.extractor == "pymupdf"
    content = block.content
    assert "rows" in content
    assert "text" not in content
    widths = [sum(cell["col_span"] for cell in row["cells"]) for row in content["rows"]]
    assert widths
    assert len(set(widths)) == 1
    cells = [cell for row in content["rows"] for cell in row["cells"]]
    assert any(len(cell["bbox"]) == 4 for cell in cells)
    assert any(cell["text"] == "128.5" for cell in cells)
    found = next(cell for cell in cells if cell["text"] == "128.5")
    assert found["value"] == 128.5
    assert found["repaired"] is False
    assert found["unit"] is None
    assert content["header_rows"][0] == ["Year", "Revenue", "EBITDA"]
    assert content["records"][-1]["Revenue"] == "128.5"


def test_colspan_rows_share_effective_width():
    cells = [
        {"row": 0, "col": 0, "row_span": 1, "col_span": 1, "text": "Item", "bbox": [0, 0, 10, 10], "confidence": 1},
        {"row": 0, "col": 1, "row_span": 1, "col_span": 2, "text": "Amount", "bbox": [10, 0, 30, 10], "confidence": 1},
        {"row": 1, "col": 0, "row_span": 1, "col_span": 1, "text": "Revenue", "bbox": [0, 10, 10, 20], "confidence": 1},
        {"row": 1, "col": 1, "row_span": 1, "col_span": 1, "text": "128.5", "bbox": [10, 10, 20, 20], "confidence": 1},
        {"row": 1, "col": 2, "row_span": 1, "col_span": 1, "text": "1", "bbox": [20, 10, 30, 20], "confidence": 1},
    ]
    content = assemble(cells)
    header_width = len(content["header_rows"][0])
    body_width = sum(cell["col_span"] for cell in content["rows"][0]["cells"])
    assert header_width == body_width == 3
    assert content["column_paths"][1] == "Amount"
    assert content["rows"][0]["cells"][1]["text"] == "128.5"
    assert content["rows"][0]["cells"][1]["col_span"] == 1


def test_html_table_keeps_colspan():
    html = "<table><tr><td>Year</td><td colspan='2'>Revenue</td></tr><tr><td>2025</td><td>128.5</td><td>29.1</td></tr></table>"
    cells = _html_cells(html, [[0, 0, 10, 10]] * 5, [0, 0, 100, 40], 1, 1)
    content = assemble(cells)
    assert len(content["header_rows"][0]) == 3
    assert sum(cell["col_span"] for cell in content["rows"][0]["cells"]) == 3
