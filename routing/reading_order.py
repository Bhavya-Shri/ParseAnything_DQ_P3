from .route_models import Region
from .column_detector import LayoutSection


def _region_y(region: Region) -> float:
    return region.bbox[1]


def _sort_within_column(
    regions: list[Region],
) -> list[Region]:
    return sorted(
        regions,
        key=lambda region: (
            region.bbox[1],
            region.bbox[0],
        ),
    )


def _group_by_column(
    regions: list[Region],
) -> dict[int, list[Region]]:
    groups: dict[int, list[Region]] = {}

    for region in regions:
        column_id = region.column_id

        if column_id is None:
            column_id = -1

        if column_id not in groups:
            groups[column_id] = []

        groups[column_id].append(region)

    for column_id in groups:
        groups[column_id] = _sort_within_column(
            groups[column_id]
        )

    return groups


def _order_column_regions(
    regions: list[Region],
) -> list[Region]:
    groups = _group_by_column(regions)

    ordered = []

    for column_id in sorted(groups):
        ordered.extend(groups[column_id])

    return ordered


def _sort_full_width_regions(
    regions: list[Region],
) -> list[Region]:
    return sorted(
        regions,
        key=lambda region: (
            region.bbox[1],
            region.bbox[0],
        ),
    )


def _order_section(
    section: LayoutSection,
) -> list[Region]:

    if not section.regions:
        return []

    full_width = [
        region
        for region in section.regions
        if region.is_full_width
    ]

    column_regions = [
        region
        for region in section.regions
        if not region.is_full_width
    ]

    if not column_regions:
        return _sort_full_width_regions(
            full_width
        )

    column_order = _order_column_regions(
        column_regions
    )

    if not full_width:
        return column_order

    all_regions = full_width + column_order

    return sorted(
        all_regions,
        key=lambda region: (
            region.bbox[1],
            0 if region.is_full_width else 1,
            region.bbox[0],
        ),
    )


def _keep_heading_with_content(
    ordered: list[Region],
) -> list[Region]:

    if len(ordered) < 2:
        return ordered

    result = []
    used = set()

    for index, region in enumerate(ordered):

        if index in used:
            continue

        result.append(region)
        used.add(index)

        if region.region_type != "heading":
            continue

        best_index = None
        best_gap = float("inf")

        for next_index in range(
            index + 1,
            len(ordered),
        ):

            if next_index in used:
                continue

            candidate = ordered[next_index]

            if candidate.region_type == "heading":
                continue

            if candidate.bbox[1] < region.bbox[3]:
                continue

            if (
                region.column_id is not None
                and candidate.column_id is not None
                and region.column_id != candidate.column_id
            ):
                continue

            gap = candidate.bbox[1] - region.bbox[3]

            if gap < 0:
                continue

            if gap > max(
                60.0,
                (region.bbox[3] - region.bbox[1]) * 4.0,
            ):
                continue

            if gap < best_gap:
                best_gap = gap
                best_index = next_index

        if best_index is not None:
            result.append(
                ordered[best_index]
            )
            used.add(best_index)

    for index, region in enumerate(ordered):

        if index not in used:
            result.append(region)

    return result


def _mark_ambiguous_regions(
    ordered: list[Region],
) -> None:

    for region in ordered:
        region.metadata.pop(
            "order_ambiguous",
            None,
        )

    for region in ordered:

        if region.column_id is None:

            if not region.is_full_width:
                region.metadata[
                    "order_ambiguous"
                ] = True


def _calculate_order_confidence(
    region: Region,
    previous: Region | None,
    section_confidence: float,
) -> float:

    confidence = 0.95

    if previous is None:
        return confidence

    if region.column_id is None:

        if not region.is_full_width:
            confidence -= 0.20

    if previous.column_id is None:

        if not previous.is_full_width:
            confidence -= 0.10

    if region.metadata.get(
        "order_ambiguous",
        False,
    ):
        confidence -= 0.30

    if (
        region.column_id is not None
        and previous.column_id is not None
        and region.column_id != previous.column_id
    ):
        confidence -= 0.01

    if section_confidence < 0.35:
        confidence -= 0.10

    elif section_confidence < 0.50:
        confidence -= 0.05

    return max(
        0.0,
        min(1.0, confidence),
    )


def reconstruct_reading_order(
    regions: list[Region],
    sections: list[LayoutSection] | None = None,
) -> list[Region]:

    if not regions:
        return []

    if sections is None:

        sections = [
            LayoutSection(
                section_id=0,
                y_start=min(
                    _region_y(region)
                    for region in regions
                ),
                y_end=max(
                    region.bbox[3]
                    for region in regions
                ),
                regions=regions,
                columns=[],
                confidence=0.50,
            )
        ]

    ordered = []

    sections = sorted(
        sections,
        key=lambda section: (
            section.y_start,
            section.section_id,
        ),
    )

    section_confidence = {}

    for section in sections:

        section_order = _order_section(
            section
        )

        section_order = _keep_heading_with_content(
            section_order
        )

        ordered.extend(
            section_order
        )

        for region in section_order:

            section_confidence[
                region.region_id
            ] = section.confidence

    _mark_ambiguous_regions(
        ordered
    )

    for index, region in enumerate(ordered):

        previous = None

        if index > 0:
            previous = ordered[index - 1]

        region.reading_order = index

        confidence = _calculate_order_confidence(
            region,
            previous,
            section_confidence.get(
                region.region_id,
                0.50,
            ),
        )

        region.metadata[
            "order_confidence"
        ] = confidence

    return ordered