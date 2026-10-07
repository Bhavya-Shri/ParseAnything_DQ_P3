"""Temporary copy of P1's Block contract.

Delete this module when pipeline/schema.py exists. Do not add fields here.
Ask P1 to change the real schema, then delete this file.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

BlockType = Literal[
    "heading",
    "paragraph",
    "list",
    "table",
    "figure",
    "chart",
    "equation",
    "caption",
    "footnote",
    "header",
    "footer",
    "numeric",
]

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

BlockStatus = Literal[
    "verified",
    "accepted",
    "needs_review",
    "failed",
    "unaudited",
]


class VerificationResult(BaseModel):
    method: str | None = None
    agreement: float | None = None
    conflict: bool = False
    secondary_value: Any | None = None


class SourceInfo(BaseModel):
    file: str
    page: int | None = None
    bbox: list[float] | None = None
    sheet: str | None = None
    cell_range: str | None = None
    slide: int | None = None


class ConfidenceInfo(BaseModel):
    extraction: float = Field(ge=0.0, le=1.0)
    structure: float = Field(ge=0.0, le=1.0)
    source_quality: float = Field(ge=0.0, le=1.0)
    final: float = Field(ge=0.0, le=1.0)


class Block(BaseModel):
    id: str
    type: BlockType
    content: Any

    page_start: int
    page_end: int | None = None

    bbox: list[float]
    bbox_by_page: dict[str, list[float]] = Field(default_factory=dict)

    reading_order: int
    order_confidence: float = Field(ge=0.0, le=1.0)
    region: str | None = None

    extractor: str

    confidence: ConfidenceInfo

    risk: RiskLevel
    status: BlockStatus

    verification: VerificationResult | None = None

    flags: list[str] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)

    source: SourceInfo
    links: dict[str, Any] = Field(default_factory=dict)
