"""The orchestrator calls P3. These samples stay on the digital and Office paths."""

from pipeline.orchestrator import parse_document


def _texts(doc) -> list[str]:
    found = []
    for block in doc.blocks:
        content = block.content
        if isinstance(content, dict):
            found.append(str(content.get("text") or ""))
            found.append(str(content.get("latex") or ""))
        else:
            found.append(str(content or ""))
    return found


def test_simple_pdf_returns_the_heading():
    doc = parse_document("sample_docs/simple.pdf")
    assert doc.status == "complete"
    assert any("Annual Financial Report 2025" in text for text in _texts(doc))
    assert any("FY2025" in text for text in _texts(doc))
    assert all(block.extractor for block in doc.blocks)


def test_docx_uses_the_office_reader():
    doc = parse_document("sample_docs/sample.docx")
    assert doc.status == "complete"
    assert any("Annual Financial Report 2025" in text for text in _texts(doc))
    assert any(block.extractor == "python-docx" for block in doc.blocks)


def test_xlsx_keeps_the_cell():
    doc = parse_document("sample_docs/sample.xlsx")
    assert doc.status == "complete"
    table = next(block for block in doc.blocks if block.type == "table")
    cells = [cell for row in table.content["rows"] for cell in row["cells"]]
    assert any(cell["text"] == "128.5" for cell in cells)
    assert table.source.sheet == "Financials"
