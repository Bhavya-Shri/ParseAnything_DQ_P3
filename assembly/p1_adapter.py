from typing import Any


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalize_type(value: Any) -> str:
    value = str(value or "paragraph").lower()

    if value == "text":
        return "paragraph"

    if value == "formula":
        return "equation"

    allowed = {
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
    }

    if value in allowed:
        return value

    return "paragraph"


def _normalize_bbox(bbox: Any) -> list[float]:
    if not isinstance(bbox, (list, tuple)):
        raise ValueError(
            "Bounding box must be a list or tuple"
        )

    if len(bbox) != 4:
        raise ValueError(
            "Bounding box must contain four values"
        )

    values = [
        float(value)
        for value in bbox
    ]

    x1, y1, x2, y2 = values

    if x2 < x1:
        x1, x2 = x2, x1

    if y2 < y1:
        y1, y2 = y2, y1

    return [
        x1,
        y1,
        x2,
        y2,
    ]


def _get_page_start(
    block: dict[str, Any],
) -> int:

    value = block.get("page_start")

    if value is None:
        value = block.get("page_number")

    if value is None:
        raise ValueError(
            "Block must contain page_start or page_number"
        )

    return int(value)


def _get_page_end(
    block: dict[str, Any],
) -> int | None:

    value = block.get("page_end")

    if value is None:
        value = block.get("page_number")

    if value is None:
        return None

    return int(value)


def _get_reading_order(
    block: dict[str, Any],
) -> int:

    value = block.get("reading_order")

    if value is None:
        raise ValueError(
            "Block must contain reading_order"
        )

    return int(value)


def _get_order_confidence(
    block: dict[str, Any],
) -> float:

    value = block.get("order_confidence")

    if value is None:
        value = block.get(
            "region_confidence",
            0.0,
        )

    try:
        return _clamp(
            float(value)
        )
    except (TypeError, ValueError):
        return 0.0


def _build_bbox_by_page(
    block: dict[str, Any],
    page_start: int,
    page_end: int | None,
    bbox: list[float],
) -> dict[str, list[float]]:

    existing = block.get(
        "bbox_by_page"
    )

    if isinstance(existing, dict):
        result = {}

        for page, page_bbox in existing.items():
            try:
                result[str(page)] = _normalize_bbox(
                    page_bbox
                )
            except (TypeError, ValueError):
                continue

        if result:
            return result

    result = {
        str(page_start): list(bbox)
    }

    if (
        page_end is not None
        and page_end != page_start
    ):
        result[str(page_end)] = list(bbox)

    return result


def _build_source(
    block: dict[str, Any],
    file_name: str,
) -> dict[str, Any]:

    source = block.get("source")

    if isinstance(source, dict):
        result = dict(source)

        result["file"] = (
            result.get("file")
            or file_name
        )

        return result

    return {
        "file": file_name,
        "page": block.get(
            "page_number",
            block.get("page_start"),
        ),
        "bbox": block.get("bbox"),
        "sheet": block.get("sheet"),
        "cell_range": block.get("cell_range"),
        "slide": block.get("slide"),
    }


def _build_confidence(
    block: dict[str, Any],
    order_confidence: float,
) -> dict[str, float]:

    existing = block.get(
        "confidence"
    )

    if isinstance(existing, dict):
        result = dict(existing)

        for field in (
            "extraction",
            "structure",
            "source_quality",
            "final",
        ):
            if field in result:
                try:
                    result[field] = _clamp(
                        float(result[field])
                    )
                except (TypeError, ValueError):
                    result[field] = 0.0

        return result

    extraction = block.get(
        "extraction_confidence"
    )

    if extraction is None:
        extraction = block.get(
            "region_confidence",
            0.0,
        )

    structure = block.get(
        "structure_confidence",
        order_confidence,
    )

    source_quality = block.get(
        "source_quality",
        0.0,
    )

    final = block.get(
        "final_confidence"
    )

    if final is None:
        final = 0.0

    try:
        extraction = _clamp(
            float(extraction)
        )
    except (TypeError, ValueError):
        extraction = 0.0

    try:
        structure = _clamp(
            float(structure)
        )
    except (TypeError, ValueError):
        structure = 0.0

    try:
        source_quality = _clamp(
            float(source_quality)
        )
    except (TypeError, ValueError):
        source_quality = 0.0

    try:
        final = _clamp(
            float(final)
        )
    except (TypeError, ValueError):
        final = 0.0

    return {
        "extraction": extraction,
        "structure": structure,
        "source_quality": source_quality,
        "final": final,
    }


def adapt_block_to_p1(
    block: dict[str, Any],
    file_name: str,
) -> dict[str, Any]:

    if not isinstance(block, dict):
        raise TypeError(
            "P1 adapter expects a dictionary"
        )

    if not file_name:
        raise ValueError(
            "file_name is required"
        )

    page_start = _get_page_start(
        block
    )

    page_end = _get_page_end(
        block
    )

    bbox = _normalize_bbox(
        block.get("bbox")
    )

    reading_order = _get_reading_order(
        block
    )

    order_confidence = _get_order_confidence(
        block
    )

    block_id = block.get(
        "id",
        block.get("region_id"),
    )

    if block_id is None:
        raise ValueError(
            "Block must contain id or region_id"
        )

    content = block.get(
        "content",
        "",
    )

    extractor = block.get(
        "extractor"
    )

    if extractor is None:
        extractor = block.get(
            "route_extractor"
        )

    if extractor is None:
        extractor = "pending"

    confidence = _build_confidence(
        block,
        order_confidence,
    )

    result = {
        "id": str(block_id),

        "type": _normalize_type(
            block.get("type")
        ),

        "content": content,

        "page_start": page_start,

        "page_end": page_end,

        "bbox": bbox,

        "bbox_by_page": _build_bbox_by_page(
            block,
            page_start,
            page_end,
            bbox,
        ),

        "reading_order": reading_order,

        "order_confidence": order_confidence,

        "region": block.get(
            "region"
        ),

        "extractor": str(
            extractor
        ),

        "confidence": confidence,

        "risk": block.get(
            "risk",
            "LOW",
        ),

        "status": block.get(
            "status",
            "unaudited",
        ),

        "verification": block.get(
            "verification"
        ),

        "flags": list(
            block.get(
                "flags",
                [],
            )
        ),

        "history": list(
            block.get(
                "history",
                [],
            )
        ),

        "source": _build_source(
            block,
            file_name,
        ),

        "links": dict(
            block.get(
                "links",
                {},
            )
        ),
    }

    return result


def adapt_blocks_to_p1(
    blocks: list[dict[str, Any]],
    file_name: str,
) -> list[dict[str, Any]]:

    result = []

    for block in blocks:
        result.append(
            adapt_block_to_p1(
                block,
                file_name,
            )
        )

    return result