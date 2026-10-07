"""Bar charts become series values. One reading leaves agreement empty."""

import pymupdf

from extractors import extract


def _region(path_id: str):
    return {
        "id": path_id,
        "type": "chart",
        "page": 1,
        "bbox": [0, 0, 612, 792],
        "route": "chart",
    }


def test_chart_pdf_bar_values():
    blocks = extract(_region("fig1"), {"file_path": "sample_docs/chart.pdf", "format": "pdf"})
    assert len(blocks) == 1
    block = blocks[0]
    assert block.type == "chart"
    assert block.content["chart_type"] == "bar"
    assert block.content["agreement"] is None
    assert block.content["title"] == "Figure 1 Revenue"
    series = block.content["series"][0]
    assert series["method"] == "geometry"
    assert series["name"] == "Revenue"
    assert [point["label"] for point in series["points"]] == ["2023", "2024", "2025"]
    assert [point["value"] for point in series["points"]] == [92.4, 110.7, 128.5]
    assert block.content["y_axis"]["unit"] is None
    assert len(block.bbox) == 4


def test_chart_route_on_pptx_uses_native_series():
    blocks = extract(
        {"id": "slidechart", "route": "chart", "page": 1},
        {"file_path": "sample_docs/sample.pptx", "format": "pptx"},
    )
    chart = next(block for block in blocks if block.type == "chart")
    series = chart.content["series"][0]
    assert series["method"] == "pptx_native"
    assert chart.content["agreement"] is None
    assert len(series["points"]) >= 2
    assert series["points"][2]["value"] == 128.5


def test_caption_without_bars_is_not_invented(tmp_path):
    path = tmp_path / "caption.pdf"
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 80), "Figure 2 Notes", fontsize=14)
    document.save(path)
    document.close()
    blocks = extract(_region("fig2"), {"file_path": str(path), "format": "pdf"})
    assert len(blocks) == 1
    block = blocks[0]
    assert block.type == "figure"
    assert block.status == "needs_review"
    assert block.content["text"] == "Figure 2 Notes"
    assert "series" not in block.content


def test_blank_chart_does_not_crash(tmp_path):
    path = tmp_path / "blank.pdf"
    document = pymupdf.open()
    document.new_page(width=612, height=792)
    document.save(path)
    document.close()
    blocks = extract(_region("blank"), {"file_path": str(path), "format": "pdf"})
    assert len(blocks) == 1
    assert blocks[0].status == "failed"
    assert blocks[0].history[0]["error_code"] == "CHART_FAILED"
