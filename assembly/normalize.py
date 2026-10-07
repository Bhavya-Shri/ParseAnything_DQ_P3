from typing import Any

from routing.route_models import Region


TYPE_MAP = {
    "text": "paragraph",
    "paragraph": "paragraph",
    "heading": "heading",
    "table": "table",
    "figure": "figure",
    "chart": "chart",
    "formula": "equation",
    "equation": "equation",
    "caption": "caption",
    "footnote": "footnote",
    "header": "header",
    "footer": "footer",
    "list": "list",
    "numeric": "numeric",
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalize_region_type(
    region_type: str,
) -> str:
    return TYPE_MAP.get(
        region_type.lower(),
        "paragraph",
    )


def normalize_bbox(
    bbox: list[float],
) -> list[float]:
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


def normalize_text(
    text: Any,
) -> Any:
    if text is None:
        return ""

    if not isinstance(text, str):
        return text

    return " ".join(
        text.split()
    )


def normalize_region(
    region: Region,
) -> dict[str, Any]:

    bbox = normalize_bbox(
        region.bbox
    )

    region_type = normalize_region_type(
        region.region_type
    )

    content = normalize_text(
        region.text
    )

    order_confidence = region.metadata.get(
        "order_confidence",
        region.confidence,
    )

    try:
        order_confidence = float(
            order_confidence
        )
    except (TypeError, ValueError):
        order_confidence = region.confidence

    order_confidence = _clamp(
        order_confidence
    )

    normalized = {
        "region_id": region.region_id,
        "page_number": region.page_number,
        "type": region_type,
        "content": content,
        "bbox": bbox,
        "reading_order": region.reading_order,
        "order_confidence": order_confidence,
        "region_confidence": _clamp(
            region.confidence
        ),
        "source": region.source,
        "column_id": region.column_id,
        "is_full_width": region.is_full_width,
        "is_header": region.is_header,
        "is_footer": region.is_footer,
        "metadata": dict(
            region.metadata
        ),
    }

    return normalized


def normalize_regions(
    regions: list[Region],
) -> list[dict[str, Any]]:

    normalized = []

    for region in regions:
        normalized.append(
            normalize_region(
                region
            )
        )

    return normalized


def sort_normalized_regions(
    regions: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    return sorted(
        regions,
        key=lambda region: (
            region["page_number"],
            (
                region["reading_order"]
                if region["reading_order"] is not None
                else float("inf")
            ),
            region["bbox"][1],
            region["bbox"][0],
        ),
    )



def normalize_block(
    block: Any,
) -> dict[str, Any]:

    if isinstance(block, Region):
        return normalize_region(block)

    if isinstance(block, dict):
        normalized = dict(block)

        if "type" in normalized:
            normalized["type"] = normalize_region_type(
                str(normalized["type"])
            )

        if "bbox" in normalized:
            normalized["bbox"] = normalize_bbox(
                normalized["bbox"]
            )

        if "content" in normalized:
            normalized["content"] = normalize_text(
                normalized["content"]
            )

        if "order_confidence" in normalized:
            normalized["order_confidence"] = _clamp(
                float(normalized["order_confidence"])
            )

        return normalized

    raise TypeError(
        "Block must be a Region or dictionary"
    )


def normalize_blocks(
    blocks: list[Any],
) -> list[dict[str, Any]]:

    normalized = []

    for block in blocks:
        normalized.append(
            normalize_block(block)
        )

    return normalized