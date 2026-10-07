from typing import Any

from .layout_checks import is_full_width, valid_bbox
from .route_models import PageProfile, Region


def _get_items(result: Any) -> list:
    if result is None:
        return []

    if isinstance(result, list):
        return result

    if isinstance(result, dict):
        for key in (
            "layout",
            "layout_res",
            "boxes",
            "regions",
            "result",
        ):
            value = result.get(key)

            if isinstance(value, list):
                return value

    return []


def _get_label(item: dict) -> str:
    value = (
        item.get("label")
        or item.get("type")
        or item.get("category")
        or "unknown"
    )

    return str(value).lower()


def _get_score(item: dict) -> float:
    value = (
        item.get("score")
        or item.get("confidence")
        or item.get("probability")
        or 0.0
    )

    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0

    return max(0.0, min(1.0, value))


def _get_bbox(item: dict) -> list[float] | None:
    coordinate = (
        item.get("coordinate")
        or item.get("bbox")
        or item.get("box")
        or item.get("points")
    )

    if coordinate is None:
        return None

    try:
        bbox = [
            float(value)
            for value in coordinate
        ]
    except (TypeError, ValueError):
        return None

    if len(bbox) != 4:
        return None

    if not valid_bbox(bbox):
        return None

    return bbox


def _map_region_type(label: str) -> str:
    if "table" in label:
        return "table"

    if (
        "formula" in label
        or "equation" in label
        or "formula" in label
    ):
        return "formula"

    if "chart" in label:
        return "chart"

    if (
        "figure" in label
        or "image" in label
        or "picture" in label
    ):
        return "figure"

    if (
        "title" in label
        or "heading" in label
    ):
        return "heading"

    if "header" in label:
        return "header"

    if "footer" in label:
        return "footer"

    if (
        "list" in label
        or "text" in label
        or "paragraph" in label
    ):
        return "text"

    return "unknown"


def _is_header(label: str) -> bool:
    return (
        "header" in label
        and "footer" not in label
    )


def _is_footer(label: str) -> bool:
    return "footer" in label


def _normalize_item(
    item: Any,
    index: int,
    profile: PageProfile,
) -> Region | None:

    if not isinstance(item, dict):
        return None

    bbox = _get_bbox(item)

    if bbox is None:
        return None

    label = _get_label(item)
    score = _get_score(item)

    region_type = _map_region_type(label)

    return Region(
        region_id=(
            f"p{profile.page_number}"
            f"_pp_{index}"
        ),
        page_number=profile.page_number,
        region_type=region_type,
        bbox=bbox,
        confidence=score,
        source="pp_structure_v3",
        is_full_width=is_full_width(
            bbox,
            profile.width,
        ),
        is_header=_is_header(label),
        is_footer=_is_footer(label),
        metadata={
            "layout_label": label,
            "layout_index": index,
            "layout_engine": "PP-StructureV3",
        },
    )


def adapt_layout_result(
    layout_result: Any,
    profile: PageProfile,
) -> list[Region]:

    items = _get_items(layout_result)

    regions = []

    for index, item in enumerate(items):
        region = _normalize_item(
            item,
            index,
            profile,
        )

        if region is not None:
            regions.append(region)

    return regions


def should_use_layout_model(
    profile: PageProfile,
) -> bool:

    if profile.is_scanned:
        return True

    if profile.complexity == "high":
        return True

    if profile.estimated_columns > 1:
        return True

    if profile.column_confidence < 0.50:
        return True

    if profile.has_tables:
        return True

    if profile.has_figures:
        return True

    if profile.has_formula_like_regions:
        return True

    return False