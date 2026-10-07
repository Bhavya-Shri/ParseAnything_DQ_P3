"""Public extraction entry for P1.

    extract(region, context) -> list[Block]

Routes that return blocks today:
    skip, native_text, ocr, docling_table, paddle_table, office, formula, chart

P1 can also call extract_document(path) for a whole DOCX, XLSX, or PPTX.
P4 and P5 call read_crop(image, task, hint) and vlm_call_count() for a single hard crop.

An unknown route returns a failed block.
"""

from extractors.base import Extractor
from extractors.schema_ref import load_schema
from extractors.utils import failed_block, region_field

Block = load_schema().Block

RESERVED_ROUTES = (
    "native_text",
    "ocr",
    "docling_table",
    "paddle_table",
    "chart",
    "formula",
    "office",
)

_REGISTRY: dict[str, Extractor] = {}


def register(route: str, extractor: Extractor) -> None:
    if route == "skip":
        raise ValueError("skip is not an extractor")
    _REGISTRY[route] = extractor


def unregister(route: str) -> None:
    _REGISTRY.pop(route, None)


def registered_routes() -> tuple[str, ...]:
    return tuple(_REGISTRY)


def extract(region, context=None) -> list[Block]:
    """Read one region. A bad region returns a failed block and does not raise."""
    context = context or {}
    try:
        route = region_field(region, "route")
        if route == "skip":
            return []
        extractor = _REGISTRY.get(route) if route else None
        if extractor is None and not route:
            extractor = _first_handler(region)
        if extractor is None:
            return [
                failed_block(
                    region,
                    error_code="INTERNAL_ERROR",
                    message=f"No extractor for route {route!r}",
                )
            ]
        if not extractor.can_handle(region):
            return [
                failed_block(
                    region,
                    error_code="INTERNAL_ERROR",
                    message=f"{extractor.name} cannot handle route {route!r}",
                    extractor=extractor.name,
                )
            ]
        return extractor.extract(region, context)
    except Exception as exc:
        return [
            failed_block(
                region,
                error_code="INTERNAL_ERROR",
                message=f"{type(exc).__name__}: {exc}",
            )
        ]


def _first_handler(region) -> Extractor | None:
    for extractor in _REGISTRY.values():
        if extractor.can_handle(region):
            return extractor
    return None


from extractors.native_text import NativeTextExtractor
from extractors.ocr import OcrExtractor
from extractors.charts import ChartExtractor
from extractors.equations import EquationExtractor
from extractors.office import OfficeExtractor, extract_document
from extractors.tables import TableExtractor
from extractors.vlm import read_crop, vlm_call_count

register("native_text", NativeTextExtractor())
register("ocr", OcrExtractor())
register("docling_table", TableExtractor(scanned=False))
register("paddle_table", TableExtractor(scanned=True))
register("office", OfficeExtractor())
register("formula", EquationExtractor())
register("chart", ChartExtractor())

__all__ = ["extract", "extract_document", "read_crop", "register", "unregister", "vlm_call_count"]
