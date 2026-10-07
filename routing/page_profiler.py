import fitz

from .route_models import PageProfile


def _get_text_blocks(page) -> list:
    try:
        return page.get_text("blocks")
    except Exception:
        return []


def _has_native_text(blocks: list) -> bool:
    for block in blocks:
        if len(block) < 5:
            continue

        text = str(block[4]).strip()

        if text:
            return True

    return False


def _count_text_blocks(blocks: list) -> int:
    count = 0

    for block in blocks:
        if len(block) < 5:
            continue

        text = str(block[4]).strip()

        if text:
            count += 1

    return count


def _calculate_text_density(page, blocks: list) -> float:
    page_area = page.rect.width * page.rect.height

    if page_area <= 0:
        return 0.0

    text_area = 0.0

    for block in blocks:
        if len(block) < 5:
            continue

        x1, y1, x2, y2 = block[:4]
        text = str(block[4]).strip()

        if not text:
            continue

        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)

        text_area += width * height

    return min(1.0, text_area / page_area)


def _count_images(page) -> int:
    try:
        return len(page.get_images(full=True))
    except Exception:
        return 0


def _estimate_columns(blocks: list, page_width: float) -> tuple[int, float]:
    if not blocks or page_width <= 0:
        return 1, 0.0

    centers = []

    for block in blocks:
        if len(block) < 5:
            continue

        x1, _, x2, _ = block[:4]
        text = str(block[4]).strip()

        if not text:
            continue

        width = max(0.0, x2 - x1)

        if width <= 0:
            continue

        centers.append((x1 + x2) / 2.0)

    if len(centers) < 4:
        return 1, 0.35

    centers.sort()

    gaps = []

    for i in range(1, len(centers)):
        gap = centers[i] - centers[i - 1]
        gaps.append(gap)

    if not gaps:
        return 1, 0.35

    average_gap = sum(gaps) / len(gaps)

    large_gaps = []

    for gap in gaps:
        if gap > average_gap * 2.5:
            large_gaps.append(gap)

    if not large_gaps:
        return 1, 0.55

    column_count = min(4, len(large_gaps) + 1)

    largest_gap = max(large_gaps)

    confidence = min(
        0.95,
        0.55 + (largest_gap / page_width) * 0.5
    )

    return column_count, confidence


def _detect_complexity(
    text_block_count: int,
    image_count: int,
    text_density: float,
    estimated_columns: int
) -> str:

    score = 0

    if text_block_count > 30:
        score += 2
    elif text_block_count > 15:
        score += 1

    if image_count > 2:
        score += 2
    elif image_count > 0:
        score += 1

    if estimated_columns > 1:
        score += 2

    if text_density > 0.45:
        score += 1

    if score >= 5:
        return "high"

    if score >= 3:
        return "medium"

    return "low"


def profile_page(page) -> PageProfile:
    blocks = _get_text_blocks(page)

    width = float(page.rect.width)
    height = float(page.rect.height)

    has_native_text = _has_native_text(blocks)
    text_block_count = _count_text_blocks(blocks)
    image_count = _count_images(page)

    text_density = _calculate_text_density(page, blocks)

    is_scanned = (
        not has_native_text
        and image_count > 0
    )

    is_sparse = (
        text_block_count <= 3
        and text_density < 0.05
    )

    estimated_columns, column_confidence = _estimate_columns(
        blocks,
        width
    )

    complexity = _detect_complexity(
        text_block_count,
        image_count,
        text_density,
        estimated_columns
    )

    return PageProfile(
        page_number=page.number + 1,
        width=width,
        height=height,
        has_native_text=has_native_text,
        text_block_count=text_block_count,
        image_count=image_count,
        text_density=text_density,
        is_scanned=is_scanned,
        is_sparse=is_sparse,
        estimated_columns=estimated_columns,
        column_confidence=column_confidence,
        has_tables=False,
        has_figures=image_count > 0,
        has_formula_like_regions=False,
        complexity=complexity,
        metadata={
            "source": "pymupdf",
            "rotation": page.rotation,
        },
    )


def profile_document(path: str) -> list[PageProfile]:
    document = fitz.open(path)

    profiles = []

    try:
        for page in document:
            profiles.append(profile_page(page))
    finally:
        document.close()

    return profiles