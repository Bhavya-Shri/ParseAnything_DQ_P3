"""
test_schema.py — P1 owned
Unit tests for the shared data contract (schema.py).
Run: pytest tests/test_schema.py -v
"""
import pytest
from pydantic import ValidationError
from pipeline.schema import (
    Block, DocumentResult, ParseError,
    ConfidenceInfo, SourceInfo, VerificationResult
)


def make_block(**overrides):
    defaults = dict(
        id="blk_001",
        type="paragraph",
        content="Hello world",
        page_start=1,
        bbox=[0.0, 0.0, 100.0, 20.0],
        reading_order=1,
        order_confidence=0.95,
        extractor="test",
        confidence=ConfidenceInfo(extraction=0.9, structure=0.9, source_quality=1.0, final=0.81),
        risk="LOW",
        status="accepted",
        source=SourceInfo(file="test.pdf", page=1, bbox=[0.0, 0.0, 100.0, 20.0]),
    )
    defaults.update(overrides)
    return Block(**defaults)


class TestBlockSchema:
    def test_valid_block_creates(self):
        b = make_block()
        assert b.id == "blk_001"
        assert b.type == "paragraph"

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            make_block(type="unknown_type")

    def test_invalid_risk_raises(self):
        with pytest.raises(ValidationError):
            make_block(risk="EXTREME")

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            make_block(status="pending")

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            make_block(confidence=ConfidenceInfo(
                extraction=1.5, structure=0.9, source_quality=1.0, final=0.9
            ))

    def test_confidence_valid_range(self):
        b = make_block(confidence=ConfidenceInfo(
            extraction=0.0, structure=0.0, source_quality=0.0, final=0.0
        ))
        assert b.confidence.final == 0.0

    def test_all_block_types_valid(self):
        for t in ["heading", "paragraph", "list", "table", "figure",
                  "chart", "equation", "caption", "footnote", "header", "footer", "numeric"]:
            b = make_block(type=t)
            assert b.type == t

    def test_all_risk_levels_valid(self):
        for r in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
            b = make_block(risk=r)
            assert b.risk == r

    def test_all_statuses_valid(self):
        for s in ["verified", "accepted", "needs_review", "failed", "unaudited"]:
            b = make_block(status=s)
            assert b.status == s

    def test_block_serializes_to_dict(self):
        b = make_block()
        d = b.model_dump()
        assert d["id"] == "blk_001"
        assert "confidence" in d


class TestDocumentResult:
    def test_empty_document_creates(self):
        doc = DocumentResult(
            document_id="doc_1",
            filename="test.pdf",
            format="pdf",
            page_count=0,
            status="complete",
            blocks=[],
        )
        assert doc.document_id == "doc_1"
        assert doc.blocks == []

    def test_document_with_blocks(self):
        doc = DocumentResult(
            document_id="doc_2",
            filename="test.pdf",
            format="pdf",
            page_count=1,
            status="complete",
            blocks=[make_block()],
        )
        assert len(doc.blocks) == 1

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            DocumentResult(
                document_id="doc_3",
                filename="test.pdf",
                format="pdf",
                page_count=0,
                status="unknown",
                blocks=[],
            )


class TestParseError:
    def test_valid_error_creates(self):
        e = ParseError(
            status="error",
            error_code="UNSUPPORTED_FORMAT",
            message="Format not supported",
            recoverable=False,
            stage="preflight",
            trace_id="abc123",
        )
        assert e.error_code == "UNSUPPORTED_FORMAT"

    def test_error_with_page(self):
        e = ParseError(
            status="error",
            error_code="OCR_FAILED",
            message="OCR failed on page 3",
            recoverable=True,
            stage="extraction",
            page=3,
            trace_id="xyz789",
        )
        assert e.page == 3
