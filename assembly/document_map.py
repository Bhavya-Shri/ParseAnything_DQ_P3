from typing import Any


def _page_number(
    region: dict[str, Any],
) -> int:
    return int(
        region.get(
            "page_number",
            0,
        )
    )


def _region_summary(
    region: dict[str, Any],
) -> dict[str, Any]:

    return {
        "region_id": region.get(
            "region_id"
        ),
        "type": region.get(
            "type"
        ),
        "reading_order": region.get(
            "reading_order"
        ),
        "order_confidence": region.get(
            "order_confidence",
            0.0,
        ),
        "bbox": region.get(
            "bbox"
        ),
        "column_id": region.get(
            "column_id"
        ),
        "is_full_width": region.get(
            "is_full_width",
            False,
        ),
        "is_header": region.get(
            "is_header",
            False,
        ),
        "is_footer": region.get(
            "is_footer",
            False,
        ),
    }


def build_page_map(
    regions: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:

    pages: dict[
        int,
        list[dict[str, Any]]
    ] = {}

    for region in regions:
        page = _page_number(
            region
        )

        if page not in pages:
            pages[page] = []

        pages[page].append(
            region
        )

    for page in pages:
        pages[page].sort(
            key=lambda region: (
                region.get(
                    "reading_order",
                    float("inf"),
                ),
                region.get(
                    "bbox",
                    [0, 0, 0, 0],
                )[1],
            )
        )

    return pages


def build_page_summary(
    page: int,
    regions: list[dict[str, Any]],
) -> dict[str, Any]:

    type_counts: dict[
        str,
        int
    ] = {}

    columns = set()

    full_width_count = 0
    header_count = 0
    footer_count = 0

    for region in regions:

        region_type = region.get(
            "type",
            "paragraph",
        )

        type_counts[region_type] = (
            type_counts.get(
                region_type,
                0,
            ) + 1
        )

        column_id = region.get(
            "column_id"
        )

        if column_id is not None:
            columns.add(
                column_id
            )

        if region.get(
            "is_full_width",
            False,
        ):
            full_width_count += 1

        if region.get(
            "is_header",
            False,
        ):
            header_count += 1

        if region.get(
            "is_footer",
            False,
        ):
            footer_count += 1

    return {
        "page_number": page,
        "region_count": len(regions),
        "type_counts": type_counts,
        "column_count": len(columns),
        "full_width_count": full_width_count,
        "header_count": header_count,
        "footer_count": footer_count,
    }


def build_document_map(
    regions: list[dict[str, Any]],
) -> dict[str, Any]:

    pages = build_page_map(
        regions
    )

    page_summaries = []

    page_regions = {}

    for page in sorted(pages):
        page_regions[page] = [
            _region_summary(region)
            for region in pages[page]
        ]

        page_summaries.append(
            build_page_summary(
                page,
                pages[page],
            )
        )

    return {
        "page_count": len(pages),
        "pages": page_regions,
        "page_summaries": page_summaries,
        "region_count": len(regions),
    }


def get_document_statistics(
    document_map: dict[str, Any],
) -> dict[str, Any]:

    type_counts: dict[
        str,
        int
    ] = {}

    total_columns = 0
    pages_with_tables = 0
    pages_with_figures = 0

    for summary in document_map.get(
        "page_summaries",
        [],
    ):

        total_columns += summary.get(
            "column_count",
            0,
        )

        counts = summary.get(
            "type_counts",
            {},
        )

        for region_type, count in counts.items():
            type_counts[region_type] = (
                type_counts.get(
                    region_type,
                    0,
                ) + count
            )

        if counts.get(
            "table",
            0,
        ) > 0:
            pages_with_tables += 1

        if (
            counts.get(
                "figure",
                0,
            )
            + counts.get(
                "chart",
                0,
            )
            > 0
        ):
            pages_with_figures += 1

    page_count = document_map.get(
        "page_count",
        0,
    )

    average_columns = 0.0

    if page_count > 0:
        average_columns = (
            total_columns / page_count
        )

    return {
        "page_count": page_count,
        "region_count": document_map.get(
            "region_count",
            0,
        ),
        "type_counts": type_counts,
        "average_columns": average_columns,
        "pages_with_tables": pages_with_tables,
        "pages_with_figures": pages_with_figures,
    }