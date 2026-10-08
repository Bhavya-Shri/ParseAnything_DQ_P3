from typing import Any


def _bbox_width(bbox):
    return max(
        0.0,
        bbox[2] - bbox[0],
    )


def _bbox_height(bbox):
    return max(
        0.0,
        bbox[3] - bbox[1],
    )


def _horizontal_overlap_ratio(
    a,
    b,
):
    overlap = max(
        0.0,
        min(a[2], b[2]) - max(a[0], b[0]),
    )

    width = min(
        _bbox_width(a),
        _bbox_width(b),
    )

    if width <= 0:
        return 0.0

    return overlap / width


def _same_page_sequence(
    previous,
    current,
):
    previous_page = previous.get(
        "page_end",
        previous.get("page_number"),
    )

    current_page = current.get(
        "page_start",
        current.get("page_number"),
    )

    if (
        previous_page is None
        or current_page is None
    ):
        return False

    return current_page == previous_page + 1


def _similar_width(
    previous,
    current,
):
    previous_bbox = previous.get(
        "bbox",
        [0, 0, 0, 0],
    )

    current_bbox = current.get(
        "bbox",
        [0, 0, 0, 0],
    )

    previous_width = _bbox_width(
        previous_bbox
    )

    current_width = _bbox_width(
        current_bbox
    )

    if (
        previous_width <= 0
        or current_width <= 0
    ):
        return False

    ratio = (
        min(
            previous_width,
            current_width,
        )
        / max(
            previous_width,
            current_width,
        )
    )

    return ratio >= 0.80


def _same_column_count(
    previous,
    current,
):
    previous_columns = previous.get(
        "metadata",
        {},
    ).get("column_count")

    current_columns = current.get(
        "metadata",
        {},
    ).get("column_count")

    if (
        previous_columns is None
        or current_columns is None
    ):
        return True

    return (
        previous_columns
        == current_columns
    )


def _has_continuation_signal(
    previous,
    current,
):
    previous_metadata = previous.get(
        "metadata",
        {},
    )

    current_metadata = current.get(
        "metadata",
        {},
    )

    if previous_metadata.get(
        "table_continuation"
    ):
        return True

    if current_metadata.get(
        "table_continuation"
    ):
        return True

    if current_metadata.get(
        "continuation_header"
    ):
        return True

    previous_height = previous.get("page_height")
    current_height = current.get("page_height")
    previous_bbox = previous.get("bbox") or [0, 0, 0, 0]
    current_bbox = current.get("bbox") or [0, 0, 0, 0]
    if previous_height and current_height:
        ends_low = previous_bbox[3] >= float(previous_height) * 0.75
        starts_high = current_bbox[1] <= float(current_height) * 0.25
        if ends_low and starts_high:
            return True

    return False


def _can_merge(
    previous,
    current,
):
    reasons = []

    if previous.get("type") != "table":
        return False, 0.0, reasons

    if current.get("type") != "table":
        return False, 0.0, reasons

    if not _same_page_sequence(
        previous,
        current,
    ):
        return False, 0.0, reasons

    reasons.append(
        "adjacent pages"
    )

    if not _similar_width(
        previous,
        current,
    ):
        return False, 0.0, reasons

    reasons.append(
        "similar table width"
    )

    if not _same_column_count(
        previous,
        current,
    ):
        return False, 0.0, reasons

    reasons.append(
        "compatible column count"
    )

    previous_bbox = previous.get(
        "bbox",
        [0, 0, 0, 0],
    )

    current_bbox = current.get(
        "bbox",
        [0, 0, 0, 0],
    )

    overlap = _horizontal_overlap_ratio(
        previous_bbox,
        current_bbox,
    )

    if overlap < 0.70:
        return False, 0.0, reasons

    reasons.append(
        "aligned horizontal position"
    )

    continuation = _has_continuation_signal(
        previous,
        current,
    )

    if not continuation:
        return False, 0.0, reasons

    reasons.append(
        "continuation signal"
    )

    confidence = 0.85
    confidence += overlap * 0.10

    confidence = min(
        1.0,
        confidence,
    )

    return (
        True,
        confidence,
        reasons,
    )


def _merge_table_dict(previous, current):
    merged = dict(previous)
    merged["rows"] = list(previous.get("rows") or []) + list(current.get("rows") or [])
    if "records" in previous or "records" in current:
        merged["records"] = list(previous.get("records") or []) + list(current.get("records") or [])
    return merged


def _merge_content(
    previous,
    current,
):
    if previous is None:
        return current

    if current is None:
        return previous

    if (
        isinstance(previous, dict)
        and isinstance(current, dict)
        and "rows" in previous
        and "rows" in current
    ):
        return _merge_table_dict(previous, current)

    if (
        isinstance(previous, list)
        and isinstance(current, list)
    ):
        return previous + current

    if (
        isinstance(previous, str)
        and isinstance(current, str)
    ):
        if not previous:
            return current

        if not current:
            return previous

        return (
            previous
            + "\n"
            + current
        )

    return [
        previous,
        current,
    ]


def _get_page_start(block):
    value = block.get(
        "page_start"
    )

    if value is not None:
        return int(value)

    value = block.get(
        "page_number"
    )

    if value is not None:
        return int(value)

    return None


def _get_page_end(block):
    value = block.get(
        "page_end"
    )

    if value is not None:
        return int(value)

    value = block.get(
        "page_number"
    )

    if value is not None:
        return int(value)

    return None


def _get_bbox(block):
    bbox = block.get(
        "bbox"
    )

    if (
        not bbox
        or len(bbox) != 4
    ):
        return None

    return bbox


def _build_bbox_by_page(
    previous,
    current,
):
    result = {}

    previous_existing = previous.get(
        "bbox_by_page",
        {},
    )

    current_existing = current.get(
        "bbox_by_page",
        {},
    )

    if isinstance(
        previous_existing,
        dict,
    ):
        result.update(
            previous_existing
        )

    if isinstance(
        current_existing,
        dict,
    ):
        result.update(
            current_existing
        )

    previous_page = _get_page_end(
        previous
    )

    previous_bbox = _get_bbox(
        previous
    )

    if (
        previous_page is not None
        and previous_bbox is not None
    ):
        result.setdefault(
            str(previous_page),
            previous_bbox,
        )

    current_page = _get_page_start(
        current
    )

    current_bbox = _get_bbox(
        current
    )

    if (
        current_page is not None
        and current_bbox is not None
    ):
        result.setdefault(
            str(current_page),
            current_bbox,
        )

    return result


def merge_table_pair(
    previous,
    current,
):
    (
        can_merge,
        confidence,
        reasons,
    ) = _can_merge(
        previous,
        current,
    )

    if not can_merge:
        return (
            None,
            confidence,
            reasons,
        )

    merged = dict(
        previous
    )

    merged["content"] = _merge_content(
        previous.get("content"),
        current.get("content"),
    )

    page_start = _get_page_start(
        previous
    )

    page_end = _get_page_end(
        current
    )

    if page_start is not None:
        merged["page_start"] = page_start

    if page_end is not None:
        merged["page_end"] = page_end

    if (
        page_start is not None
        and "page_number" in merged
    ):
        merged["page_number"] = page_start

    merged["bbox_by_page"] = (
        _build_bbox_by_page(
            previous,
            current,
        )
    )

    metadata = dict(
        previous.get(
            "metadata",
            {},
        )
    )

    metadata["merged_table"] = True
    metadata["merge_confidence"] = confidence

    previous_reasons = metadata.get(
        "merge_reasons",
        [],
    )

    metadata["merge_reasons"] = (
        list(previous_reasons)
        + reasons
    )

    metadata["table_continuation"] = True

    merged["metadata"] = metadata

    return (
        merged,
        confidence,
        reasons,
    )


def merge_cross_page_tables(
    regions,
):
    if not regions:
        return []

    ordered = sorted(
        regions,
        key=lambda region: (
            region.get(
                "page_start",
                region.get(
                    "page_number",
                    0,
                ),
            ),
            region.get(
                "reading_order",
                float("inf"),
            ),
        ),
    )

    result = []

    current_table = None

    for region in ordered:

        if current_table is None:
            current_table = region
            continue

        (
            merged,
            confidence,
            reasons,
        ) = merge_table_pair(
            current_table,
            region,
        )

        if merged is not None:
            current_table = merged
            continue

        result.append(
            current_table
        )

        current_table = region

    if current_table is not None:
        result.append(
            current_table
        )

    return result