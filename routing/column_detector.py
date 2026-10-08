from dataclasses import dataclass, field

from .layout_checks import bbox_width, is_full_width
from .route_models import Column, PageProfile, Region


@dataclass
class ColumnDetection:
    columns: list[Column] = field(default_factory=list)
    confidence: float = 0.0
    ambiguous: bool = False
    boundaries: list[float] = field(default_factory=list)
    method: str = "geometry"


@dataclass
class LayoutSection:
    section_id: int
    y_start: float
    y_end: float
    regions: list[Region] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)
    confidence: float = 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _usable_regions(
    regions: list[Region],
    page_width: float
) -> list[Region]:

    result = []

    for region in regions:

        if not region.bbox:
            continue

        if region.is_full_width:
            continue

        if is_full_width(
            region.bbox,
            page_width
        ):
            continue

        if bbox_width(region.bbox) <= 0:
            continue

        if bbox_width(region.bbox) > page_width * 0.55:
            continue

        result.append(region)

    return result


def _build_x_occupancy(
    regions: list[Region],
    page_width: float,
    bins: int = 100
) -> list[float]:

    occupancy = [0.0] * bins

    if page_width <= 0:
        return occupancy

    for region in regions:

        x1 = region.bbox[0]
        x2 = region.bbox[2]

        width = x2 - x1

        if width <= 0:
            continue

        start = int(
            max(
                0,
                min(
                    bins - 1,
                    (x1 / page_width) * bins
                )
            )
        )

        end = int(
            max(
                0,
                min(
                    bins - 1,
                    (x2 / page_width) * bins
                )
            )
        )

        if end < start:
            continue

        for index in range(start, end + 1):
            occupancy[index] += 1.0

    return occupancy


def _build_column_occupancy(
    regions: list[Region],
    page_width: float,
    bins: int = 200
) -> list[float]:

    occupancy = [0.0] * bins

    if page_width <= 0:
        return occupancy

    page_area = page_width

    for region in regions:

        x1 = region.bbox[0]
        x2 = region.bbox[2]

        width = x2 - x1

        if width <= 0:
            continue

        normalized_width = width / page_area

        if normalized_width < 0.10:
            continue

        start = int(
            max(
                0,
                min(
                    bins - 1,
                    (x1 / page_width) * bins
                )
            )
        )

        end = int(
            max(
                0,
                min(
                    bins - 1,
                    (x2 / page_width) * bins
                )
            )
        )

        if end < start:
            continue

        for index in range(start, end + 1):
            occupancy[index] += 1.0

    return occupancy


def _smooth(
    values: list[float],
    radius: int = 2
) -> list[float]:

    if not values:
        return []

    result = []

    for index in range(len(values)):

        start = max(
            0,
            index - radius
        )

        end = min(
            len(values),
            index + radius + 1
        )

        window = values[start:end]

        result.append(
            sum(window) / len(window)
        )

    return result


def _find_valleys(
    occupancy: list[float],
    minimum_width: int = 3
) -> list[int]:

    if len(occupancy) < minimum_width * 2 + 1:
        return []

    smooth = _smooth(occupancy,radius=1)

    maximum = max(smooth)

    if maximum <= 0:
        return []

    threshold = maximum * 0.20

    valleys = []

    index = 0

    while index < len(smooth):

        if smooth[index] > threshold:
            index += 1
            continue

        start = index

        while (
            index < len(smooth)
            and smooth[index] <= threshold
        ):
            index += 1

        end = index - 1

        if end - start + 1 >= minimum_width:
            valleys.append(
                (start + end) // 2
            )

    return valleys


def _valley_strength(
    occupancy: list[float],
    valley: int
) -> float:

    if not occupancy:
        return 0.0

    maximum = max(occupancy)

    if maximum <= 0:
        return 0.0

    left_values = occupancy[
        max(0, valley - 5): valley + 1
    ]

    right_values = occupancy[
        valley: min(
            len(occupancy),
            valley + 6
        )
    ]

    left = max(
        left_values or [0.0]
    )

    right = max(
        right_values or [0.0]
    )

    surrounding = max(
        left,
        right
    )

    current = occupancy[valley]

    if surrounding <= 0:
        return 0.0

    return _clamp(
        1.0 - current / surrounding
    )


def _candidate_boundaries(
    regions: list[Region],
    page_width: float
) -> list[tuple[float, float]]:

    occupancy = _build_column_occupancy(
        regions,
        page_width
    )

    valleys = _find_valleys(
        occupancy
    )

    candidates = []

    for valley in valleys:

        x = (
            valley
            / len(occupancy)
            * page_width
        )

        strength = _valley_strength(
            occupancy,
            valley
        )

        if (
            0.15 * page_width
            < x
            < 0.85 * page_width
        ):
            candidates.append(
                (x, strength)
            )

    return candidates


def _select_boundaries(
    candidates: list[tuple[float, float]],
    page_width: float
) -> list[float]:

    if not candidates:
        return []

    candidates = sorted(
        candidates,
        key=lambda item: item[0]
    )

    selected = []

    minimum_gap = page_width * 0.12

    for x, strength in candidates:

        if not selected:
            selected.append(x)
            continue

        if (
            x - selected[-1]
            < minimum_gap
        ):

            previous_x = selected[-1]

            previous_strength = 0.0

            for candidate_x, candidate_strength in candidates:

                if (
                    candidate_x
                    == previous_x
                ):
                    previous_strength = (
                        candidate_strength
                    )
                    break

            if strength > previous_strength:
                selected[-1] = x

            continue

        selected.append(x)

    return selected


def _create_columns(
    boundaries: list[float],
    page_width: float
) -> list[Column]:

    edges = (
        [0.0]
        + boundaries
        + [page_width]
    )

    columns = []

    for index in range(
        len(edges) - 1
    ):

        start = edges[index]
        end = edges[index + 1]

        if end <= start:
            continue

        columns.append(
            Column(
                column_id=index,
                x_start=start,
                x_end=end
            )
        )

    return columns


def _assign_regions(
    regions: list[Region],
    columns: list[Column]
) -> None:

    for region in regions:

        best_column = None
        best_overlap = 0.0

        for column in columns:

            overlap_start = max(
                region.bbox[0],
                column.x_start
            )

            overlap_end = min(
                region.bbox[2],
                column.x_end
            )

            overlap = max(
                0.0,
                overlap_end - overlap_start
            )

            width = bbox_width(
                region.bbox
            )

            if width <= 0:
                continue

            ratio = (
                overlap / width
            )

            if ratio > best_overlap:

                best_overlap = ratio
                best_column = column

        if best_column is not None:

            region.column_id = (
                best_column.column_id
            )

            best_column.region_ids.append(
                region.region_id
            )


def _column_balance(
    regions: list[Region],
    columns: list[Column]
) -> float:

    if len(columns) <= 1:
        return 1.0

    counts = []

    for column in columns:

        count = sum(
            1
            for region in regions
            if region.column_id
            == column.column_id
        )

        counts.append(count)

    if not counts:
        return 0.0

    if max(counts) == 0:
        return 0.0

    return (
        min(counts)
        / max(counts)
    )


def detect_columns(
    regions: list[Region],
    profile: PageProfile
) -> ColumnDetection:

    usable = _usable_regions(
        regions,
        profile.width
    )

    if len(usable) < 4:

        columns = _create_columns(
            [],
            profile.width
        )

        _assign_regions(
            usable,
            columns
        )

        return ColumnDetection(
            columns=columns,
            confidence=0.45,
            ambiguous=True,
            boundaries=[],
            method="insufficient_regions"
        )

    candidates = _candidate_boundaries(
        usable,
        profile.width
    )

    boundaries = _select_boundaries(
        candidates,
        profile.width
    )

    columns = _create_columns(
        boundaries,
        profile.width
    )

    _assign_regions(
        usable,
        columns
    )

    balance = _column_balance(
        usable,
        columns
    )

    boundary_strength = 0.0

    if candidates:

        strengths = []

        for boundary in boundaries:

            closest = min(
                candidates,
                key=lambda item:
                abs(item[0] - boundary)
            )

            strengths.append(
                closest[1]
            )

        if strengths:

            boundary_strength = (
                sum(strengths)
                / len(strengths)
            )

    confidence = (
        0.35 * boundary_strength
        + 0.35 * balance
        + 0.30 * min(
            1.0,
            len(usable) / 20.0
        )
    )

    ambiguous = False

    if len(columns) > 1:

        if balance < 0.25:
            ambiguous = True

        if boundary_strength < 0.35:
            ambiguous = True

    if confidence < 0.50:
        ambiguous = True

    return ColumnDetection(
        columns=columns,
        confidence=_clamp(confidence),
        ambiguous=ambiguous,
        boundaries=boundaries,
        method="x_axis_occupancy"
    )


def assign_columns(
    regions: list[Region],
    profile: PageProfile
) -> ColumnDetection:

    return detect_columns(
        regions,
        profile
    )


def detect_layout_sections(
    regions: list[Region],
    profile: PageProfile
) -> list[LayoutSection]:

    if not regions:
        return []

    ordered = sorted(
        regions,
        key=lambda region: (
            region.bbox[1],
            region.bbox[3]
        )
    )

    sections = []

    current_regions = []

    section_id = 0

    section_start = (
        ordered[0].bbox[1]
    )

    for region in ordered:

        if region.is_full_width:

            if current_regions:

                section_end = max(
                    item.bbox[3]
                    for item in current_regions
                )

                detection = detect_columns(
                    current_regions,
                    profile
                )

                sections.append(
                    LayoutSection(
                        section_id=section_id,
                        y_start=section_start,
                        y_end=section_end,
                        regions=current_regions,
                        columns=detection.columns,
                        confidence=detection.confidence
                    )
                )

                section_id += 1

                current_regions = []

            sections.append(
                LayoutSection(
                    section_id=section_id,
                    y_start=region.bbox[1],
                    y_end=region.bbox[3],
                    regions=[region],
                    columns=[],
                    confidence=region.confidence
                )
            )

            section_id += 1

            section_start = region.bbox[3]

        else:

            current_regions.append(
                region
            )

    if current_regions:

        section_end = max(
            item.bbox[3]
            for item in current_regions
        )

        detection = detect_columns(
            current_regions,
            profile
        )

        sections.append(
            LayoutSection(
                section_id=section_id,
                y_start=section_start,
                y_end=section_end,
                regions=current_regions,
                columns=detection.columns,
                confidence=detection.confidence
            )
        )

    return sections