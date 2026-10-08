"""P1, P2, and P3 meet at the P4 handoff. These checks stop before trust scoring."""

import pymupdf

from assembly.assembler import DocumentAssembler
from assembly.units import apply_units
from pipeline.orchestrator import parse_document
from routing.page_profiler import profile_page
from routing.region_detector import detect_native_regions
from routing.router import route_regions


def _page(path):
    document = pymupdf.open(path)
    page = document[0]
    return document, page


def test_margin_text_is_marked_as_furniture():
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 20), "CONFIDENTIAL", fontsize=9)
    page.insert_text((72, 780), "Page 1", fontsize=9)
    page.insert_text((72, 120), "Body text here", fontsize=12)
    try:
        profile = profile_page(page)
        regions = detect_native_regions(page, profile)
        assert any(region.is_header and "CONFIDENTIAL" in region.text for region in regions)
        assert any(region.is_footer and "Page 1" in region.text for region in regions)
        assert any(region.text.startswith("Body") and not region.is_header for region in regions)
    finally:
        document.close()


def test_two_column_reading_order_is_left_then_right():
    document, page = _page("sample_docs/03_two_column.pdf")
    try:
        profile = profile_page(page)
        regions = detect_native_regions(page, profile)
        from routing.column_detector import detect_layout_sections
        from routing.reading_order import reconstruct_reading_order

        ordered = reconstruct_reading_order(
            regions,
            detect_layout_sections(regions, profile),
        )
        texts = [region.text for region in ordered]
    finally:
        document.close()
    assert texts == [
        "Two-Column Financial Overview",
        "Test document for reading-order reconstruction.",
        "Company Overview",
        "The company operates across three regional markets.",
        "Revenue increased during the reporting period,",
        "supported by stronger demand and improved pricing.",
        "Management expects continued growth in the next",
        "financial year, subject to market conditions.",
        "Financial Highlights",
        "Operating margin improved by 2.4 percentage points.",
        "Free cash flow remained positive throughout the year.",
        "Capital expenditure focused on technology and",
        "capacity expansion across the core business units.",
        "The board approved the proposed annual dividend.",
        "Expected reading order: left column top-to-bottom, then right column top-to-bottom.",
    ]


def test_wide_heading_line_is_kept():
    from routing.region_detector import merge_region_sources
    from routing.route_models import Region

    banner = Region(
        region_id="banner",
        page_number=1,
        region_type="text",
        bbox=[55, 110, 429, 135],
        text="Company Overview Financial Highlights",
    )
    fragment = Region(
        region_id="fragment",
        page_number=1,
        region_type="text",
        bbox=[55, 112, 180, 132],
        text="Company Overview",
    )
    merged = merge_region_sources([fragment], [banner], page_width=595)
    assert [region.region_id for region in merged] == ["banner"]


def test_heading_is_not_absorbed_by_the_column_below_it():
    from routing.region_detector import merge_region_sources
    from routing.route_models import Region

    column = Region(
        region_id="column",
        page_number=1,
        region_type="text",
        bbox=[55, 150, 280, 400],
        text="The company operates across three regional markets.",
    )
    heading = Region(
        region_id="heading",
        page_number=1,
        region_type="text",
        bbox=[55, 130, 250, 175],
        text="Company Overview",
    )
    merged = merge_region_sources([heading], [column], page_width=595)
    assert [region.region_id for region in merged] == ["column", "heading"]


def test_column_heading_below_a_banner_is_kept():
    from routing.region_detector import merge_region_sources
    from routing.route_models import Region

    banner = Region(
        region_id="banner",
        page_number=1,
        region_type="text",
        bbox=[55, 110, 429, 140],
        text="Company Overview Financial Highlights",
    )
    heading = Region(
        region_id="heading",
        page_number=1,
        region_type="text",
        bbox=[55, 132, 200, 158],
        text="Company Overview",
    )
    merged = merge_region_sources([heading], [banner], page_width=595)
    assert [region.region_id for region in merged] == ["banner", "heading"]


def test_tall_page_box_does_not_swallow_columns():
    from routing.region_detector import merge_region_sources
    from routing.route_models import Region

    page_box = Region(
        region_id="page",
        page_number=1,
        region_type="text",
        bbox=[40, 100, 560, 700],
        text="both columns",
    )
    left = Region("left", 1, "text", [55, 150, 250, 180], text="The company operates across three regional markets.")
    right = Region("right", 1, "text", [320, 150, 520, 180], text="Operating margin improved by 2.4 percentage points.")
    merged = merge_region_sources([left, right], [page_box], page_width=595)
    assert [region.region_id for region in merged] == ["left", "right"]


def test_nested_column_box_does_not_keep_both_copies():
    from routing.region_detector import merge_region_sources
    from routing.route_models import Region

    column = Region(
        region_id="column",
        page_number=1,
        region_type="text",
        bbox=[300, 140, 540, 320],
        text="Operating margin improved by 2.4 percentage points.",
    )
    line = Region(
        region_id="line",
        page_number=1,
        region_type="text",
        bbox=[310, 150, 530, 170],
        text="Operating margin improved by 2.4 percentage points.",
    )
    merged = merge_region_sources([line], [column], page_width=595)
    assert [region.region_id for region in merged] == ["column"]


def test_table_page_is_routed_as_a_table():
    document, page = _page("sample_docs/table.pdf")
    try:
        profile = profile_page(page)
        assert profile.has_tables is True
        regions = detect_native_regions(page, profile)
        assert any(region.region_type == "table" for region in regions)
        assert not any(region.text == "128.5" for region in regions)
        routes = route_regions(regions, profile, risk="LOW")
        assert any(decision.route == "table" for decision in routes)
    finally:
        document.close()


def test_equation_page_is_routed_as_a_formula():
    document, page = _page("sample_docs/equation.pdf")
    try:
        profile = profile_page(page)
        assert profile.has_formula_like_regions is True
        regions = detect_native_regions(page, profile)
        assert any(region.region_type == "formula" for region in regions)
    finally:
        document.close()


def test_chart_page_is_routed_as_a_chart():
    document, page = _page("sample_docs/chart.pdf")
    try:
        profile = profile_page(page)
        assert profile.has_figures is True
        regions = detect_native_regions(page, profile)
        assert any(region.region_type == "chart" for region in regions)
        routes = route_regions(regions, profile, risk="LOW")
        assert any(decision.route == "chart" for decision in routes)
    finally:
        document.close()


def test_units_land_on_cells_and_charts():
    blocks = apply_units(
        [
            {
                "type": "paragraph",
                "page_start": 1,
                "content": {"text": "Figures are in crore."},
            },
            {
                "type": "table",
                "page_start": 1,
                "content": {
                    "header_rows": [["Year", "Revenue"]],
                    "rows": [
                        {
                            "cells": [
                                {"text": "2025", "value": 2025, "unit": None, "scale": None},
                                {"text": "128.5", "value": 128.5, "unit": None, "scale": None},
                            ]
                        }
                    ],
                },
            },
            {
                "type": "chart",
                "page_start": 1,
                "content": {"title": "Revenue", "y_axis": {"label": "Revenue", "unit": None}},
            },
        ]
    )
    cells = blocks[1]["content"]["rows"][0]["cells"]
    assert cells[0]["unit"] is None
    assert cells[1]["unit"] == "crore"
    assert cells[1]["scale"] == "crore"
    assert blocks[2]["content"]["y_axis"]["unit"] == "crore"


def test_bottom_and_top_tables_merge():
    def table(page, top, bottom):
        return {
            "type": "table",
            "page_start": page,
            "page_end": page,
            "page_number": page,
            "page_height": 792,
            "bbox": [72, top, 432, bottom],
            "reading_order": page,
            "content": {
                "header_rows": [["Year", "Revenue"]],
                "rows": [{"cells": [{"text": "1"}, {"text": "2"}]}],
            },
            "metadata": {"column_count": 2},
        }

    result = DocumentAssembler().assemble(
        [table(1, 640, 760), table(2, 36, 120)]
    )
    assert result.block_count == 1
    assert result.blocks[0]["page_end"] == 2
    assert result.blocks[0]["metadata"]["merged_table"] is True


def test_figure_route_keeps_a_review_block():
    from extractors import extract

    blocks = extract(
        {"id": "fig", "route": "figure", "page": 1, "bbox": [10, 10, 40, 40], "text": "Logo"},
        {"file_path": "sample_docs/simple.pdf"},
    )
    assert len(blocks) == 1
    assert blocks[0].type == "figure"
    assert blocks[0].status == "needs_review"
    assert blocks[0].content["text"] == "Logo"


def test_table_document_is_ready_for_p4():
    doc = parse_document("sample_docs/table.pdf")
    assert doc.metrics.get("ready_for") == "p4"
    table = next(block for block in doc.blocks if block.type == "table")
    cells = [cell for row in table.content["rows"] for cell in row["cells"]]
    assert any(cell["text"] == "128.5" for cell in cells)
    assert table.links["table_merge"]["merged"] is False


def test_chart_document_is_ready_for_p4():
    doc = parse_document("sample_docs/chart.pdf")
    assert doc.metrics.get("ready_for") == "p4"
    chart = next(block for block in doc.blocks if block.type == "chart")
    points = chart.content["series"][0]["points"]
    assert any(point["value"] == 128.5 for point in points)


def test_equation_document_is_ready_for_p4():
    doc = parse_document("sample_docs/equation.pdf")
    assert doc.metrics.get("ready_for") == "p4"
    equation = next(block for block in doc.blocks if block.type == "equation")
    assert "E" in equation.content["latex"]


def test_scanned_document_carries_the_unit():
    doc = parse_document("sample_docs/scanned.pdf")
    assert doc.metrics.get("ready_for") == "p4"
    texts = []
    for block in doc.blocks:
        content = block.content if isinstance(block.content, dict) else {}
        texts.append(str(content.get("text") or ""))
    assert any("128.5" in text and "crore" in text for text in texts)
    assert any(
        isinstance(block.content, dict) and block.content.get("unit") == "crore"
        for block in doc.blocks
    )


def test_image_file_reaches_p4(tmp_path):
    source = pymupdf.open("sample_docs/scanned.pdf")
    try:
        image_path = tmp_path / "note.png"
        source[0].get_pixmap(dpi=120).save(image_path)
    finally:
        source.close()
    doc = parse_document(str(image_path))
    assert doc.metrics.get("ready_for") == "p4"
    assert doc.blocks
    assert any(block.extractor == "paddleocr" for block in doc.blocks)


def test_timeout_option_uses_the_worker():
    doc = parse_document("sample_docs/missing.pdf", {"timeout_seconds": 30})
    assert doc.status == "failed"
    assert doc.errors[0]["error_code"] == "FILE_NOT_FOUND"
