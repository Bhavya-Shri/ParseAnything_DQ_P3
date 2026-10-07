"""
test_pipeline.py — P1 owned
Integration tests for preflight and orchestrator.
Run: pytest tests/test_pipeline.py -v
"""
import os
import json
import pytest
import tempfile
from pipeline.preflight import preflight_check
from pipeline.errors import ParseAnythingException
from pipeline.orchestrator import parse_document
from pipeline.mock_data import MOCK_DOCUMENT


class TestPreflight:
    def test_valid_pdf(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4 fake content")
        result = preflight_check(str(f))
        assert result["ok"] is True
        assert result["format"] == "pdf"
        assert "trace_id" in result

    def test_valid_docx(self, tmp_path):
        f = tmp_path / "test.docx"
        f.write_bytes(b"PK fake docx content")
        result = preflight_check(str(f))
        assert result["format"] == "docx"

    def test_valid_image(self, tmp_path):
        f = tmp_path / "test.png"
        f.write_bytes(b"\x89PNG fake content")
        result = preflight_check(str(f))
        assert result["format"] == "png"

    def test_file_not_found_raises(self):
        with pytest.raises(ParseAnythingException) as exc:
            preflight_check("/nonexistent/path/fake.pdf")
        assert exc.value.error.error_code == "FILE_NOT_FOUND"

    def test_empty_file_raises(self, tmp_path):
        f = tmp_path / "empty.pdf"
        f.write_bytes(b"")
        with pytest.raises(ParseAnythingException) as exc:
            preflight_check(str(f))
        assert exc.value.error.error_code == "EMPTY_DOCUMENT"

    def test_unsupported_format_raises(self, tmp_path):
        f = tmp_path / "legacy.doc"
        f.write_bytes(b"some content")
        with pytest.raises(ParseAnythingException) as exc:
            preflight_check(str(f))
        assert exc.value.error.error_code == "UNSUPPORTED_FORMAT"

    def test_trace_id_is_unique(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF content")
        r1 = preflight_check(str(f))
        r2 = preflight_check(str(f))
        assert r1["trace_id"] != r2["trace_id"]


class TestOrchestrator:
    def test_missing_file_returns_failed(self):
        doc = parse_document("/fake/path/missing.pdf")
        assert doc.status == "failed"
        assert len(doc.errors) > 0
        assert doc.errors[0]["error_code"] == "FILE_NOT_FOUND"

    def test_empty_file_returns_failed(self, tmp_path):
        f = tmp_path / "empty.pdf"
        f.write_bytes(b"")
        doc = parse_document(str(f))
        assert doc.status == "failed"

    def test_unsupported_format_returns_failed(self, tmp_path):
        f = tmp_path / "bad.xyz"
        f.write_bytes(b"bad content")
        doc = parse_document(str(f))
        assert doc.status == "failed"
        assert doc.errors[0]["error_code"] == "UNSUPPORTED_FORMAT"

    def test_result_has_required_fields(self, tmp_path):
        # Use a real minimal PDF to test structure
        f = tmp_path / "dummy.pdf"
        f.write_bytes(b"%PDF-1.4\n%%EOF")
        doc = parse_document(str(f))
        # Even a failed parse should return a structured result
        assert hasattr(doc, "document_id")
        assert hasattr(doc, "filename")
        assert hasattr(doc, "status")
        assert hasattr(doc, "blocks")
        assert hasattr(doc, "errors")


class TestMockData:
    def test_mock_document_is_valid(self):
        assert MOCK_DOCUMENT.document_id == "doc_mock_001"
        assert len(MOCK_DOCUMENT.blocks) == 6

    def test_mock_blocks_have_all_types(self):
        types = {b.type for b in MOCK_DOCUMENT.blocks}
        assert "heading" in types
        assert "paragraph" in types
        assert "table" in types
        assert "figure" in types
        assert "equation" in types

    def test_mock_has_flagged_block(self):
        flagged = [b for b in MOCK_DOCUMENT.blocks if b.status == "needs_review"]
        assert len(flagged) >= 1
        assert "arith_fail" in flagged[0].flags

    def test_mock_serializes_to_json(self):
        data = MOCK_DOCUMENT.model_dump()
        dumped = json.dumps(data)
        assert "blk_001" in dumped
