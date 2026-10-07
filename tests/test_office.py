"""Native Office reads. These must match the sample files and must not use a vision model."""

from extractors import extract
from extractors.office import extract_document


def test_xlsx_cell_value():
    blocks = extract_document("sample_docs/sample.xlsx")
    assert len(blocks) == 1
    block = blocks[0]
    assert block.type == "table"
    assert block.extractor == "openpyxl"
    assert block.source.sheet == "Financials"
    assert block.source.page is None
    assert "B2" in block.source.cell_range
    cells = [cell for row in block.content["rows"] for cell in row["cells"]]
    found = next(cell for cell in cells if cell["text"] == "128.5")
    assert found["value"] == 128.5
    assert found["repaired"] is False
    assert found["number_format"]


def test_docx_heading():
    blocks = extract_document("sample_docs/sample.docx")
    heading = next(block for block in blocks if block.type == "heading")
    assert heading.content["text"] == "Annual Financial Report 2025"
    assert heading.content["level"] == 1
    assert heading.extractor == "python-docx"
    assert heading.source.page is None
    assert any("FY2025" in block.content["text"] for block in blocks if block.type == "paragraph")


def test_pptx_title_and_native_chart():
    blocks = extract_document("sample_docs/sample.pptx")
    title = next(block for block in blocks if block.type == "heading")
    assert title.content["text"] == "Revenue Growth"
    assert title.source.slide == 1
    assert len(title.bbox) == 4
    chart = next(block for block in blocks if block.type == "chart")
    series = chart.content["series"][0]
    assert series["method"] == "pptx_native"
    assert series["name"] == "Revenue"
    assert series["points"][2]["value"] == 128.5
    assert chart.content["agreement"] is None


def test_office_route_reads_xlsx():
    blocks = extract(
        {"id": "sheet", "route": "office"},
        {"file_path": "sample_docs/sample.xlsx", "format": "xlsx"},
    )
    assert blocks[0].source.sheet == "Financials"
