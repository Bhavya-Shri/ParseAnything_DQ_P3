from dataclasses import dataclass, field
from typing import Any


@dataclass
class Region:
    region_id: str
    page_number: int
    region_type: str
    bbox: list[float]

    confidence: float = 1.0
    source: str = "native"
    text: str = ""

    column_id: int | None = None
    reading_order: int | None = None

    is_full_width: bool = False
    is_header: bool = False
    is_footer: bool = False

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Column:
    column_id: int
    x_start: float
    x_end: float

    region_ids: list[str] = field(default_factory=list)

    confidence: float = 1.0


@dataclass
class PageProfile:
    page_number: int

    width: float
    height: float

    has_native_text: bool
    text_block_count: int
    image_count: int

    text_density: float

    is_scanned: bool
    is_sparse: bool

    estimated_columns: int
    column_confidence: float

    has_tables: bool
    has_figures: bool
    has_formula_like_regions: bool

    complexity: str

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteDecision:
    region_id: str

    route: str
    extractor: str

    confidence: float

    reason: str

    priority: str = "normal"


@dataclass
class AssemblyResult:
    blocks: list[Any]

    page_count: int
    block_count: int

    warnings: list[str] = field(default_factory=list)

    metadata: dict[str, Any] = field(default_factory=dict)