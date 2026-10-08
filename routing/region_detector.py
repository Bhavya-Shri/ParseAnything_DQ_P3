from typing import Any

from routing.structure import (
    covered_by_structure,
    formula_or_furniture,
    structural_regions,
)
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
    regions = structural_regions(page, profile)

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

        if covered_by_structure(bbox, regions):
            continue

        pieces = _split_on_column_gap(page, bbox, profile.width) or [(text, bbox)]
        for piece_text, piece_bbox in pieces:
            formula_type, is_header, is_footer = formula_or_furniture(
                piece_text,
                piece_bbox,
                profile.height,
            )
            region_type = formula_type or _classify_text_region(piece_text, piece_bbox)
            regions.append(
                Region(
                    region_id=f"p{profile.page_number}_r{region_number}",
                    page_number=profile.page_number,
                    region_type=region_type,
                    bbox=piece_bbox,
                    confidence=_region_confidence(
                        piece_text,
                        piece_bbox,
                        profile.width,
                        profile.height,
                    ),
                    source="pymupdf",
                    text=piece_text,
                    is_full_width=is_full_width(piece_bbox, profile.width),
                    is_header=is_header,
                    is_footer=is_footer,
                )
            )
            region_number += 1

    return regions


def _split_on_column_gap(page, bbox: list[float], page_width: float) -> list[tuple[str, list[float]]] | None:
    """Split one PDF block when a gap shows the line belongs to two columns."""
    words = []
    for word in page.get_text("words"):
        center_x = (float(word[0]) + float(word[2])) / 2
        center_y = (float(word[1]) + float(word[3])) / 2
        if bbox[0] - 1 <= center_x <= bbox[2] + 1 and bbox[1] - 1 <= center_y <= bbox[3] + 1:
            words.append(word)
    if len(words) < 2:
        return None

    gap_limit = max(36.0, page_width * 0.06)
    lines: dict[int, list] = {}
    for word in words:
        lines.setdefault(int(word[6]), []).append(word)

    pieces = []
    for line_no in sorted(lines, key=lambda key: min(float(word[1]) for word in lines[key])):
        line_words = sorted(lines[line_no], key=lambda word: float(word[0]))
        groups = [[line_words[0]]]
        for word in line_words[1:]:
            gap = float(word[0]) - float(groups[-1][-1][2])
            if gap > gap_limit:
                groups.append([word])
            else:
                groups[-1].append(word)
        pieces.extend(groups)

    if len(pieces) <= 1:
        return None

    result = []
    for group in pieces:
        text = _clean_text(" ".join(str(word[4]) for word in group))
        if not text:
            continue
        result.append(
            (
                text,
                [
                    min(float(word[0]) for word in group),
                    min(float(word[1]) for word in group),
                    max(float(word[2]) for word in group),
                    max(float(word[3]) for word in group),
                ],
            )
        )
    return result or None


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
    layout_regions: list[Region],
    page_width: float = 0.0,
) -> list[Region]:

    if not layout_regions:
        return _drop_duplicate_regions(native_regions, page_width)

    if not native_regions:
        return _drop_duplicate_regions(layout_regions, page_width)

    merged = list(layout_regions)
    structural = {"table", "chart", "figure", "formula", "equation"}

    for native in native_regions:
        matched = False

        for layout in layout_regions:
            layout_width = layout.bbox[2] - layout.bbox[0]
            if (
                layout.region_type not in structural
                and page_width > 0
                and layout_width > page_width * 0.55
            ):
                continue

            native_mid_x = (native.bbox[0] + native.bbox[2]) / 2
            native_mid_y = (native.bbox[1] + native.bbox[3]) / 2
            if not (
                layout.bbox[0] <= native_mid_x <= layout.bbox[2]
                and layout.bbox[1] <= native_mid_y <= layout.bbox[3]
            ):
                continue

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

    width = page_width or max((region.bbox[2] for region in merged if region.bbox), default=0.0)
    return _drop_duplicate_regions(merged, width)


def _region_text(region: Region) -> str:
    return " ".join(region.text.split())


def _box_area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _overlap_area(left: list[float], right: list[float]) -> float:
    width = min(left[2], right[2]) - max(left[0], right[0])
    height = min(left[3], right[3]) - max(left[1], right[1])
    if width <= 1 or height <= 1:
        return 0.0
    return width * height


def _crosses_column_gap(outer: Region, regions: list[Region], drop: set[int]) -> bool:
    """A short wide box is a joined column heading when two pieces sit inside it."""
    height = outer.bbox[3] - outer.bbox[1]
    if height >= 36:
        return False
    pieces = []
    for index, region in enumerate(regions):
        if region is outer or index in drop:
            continue
        mid_x = (region.bbox[0] + region.bbox[2]) / 2
        mid_y = (region.bbox[1] + region.bbox[3]) / 2
        if outer.bbox[0] <= mid_x <= outer.bbox[2] and outer.bbox[1] <= mid_y <= outer.bbox[3]:
            pieces.append(region)
    if len(pieces) < 2:
        return False
    pieces.sort(key=lambda region: region.bbox[0])
    return any(right.bbox[0] - left.bbox[2] > 36 for left, right in zip(pieces, pieces[1:]))


def _drop_duplicate_regions(regions: list[Region], page_width: float) -> list[Region]:
    """Keep one box when layout and native detection describe the same lines.

    A line that sits inside a column-width box is dropped, because extraction
    reads every word inside the box. A box wider than the column is dropped
    when smaller regions already cover it, so the two columns stay separate.
    A table, chart, or formula box is kept and the text inside it is dropped.
    """
    structural = {"table", "chart", "figure", "formula", "equation"}
    drop: set[int] = set()
    for index, region in enumerate(regions):
        text = _region_text(region)
        if not text:
            continue
        for earlier in range(index):
            if earlier in drop:
                continue
            other = regions[earlier]
            same_line = min(region.bbox[3], other.bbox[3]) - max(region.bbox[1], other.bbox[1]) > 2
            if _region_text(other) == text and same_line:
                drop.add(index)
                break

    for index, inner in enumerate(regions):
        if index in drop:
            continue
        inner_area = _box_area(inner.bbox)
        if inner_area <= 0:
            continue
        for outer_index, outer in enumerate(regions):
            if index == outer_index or outer_index in drop:
                continue
            outer_area = _box_area(outer.bbox)
            if outer_area <= inner_area * 1.15:
                continue
            if _overlap_area(inner.bbox, outer.bbox) / inner_area < 0.8:
                continue
            if outer.region_type in structural:
                drop.add(index)
                break
            if inner.region_type in structural:
                drop.add(outer_index)
                continue
            outer_width = outer.bbox[2] - outer.bbox[0]
            outer_height = outer.bbox[3] - outer.bbox[1]
            inner_mid = (inner.bbox[1] + inner.bbox[3]) / 2
            tall_and_wide = (
                page_width > 0
                and outer_width > page_width * 0.55
                and outer_height >= 36
            )
            if tall_and_wide or _crosses_column_gap(outer, regions, drop):
                drop.add(outer_index)
                continue
            if outer_height < 36 and not (outer.bbox[1] <= inner_mid <= outer.bbox[3]):
                continue
            drop.add(index)
            break

    return [region for index, region in enumerate(regions) if index not in drop]


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
        layout_regions,
        profile.width,
    )

    return regions