"""P4 trust, confidence, verification, and fail-safe."""

import pytest
from pydantic import ValidationError

from pipeline.schema import Block, ConfidenceInfo, SourceInfo
from validation.confidence import WEIGHTS, score_confidence
from validation import apply_trust, assess, assess_block


def make_block(**overrides):
    defaults = dict(
        id="blk_p4",
        type="paragraph",
        content="The notes describe the accounting policy.",
        page_start=1,
        bbox=[0.0, 0.0, 100.0, 20.0],
        reading_order=1,
        order_confidence=0.95,
        extractor="test",
        confidence=ConfidenceInfo(extraction=0.9, structure=0.8, source_quality=0.7, final=0.0),
        risk="LOW",
        status="accepted",
        source=SourceInfo(file="test.pdf", page=1, bbox=[0.0, 0.0, 100.0, 20.0]),
    )
    defaults.update(overrides)
    return Block(**defaults)


def test_each_block_type_uses_its_weights():
    assert set(WEIGHTS) == {
        "heading", "paragraph", "list", "table", "figure", "chart",
        "equation", "caption", "footnote", "header", "footer", "numeric",
    }
    for block_type, (extraction_weight, structure_weight, source_weight) in WEIGHTS.items():
        extraction_only = score_confidence(1, 0, 0, block_type)
        structure_only = score_confidence(0, 1, 0, block_type)
        source_only = score_confidence(0, 0, 1, block_type)
        assert extraction_only.final == extraction_weight
        assert structure_only.final == structure_weight
        assert source_only.final == source_weight


def test_all_zero_inputs_score_zero():
    for block_type in WEIGHTS:
        score = score_confidence(0, 0, 0, block_type)
        assert score.valid is True
        assert score.final == 0.0


def test_all_one_inputs_score_one():
    for block_type in WEIGHTS:
        score = score_confidence(1, 1, 1, block_type)
        assert score.valid is True
        assert score.final == 1.0


@pytest.mark.parametrize(
    "components",
    [
        (0, 0, 0),
        (1, 1, 1),
        (0.2, 0.4, 0.6),
        (0.333, 0.5, 1),
        (1, 0, 0.25),
    ],
)
def test_final_stays_inside_unit_interval(components):
    for block_type in WEIGHTS:
        score = score_confidence(*components, block_type)
        assert score.valid is True
        assert score.final is not None
        assert 0.0 <= score.final <= 1.0


def test_high_risk_block_requires_verification_and_does_not_invent_a_second_read():
    block = make_block(
        type="table",
        content={
            "headers": ["Metric", "FY2025"],
            "rows": [["Revenue", "100"], ["Cost", "40"], ["Profit", "60"]],
        },
    )
    result = assess_block(block)
    assert result.risk == "CRITICAL"
    assert "verification_required" in result.flags
    assert result.status == "unaudited"
    assert result.verification is None
    assert result.content == block.content


def test_matching_secondary_result_is_verified():
    block = make_block(content="Revenue grew during the year.")
    result = assess_block(block, secondary="Revenue grew during the year.")
    assert result.status == "verified"
    assert result.verification is not None
    assert result.verification.conflict is False
    assert result.verification.agreement == 1.0
    assert result.content == "Revenue grew during the year."


def test_conflicting_secondary_result_needs_review_and_keeps_the_primary():
    block = make_block(content="Revenue grew during the year.")
    result = assess_block(block, secondary="Revenue fell during the year.")
    assert result.status == "needs_review"
    assert result.verification is not None
    assert result.verification.conflict is True
    assert result.verification.secondary_value == "Revenue fell during the year."
    assert result.content == "Revenue grew during the year."
    assert "verification_conflict" in result.flags
    assert "repair_declined" in result.flags


def test_arithmetic_mismatch_is_flagged_without_changing_the_cell():
    content = {
        "headers": ["Quarter", "Revenue"],
        "rows": [
            ["Q1", "10"],
            ["Q2", "10"],
            ["Q3", "10"],
            ["Q4", "10"],
            ["Total", "50"],
        ],
    }
    block = make_block(type="table", content=content)
    result = assess_block(block)
    assert "arith_mismatch" in result.flags
    assert result.status == "needs_review"
    assert result.content["rows"][-1][1] == "50"
    assert block.content["rows"][-1][1] == "50"


def test_invalid_confidence_is_not_replaced():
    score = score_confidence(None, 0.5, 0.5, "paragraph")
    assert score.valid is False
    assert score.final is None

    out_of_range = score_confidence(1.4, 0.2, 0.2, "table")
    assert out_of_range.valid is False
    assert out_of_range.final is None

    unknown = score_confidence(0.5, 0.5, 0.5, "sidebar")
    assert unknown.valid is False
    assert unknown.final is None


def test_ambiguous_input_is_rejected_without_a_fabricated_block():
    missing = assess(None)
    assert missing.ok is False
    assert missing.block is None
    assert missing.flags == ["ambiguous_input"]

    incomplete = assess({"type": "paragraph", "content": "orphan"})
    assert incomplete.ok is False
    assert incomplete.block is None
    assert "ambiguous_input" in incomplete.flags


def test_profit_identity_mismatch_is_flagged():
    block = make_block(
        type="table",
        content={
            "header_rows": [["", "FY2025"]],
            "rows": [
                {"cells": [{"text": "Revenue"}, {"text": "100", "value": 100, "repaired": False}]},
                {"cells": [{"text": "Cost"}, {"text": "40", "value": 40, "repaired": False}]},
                {"cells": [{"text": "Profit"}, {"text": "50", "value": 50, "repaired": False}]},
            ],
        },
    )
    result = assess_block(block)
    assert "arith_mismatch" in result.flags
    assert result.content["rows"][2]["cells"][1]["text"] == "50"
    assert result.content["rows"][2]["cells"][1]["repaired"] is False


def test_unmeasured_components_are_scored_and_extraction_stays():
    block = make_block(
        confidence=ConfidenceInfo(extraction=1, structure=0, source_quality=0, final=0.2),
    )
    result = assess_block(block)
    assert result.confidence.extraction == 1
    assert result.confidence.structure == 0.95
    assert result.confidence.source_quality == 1.0
    assert result.confidence.final == 0.9875
    assert result.content == block.content
    with pytest.raises(ValidationError):
        ConfidenceInfo(extraction=-0.1, structure=0, source_quality=0, final=0)


def test_supplied_component_scores_are_kept():
    block = make_block(
        confidence=ConfidenceInfo(extraction=1, structure=0.8, source_quality=0.4, final=0),
    )
    result = assess_block(block)
    assert result.confidence.structure == 0.8
    assert result.confidence.source_quality == 0.4
    assert result.confidence.final == 0.86


def test_apply_trust_scores_risk_without_changing_extracted_content():
    content = {
        "headers": ["Metric", "FY2025"],
        "rows": [["Revenue", "100"], ["Cost", "40"], ["Profit", "50"]],
    }
    block = make_block(
        type="table",
        content=content,
        flags=["ocr_low_conf"],
        confidence=ConfidenceInfo(extraction=0.9, structure=0, source_quality=0, final=0.9),
    )
    result = apply_trust([block])[0]
    assert result.content == content
    assert result.status == "accepted"
    assert result.flags == ["ocr_low_conf"]
    assert result.reading_order == block.reading_order
    assert result.confidence.extraction == 0.9
    assert result.confidence.structure == 0.7
    assert result.confidence.source_quality == 0.7
    assert result.risk == "CRITICAL"
    assert block.risk == "LOW"
    assert block.confidence.final == 0.9


def test_pipeline_adds_trust_scores_on_an_office_file():
    from pipeline.orchestrator import parse_document

    doc = parse_document("sample_docs/sample.docx")
    assert doc.trust_report["total_blocks"] == len(doc.blocks)
    assert doc.trust_report["mean_final"] > 0
    assert any("Annual Financial Report 2025" in str(block.content) for block in doc.blocks)
    assert all(block.confidence.structure > 0 for block in doc.blocks)
    assert all(block.confidence.source_quality > 0 for block in doc.blocks)
    assert all(0.0 <= block.confidence.final <= 1.0 for block in doc.blocks)
    assert any(block.risk == "HIGH" for block in doc.blocks)
