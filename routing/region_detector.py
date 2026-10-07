from typing import Any

from .layout_checks import is_full_width, valid_bbox
from .route_models import PageProfile, Region


def _clean_text(text: str) -> str:
    return " ".join(str(text).split())


def _classify_text_region(text: str, bbox: list[float]) -> str:
    words = text.split()

    if len(words) <= 12 and len(text) <= 120:
        if text.isupper():
            return "heading"

        if text.endswith(":"):
            return "heading"

    height = bbox[3] - bbox[1]

    if height > 30 and len(words) <= 20:
        return "heading"

    return "text"


def _region_confidence(
    text: str,
    bbox: list[float],
    page_width: float,
    page_height: float
) -> float:
    if not valid_bbox(bbox):
        return 0.0

    confidence = 0.70

    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]

    if width > 0 and height > 0:
        confidence += 0.10

    if page_width > 0 and page_height > 0:
        if (
            bbox[0] >= 0
            and bbox[1] >= 0
            and bbox[2] <= page_width
            and bbox[3] <= page_height
        ):
            confidence += 0.10

    if text.strip():
        confidence += 0.10

    return min(1.0, confidence)


def detect_native_regions(
    page,
    profile: PageProfile
) -> list[Region]:
    regions = []

    try:
        blocks = page.get_text("blocks")
    except Exception:
        return regions

    region_number = 0

    for block in blocks:
        if len(block) < 5:
            continue

        x1, y1, x2, y2 = block[:4]
        raw_text = str(block[4])
        text = _clean_text(raw_text)

        if not text:
            continue

        bbox = [
            float(x1),
            float(y1),
            float(x2),
            float(y2),
        ]

        if not valid_bbox(bbox):
            continue

        region_type = _classify_text_region(text, bbox)

        full_width = is_full_width(
            bbox,
            profile.width
        )

        confidence = _region_confidence(
            text,
            bbox,
            profile.width,
            profile.height
        )

        regions.append(
            Region(
                region_id=f"p{profile.page_number}_r{region_number}",
                page_number=profile.page_number,
                region_type=region_type,
                bbox=bbox,
                confidence=confidence,
                source="pymupdf",
                text=text,
                is_full_width=full_width,
            )
        )

        region_number += 1

    return regions


def _normalize_layout_box(
    item: Any
) -> tuple[str, float, list[float], float] | None:

    if not isinstance(item, dict):
        return None

    label = str(
        item.get("label")
        or item.get("type")
        or "unknown"
    )

    score = item.get(
        "score",
        item.get("confidence", 0.0)
    )

    coordinate = (
        item.get("coordinate")
        or item.get("bbox")
        or item.get("box")
    )

    if coordinate is None:
        return None

    try:
        bbox = [float(value) for value in coordinate]
        score = float(score)
    except (TypeError, ValueError):
        return None

    if len(bbox) != 4 or not valid_bbox(bbox):
        return None

    return label, score, bbox, max(0.0, min(1.0, score))


def detect_layout_regions(
    layout_result: Any,
    profile: PageProfile
) -> list[Region]:

    regions = []

    if layout_result is None:
        return regions

    if isinstance(layout_result, dict):
        items = (
            layout_result.get("boxes")
            or layout_result.get("regions")
            or layout_result.get("layout")
            or []
        )
    elif isinstance(layout_result, list):
        items = layout_result
    else:
        items = []

    for index, item in enumerate(items):
        normalized = _normalize_layout_box(item)

        if normalized is None:
            continue

        label, _, bbox, score = normalized

        label = label.lower()

        if "table" in label:
            region_type = "table"
        elif "formula" in label or "equation" in label:
            region_type = "formula"
        elif "chart" in label:
            region_type = "chart"
        elif (
            "image" in label
            or "figure" in label
            or "picture" in label
        ):
            region_type = "figure"
        elif "title" in label or "header" in label:
            region_type = "heading"
        elif "footer" in label:
            region_type = "footer"
        else:
            region_type = "text"

        full_width = is_full_width(
            bbox,
            profile.width
        )

        regions.append(
            Region(
                region_id=f"p{profile.page_number}_layout_{index}",
                page_number=profile.page_number,
                region_type=region_type,
                bbox=bbox,
                confidence=score,
                source="layout_model",
                is_full_width=full_width,
                is_header=(
                    "header" in label
                    or "page_header" in label
                ),
                is_footer=(
                    "footer" in label
                    or "page_footer" in label
                ),
                metadata={
                    "layout_label": label,
                },
            )
        )

    return regions


def merge_region_sources(
    native_regions: list[Region],
    layout_regions: list[Region]
) -> list[Region]:

    if not layout_regions:
        return native_regions

    if not native_regions:
        return layout_regions

    merged = list(layout_regions)

    for native in native_regions:
        matched = False

        for layout in layout_regions:
            horizontal = min(
                native.bbox[2],
                layout.bbox[2]
            ) - max(
                native.bbox[0],
                layout.bbox[0]
            )

            vertical = min(
                native.bbox[3],
                layout.bbox[3]
            ) - max(
                native.bbox[1],
                layout.bbox[1]
            )

            if horizontal <= 0 or vertical <= 0:
                continue

            native_area = (
                (native.bbox[2] - native.bbox[0])
                * (native.bbox[3] - native.bbox[1])
            )

            if native_area <= 0:
                continue

            overlap_area = horizontal * vertical
            overlap_ratio = overlap_area / native_area

            if overlap_ratio >= 0.60:
                matched = True

                if layout.region_type == "text":
                    layout.text = native.text

                layout.metadata["native_region_id"] = (
                    native.region_id
                )

                break

        if not matched:
            merged.append(native)

    return merged


def detect_regions(
    page,
    profile: PageProfile,
    layout_result: Any = None
) -> list[Region]:

    native_regions = detect_native_regions(
        page,
        profile
    )

    layout_regions = detect_layout_regions(
        layout_result,
        profile
    )

    regions = merge_region_sources(
        native_regions,
        layout_regions
    )

    return regions