"""
test_failures.py — P1 owned
Tests that every failure mode produces the correct structured error.
Run: pytest tests/test_failures.py -v
"""
import pytest
from pipeline.orchestrator import parse_document


class TestFailureModes:

    def test_missing_file_returns_structured_error(self):
        doc = parse_document("/does/not/exist.pdf")
        assert doc.status == "failed"
        assert doc.errors[0]["error_code"] == "FILE_NOT_FOUND"
        assert doc.errors[0]["recoverable"] is False
        assert doc.errors[0]["stage"] == "preflight"
        assert doc.errors[0]["trace_id"] != ""

    def test_empty_file_returns_structured_error(self, tmp_path):
        f = tmp_path / "empty.pdf"
        f.write_bytes(b"")
        doc = parse_document(str(f))
        assert doc.status == "failed"
        assert doc.errors[0]["error_code"] == "EMPTY_DOCUMENT"

    def test_unsupported_extension_returns_structured_error(self, tmp_path):
        f = tmp_path / "archive.rar"
        f.write_bytes(b"Rar!\x1a\x07")
        doc = parse_document(str(f))
        assert doc.status == "failed"
        assert doc.errors[0]["error_code"] == "UNSUPPORTED_FORMAT"
        assert doc.errors[0]["recoverable"] is False

    def test_wrong_extension_masked_as_pdf(self, tmp_path):
        # A ZIP file renamed to .pdf — preflight accepts based on extension
        # but Docling/PyMuPDF will fail during ingestion
        f = tmp_path / "fake.pdf"
        f.write_bytes(b"PK\x03\x04 this is a zip file not a pdf")
        doc = parse_document(str(f))
        # Should either fail gracefully or return partial — must not crash
        assert doc.status in ("failed", "partial", "complete")
        assert isinstance(doc.errors, list)

    def test_error_object_has_all_required_fields(self, tmp_path):
        f = tmp_path / "empty.docx"
        f.write_bytes(b"")
        doc = parse_document(str(f))
        assert doc.status == "failed"
        err = doc.errors[0]
        for field in ["status", "error_code", "message", "recoverable", "stage", "trace_id"]:
            assert field in err, f"Missing field: {field}"

    def test_failed_parse_returns_no_blocks(self):
        doc = parse_document("/nonexistent/file.pdf")
        assert doc.blocks == []

    def test_result_never_crashes_on_bad_input(self, tmp_path):
        """The pipeline must always return a DocumentResult, never raise uncaught."""
        inputs = [
            "/no/such/file.pdf",
            str(tmp_path / "empty.xlsx"),
            str(tmp_path / "unsupported.msg"),
        ]
        (tmp_path / "empty.xlsx").write_bytes(b"")
        (tmp_path / "unsupported.msg").write_bytes(b"message content")

        for path in inputs:
            result = parse_document(path)
            assert result is not None
            assert hasattr(result, "status")
