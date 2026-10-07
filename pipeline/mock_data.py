"""
mock_data.py — P1 owned
Canonical mock data following the exact UniversalBlock / DocumentResult contract.

P2, P3, P4, P5 import from here to work independently before real extractors are ready.

Usage:
    from pipeline.mock_data import MOCK_DOCUMENT, MOCK_BLOCKS
"""

from pipeline.schema import (
    Block, DocumentResult, ConfidenceInfo, SourceInfo, VerificationResult
)

# ------------------------------------------------------------------
# Individual mock blocks — one of each major type
# ------------------------------------------------------------------

MOCK_BLOCKS = [
    Block(
        id="blk_001",
        type="heading",
        content="Annual Financial Report 2025",
        page_start=1,
        bbox=[72.0, 80.0, 520.0, 120.0],
        reading_order=1,
        order_confidence=0.99,
        extractor="mock",
        confidence=ConfidenceInfo(extraction=0.99, structure=0.99, source_quality=1.0, final=0.99),
        risk="LOW",
        status="verified",
        verification=VerificationResult(method="secondary_extraction", agreement=1.0),
        source=SourceInfo(file="sample_annual_report.pdf", page=1, bbox=[72.0, 80.0, 520.0, 120.0]),
    ),
    Block(
        id="blk_002",
        type="paragraph",
        content="The company delivered strong financial performance during FY2025, with revenue growing 18% year-on-year.",
        page_start=1,
        bbox=[72.0, 140.0, 520.0, 205.0],
        reading_order=2,
        order_confidence=0.97,
        extractor="mock",
        confidence=ConfidenceInfo(extraction=0.97, structure=0.95, source_quality=1.0, final=0.92),
        risk="LOW",
        status="accepted",
        source=SourceInfo(file="sample_annual_report.pdf", page=1, bbox=[72.0, 140.0, 520.0, 205.0]),
    ),
    Block(
        id="blk_003",
        type="table",
        content={
            "headers": ["Metric", "FY2024", "FY2025", "YoY Growth"],
            "rows": [
                ["Revenue (INR Cr)", "1,050", "1,239", "18.0%"],
                ["EBITDA (INR Cr)", "210",   "261",   "24.3%"],
                ["Net Profit (INR Cr)", "120", "148",  "23.3%"],
                ["Total", "1,380", "1,648", "19.4%"],
            ],
            "arithmetic_checks": {
                "checks_run": 3,
                "checks_passed": 3,
                "checks_failed": 0,
            }
        },
        page_start=2,
        bbox=[72.0, 200.0, 540.0, 380.0],
        reading_order=5,
        order_confidence=0.95,
        extractor="mock_table",
        confidence=ConfidenceInfo(extraction=0.93, structure=0.91, source_quality=1.0, final=0.85),
        risk="CRITICAL",
        status="verified",
        verification=VerificationResult(method="arithmetic_check", agreement=1.0),
        source=SourceInfo(file="sample_annual_report.pdf", page=2, bbox=[72.0, 200.0, 540.0, 380.0]),
    ),
    Block(
        id="blk_004",
        type="table",
        content={
            "headers": ["Q", "Revenue"],
            "rows": [
                ["Q1", "290"],
                ["Q2", "295"],
                ["Q3", "310"],
                ["Q4", "344"],
                ["Total", "1,239"],  # intentional arithmetic discrepancy for demo
            ],
            "arithmetic_checks": {
                "checks_run": 1,
                "checks_passed": 0,
                "checks_failed": 1,
                "failed_cells": ["blk_004_row4_col1"],
                "repair_attempted": True,
                "repair_succeeded": False,
            }
        },
        page_start=2,
        bbox=[72.0, 400.0, 300.0, 560.0],
        reading_order=6,
        order_confidence=0.88,
        extractor="mock_ocr",
        confidence=ConfidenceInfo(extraction=0.61, structure=0.72, source_quality=0.68, final=0.30),
        risk="CRITICAL",
        status="needs_review",
        flags=["arith_fail", "ocr_low_conf"],
        source=SourceInfo(file="sample_annual_report.pdf", page=2, bbox=[72.0, 400.0, 300.0, 560.0]),
    ),
    Block(
        id="blk_005",
        type="figure",
        content={
            "caption": "Figure 1: Revenue breakdown by segment FY2025",
            "chart_type": "bar",
            "series": [
                {"label": "Product A", "value": 620.0},
                {"label": "Product B", "value": 380.0},
                {"label": "Services",  "value": 239.0},
            ],
            "method": "vlm_caption_extraction",
        },
        page_start=3,
        bbox=[72.0, 80.0, 540.0, 400.0],
        reading_order=8,
        order_confidence=0.91,
        extractor="mock_chart",
        confidence=ConfidenceInfo(extraction=0.78, structure=0.80, source_quality=0.90, final=0.56),
        risk="HIGH",
        status="accepted",
        source=SourceInfo(file="sample_annual_report.pdf", page=3, bbox=[72.0, 80.0, 540.0, 400.0]),
    ),
    Block(
        id="blk_006",
        type="equation",
        content=r"EBITDA\_margin = \frac{EBITDA}{Revenue} \times 100 = 21.1\%",
        page_start=3,
        bbox=[180.0, 420.0, 430.0, 460.0],
        reading_order=9,
        order_confidence=0.94,
        extractor="mock_formula",
        confidence=ConfidenceInfo(extraction=0.90, structure=0.88, source_quality=1.0, final=0.79),
        risk="HIGH",
        status="verified",
        source=SourceInfo(file="sample_annual_report.pdf", page=3, bbox=[180.0, 420.0, 430.0, 460.0]),
    ),
]

# ------------------------------------------------------------------
# Full mock DocumentResult — P5 / P4 can load this directly
# ------------------------------------------------------------------

MOCK_DOCUMENT = DocumentResult(
    document_id="doc_mock_001",
    filename="sample_annual_report.pdf",
    format="pdf",
    page_count=3,
    page_sizes={
        "1": {"width": 612.0, "height": 792.0},
        "2": {"width": 612.0, "height": 792.0},
        "3": {"width": 612.0, "height": 792.0},
    },
    status="complete",
    blocks=MOCK_BLOCKS,
    document_map=[
        {"title": "Annual Financial Report 2025", "level": 1, "page": 1, "kind": "section"},
        {"title": "Financial Summary Table",       "level": 2, "page": 2, "kind": "table"},
        {"title": "Figure 1: Revenue Breakdown",  "level": 2, "page": 3, "kind": "figure"},
    ],
    errors=[],
    trust_report={
        "total_blocks": len(MOCK_BLOCKS),
        "verified": 3,
        "accepted": 1,
        "needs_review": 1,
        "failed": 0,
        "arithmetic_checks_run": 4,
        "arithmetic_checks_passed": 3,
        "arithmetic_checks_failed": 1,
        "repaired_cells": 0,
        "flagged_blocks": 1,
    },
    metrics={
        "total_time_seconds": 36.0,
        "pages_per_second": 0.08,
        "vlm_calls": 1,
        "ocr_pages": 0,
    }
)


if __name__ == "__main__":
    import json
    print(json.dumps(MOCK_DOCUMENT.model_dump(), indent=2))
