"""Crop, coordinate conversion, and the one Block builder every extractor uses."""

from typing import Any

from extractors.schema_ref import load_schema

_schema = load_schema()
Block = _schema.Block
ConfidenceInfo = _schema.ConfidenceInfo
SourceInfo = _schema.SourceInfo


def region_field(region, name: str, default=None):
    if isinstance(region, dict):
        return region.get(name, default)
    return getattr(region, name, default)


def to_top_left(bbox, page_height: float, origin: str = "top-left") -> list[float]:
    """Return [x1, y1, x2, y2] with origin at the top-left of the page."""
    if len(bbox) != 4:
        raise ValueError("bbox must have four numbers")
    x1, y1, x2, y2 = (float(value) for value in bbox)
    if origin == "top-left":
        return [x1, y1, x2, y2]
    if origin == "bottom-left":
        return [x1, page_height - y2, x2, page_height - y1]
    raise ValueError(f"Unknown bbox origin: {origin}")


def crop_region(page_image, bbox, page_size):
    """Crop a page image. bbox is in page points, origin top-left."""
    from PIL import Image

    image = page_image if isinstance(page_image, Image.Image) else Image.open(page_image)
    if len(bbox) != 4:
        raise ValueError("bbox must have four numbers")
    width = float(page_size["width"])
    height = float(page_size["height"])
    if width <= 0 or height <= 0:
        raise ValueError("page_size width and height must be positive")
    scale_x = image.width / width
    scale_y = image.height / height
    x1, y1, x2, y2 = (float(value) for value in bbox)
    box = (
        int(round(x1 * scale_x)),
        int(round(y1 * scale_y)),
        int(round(x2 * scale_x)),
        int(round(y2 * scale_y)),
    )
    return image.crop(box)


def make_block(
    *,
    extractor: str,
    bbox: list[float],
    page_start: int,
    extraction: float,
    block_type: str = "paragraph",
    content: Any = None,
    page_end: int | None = None,
    region_id: str | None = None,
    index: int = 0,
    block_id: str | None = None,
    status: str = "accepted",
    flags: list[str] | None = None,
    history: list[dict[str, Any]] | None = None,
    source_file: str = "",
    sheet: str | None = None,
    cell_range: str | None = None,
    slide: int | None = None,
) -> Block:
    """Build one Block. P2 and P4 overwrite order, risk, and the final score."""
    box = [float(value) for value in bbox]
    if len(box) != 4:
        raise ValueError("bbox must have four numbers")
    identity = block_id or f"blk_{region_id or 'region'}_{index}"
    return Block(
        id=identity,
        type=block_type,
        content=content,
        page_start=page_start,
        page_end=page_end,
        bbox=box,
        bbox_by_page={str(page_start): box},
        reading_order=0,
        order_confidence=0.0,
        region=region_id,
        extractor=extractor,
        confidence=ConfidenceInfo(
            extraction=extraction,
            structure=0.0,
            source_quality=0.0,
            final=extraction,
        ),
        risk="LOW",
        status=status,
        flags=list(flags or []),
        history=list(history or []),
        source=SourceInfo(
            file=source_file,
            page=page_start,
            bbox=box,
            sheet=sheet,
            cell_range=cell_range,
            slide=slide,
        ),
    )


def failed_block(region, *, error_code: str, message: str, extractor: str = "dispatcher") -> Block:
    """One failed block. The region error stays on the block and does not raise."""
    page = region_field(region, "page", 0) or 0
    bbox = region_field(region, "bbox", None) or [0.0, 0.0, 0.0, 0.0]
    region_id = region_field(region, "id", "unknown")
    return make_block(
        extractor=extractor,
        bbox=list(bbox),
        page_start=int(page),
        extraction=0.0,
        content=None,
        region_id=str(region_id),
        status="failed",
        flags=[error_code.lower()],
        history=[
            {
                "engine": extractor,
                "confidence": 0.0,
                "note": message,
                "error_code": error_code,
            }
        ],
        source_file=str(region_field(region, "file", "") or ""),
    )
