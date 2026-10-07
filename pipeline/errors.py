from typing import Optional
from pipeline.schema import ParseError

class ParseAnythingException(Exception):
    def __init__(self, error: ParseError):
        super().__init__(error.message)
        self.error = error

def create_error(code: str, msg: str, stage: str, recoverable: bool = False, page: Optional[int] = None) -> ParseError:
    return ParseError(
        status="error",
        error_code=code,
        message=msg,
        recoverable=recoverable,
        stage=stage,
        page=page,
        trace_id="000" # Placeholder trace id
    )
