"""Public extraction entry for P1.

    from extractors import extract, extract_document, read_crop, vlm_call_count
    extract(region, context) -> list[Block]

This repo has no pipeline/orchestrator.py. That file belongs to P1.
P1 imports extract from here. Office files can also use extract_document(path).
P4 and P5 use read_crop and vlm_call_count for one hard crop.

Routes that return blocks:
    skip, native_text, ocr, docling_table, paddle_table, office, formula, chart, figure

An unknown route returns one failed block. It does not return an empty success.

Not claimed:
    paddle_table's live model was not run; a failure returns TABLE_FAILED
    Docling's table fallback was not needed for table.pdf and was not run
    no live VLM call; a missing key returns vlm_unavailable
    line charts and charts without printed values are not read
    pipeline/schema.py is the live Block. The stub remains only as a fallback

No new routes after this handoff.
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
from extractors.figures import FigureExtractor
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
register("figure", FigureExtractor())

__all__ = ["extract", "extract_document", "read_crop", "register", "unregister", "vlm_call_count"]
