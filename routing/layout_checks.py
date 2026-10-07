from typing import Iterable


def valid_bbox(bbox: list[float]) -> bool:
    if len(bbox) != 4:
        return False

    x1, y1, x2, y2 = bbox

    return x2 > x1 and y2 > y1


def bbox_width(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0])


def bbox_height(bbox: list[float]) -> float:
    return max(0.0, bbox[3] - bbox[1])


def bbox_area(bbox: list[float]) -> float:
    return bbox_width(bbox) * bbox_height(bbox)


def center_x(bbox: list[float]) -> float:
    return (bbox[0] + bbox[2]) / 2.0


def center_y(bbox: list[float]) -> float:
    return (bbox[1] + bbox[3]) / 2.0


def horizontal_overlap(a: list[float], b: list[float]) -> float:
    left = max(a[0], b[0])
    right = min(a[2], b[2])

    return max(0.0, right - left)


def vertical_overlap(a: list[float], b: list[float]) -> float:
    top = max(a[1], b[1])
    bottom = min(a[3], b[3])

    return max(0.0, bottom - top)


def horizontal_overlap_ratio(a: list[float], b: list[float]) -> float:
    overlap = horizontal_overlap(a, b)

    width = min(
        bbox_width(a),
        bbox_width(b)
    )

    if width <= 0:
        return 0.0

    return overlap / width


def vertical_overlap_ratio(a: list[float], b: list[float]) -> float:
    overlap = vertical_overlap(a, b)

    height = min(
        bbox_height(a),
        bbox_height(b)
    )

    if height <= 0:
        return 0.0

    return overlap / height


def contains_bbox(
    outer: list[float],
    inner: list[float]
) -> bool:

    return (
        inner[0] >= outer[0]
        and inner[1] >= outer[1]
        and inner[2] <= outer[2]
        and inner[3] <= outer[3]
    )


def horizontal_gap(
    a: list[float],
    b: list[float]
) -> float:

    if horizontal_overlap(a, b) > 0:
        return 0.0

    if a[2] <= b[0]:
        return b[0] - a[2]

    return a[0] - b[2]


def vertical_gap(
    a: list[float],
    b: list[float]
) -> float:

    if vertical_overlap(a, b) > 0:
        return 0.0

    if a[3] <= b[1]:
        return b[1] - a[3]

    return a[1] - b[3]


def is_full_width(
    bbox: list[float],
    page_width: float,
    tolerance: float = 0.10
) -> bool:

    if page_width <= 0 or not valid_bbox(bbox):
        return False

    left_margin = bbox[0]
    right_margin = page_width - bbox[2]

    allowed_margin = page_width * tolerance

    return (
        left_margin <= allowed_margin
        and right_margin <= allowed_margin
    )


def validate_regions(
    regions: Iterable,
    page_width: float,
    page_height: float
) -> list[str]:

    errors = []

    for region in regions:

        bbox = region.bbox

        if not valid_bbox(bbox):
            errors.append(
                f"{region.region_id}: invalid bounding box"
            )
            continue

        if bbox[0] < 0 or bbox[1] < 0:
            errors.append(
                f"{region.region_id}: bbox starts outside page"
            )

        if bbox[2] > page_width or bbox[3] > page_height:
            errors.append(
                f"{region.region_id}: bbox extends outside page"
            )

    return errors