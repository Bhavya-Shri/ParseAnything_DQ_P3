import pathlib
import uuid
from typing import Dict, Any
from pipeline.schema import ParseError
from pipeline.errors import ParseAnythingException

def preflight_check(file_path: str) -> Dict[str, Any]:
    """
    Phase A — Preflight checks (size, extension, exists).
    """
    path = pathlib.Path(file_path)
    trace_id = str(uuid.uuid4())
    
    if not path.exists():
        raise ParseAnythingException(
            ParseError(
                status="failed",
                error_code="FILE_NOT_FOUND",
                message="The specified file does not exist.",
                recoverable=False,
                stage="preflight",
                trace_id=trace_id
            )
        )
        
    size = path.stat().st_size
    if size == 0:
        raise ParseAnythingException(
            ParseError(
                status="failed",
                error_code="EMPTY_DOCUMENT",
                message="The file is empty.",
                recoverable=False,
                stage="preflight",
                trace_id=trace_id
            )
        )
        
    ext = path.suffix.lower().lstrip(".")
    supported = {"pdf", "docx", "xlsx", "pptx", "png", "jpg", "jpeg"}
    
    if ext not in supported:
        raise ParseAnythingException(
            ParseError(
                status="failed",
                error_code="UNSUPPORTED_FORMAT",
                message=f"Format '{ext}' is not supported.",
                recoverable=False,
                stage="preflight",
                trace_id=trace_id
            )
        )
        
    return {
        "ok": True,
        "format": ext,
        "filename": path.name,
        "size_bytes": size,
        "trace_id": trace_id
    }
