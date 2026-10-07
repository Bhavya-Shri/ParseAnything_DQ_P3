from typing import Any


def _block_key(
    block: dict[str, Any],
) -> tuple:

    page = block.get(
        "page_number",
        block.get("page_start", 0),
    )

    reading_order = block.get(
        "reading_order"
    )

    if reading_order is None:
        reading_order = float("inf")

    bbox = block.get(
        "bbox",
        [0.0, 0.0, 0.0, 0.0],
    )

    return (
        page,
        reading_order,
        bbox[1],
        bbox[0],
    )


def sort_blocks(
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    return sorted(
        blocks,
        key=_block_key,
    )


def order_regions(
    regions: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    return sort_blocks(
        regions
    )


def assign_reading_order(
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    ordered = sort_blocks(
        blocks
    )

    has_existing_order = False

    for block in ordered:

        if block.get(
            "reading_order"
        ) is not None:

            has_existing_order = True
            break

    if has_existing_order:

        used_orders = set()

        for block in ordered:

            order = block.get(
                "reading_order"
            )

            if order is not None:

                used_orders.add(
                    order
                )

        next_order = 0

        for block in ordered:

            if block.get(
                "reading_order"
            ) is not None:

                continue

            while next_order in used_orders:
                next_order += 1

            block["reading_order"] = next_order

            used_orders.add(
                next_order
            )

            next_order += 1

        return sort_blocks(
            ordered
        )

    for index, block in enumerate(
        ordered
    ):

        block["reading_order"] = index

    return ordered


def assign_missing_order(
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    ordered = sort_blocks(
        blocks
    )

    for index, block in enumerate(
        ordered
    ):

        if block.get(
            "reading_order"
        ) is None:

            block["reading_order"] = index

    return ordered


def group_by_page(
    blocks: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:

    pages: dict[
        int,
        list[dict[str, Any]]
    ] = {}

    for block in sort_blocks(
        blocks
    ):

        page = int(
            block.get(
                "page_number",
                block.get(
                    "page_start",
                    0,
                ),
            )
        )

        if page not in pages:

            pages[page] = []

        pages[page].append(
            block
        )

    return pages


def flatten_page_groups(
    pages: dict[
        int,
        list[dict[str, Any]]
    ],
) -> list[dict[str, Any]]:

    flattened = []

    for page in sorted(
        pages
    ):

        flattened.extend(
            sort_blocks(
                pages[page]
            )
        )

    return flattened


def validate_reading_order(
    blocks: list[dict[str, Any]],
) -> list[str]:

    errors = []

    pages = group_by_page(
        blocks
    )

    for page, page_blocks in pages.items():

        previous = None

        for block in page_blocks:

            current = block.get(
                "reading_order"
            )

            if current is None:
                continue

            if (
                previous is not None
                and current < previous
            ):

                errors.append(
                    f"{block.get('region_id', block.get('id'))}: "
                    f"reading order is not monotonic on page {page}"
                )

            previous = current

    return errors