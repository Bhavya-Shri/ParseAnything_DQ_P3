from typing import Any

from routing.route_models import (
    AssemblyResult,
    PageProfile,
    Region,
)

from routing.reading_order import (
    reconstruct_reading_order,
)

from routing.layout_checks import (
    validate_regions,
)

from assembly.normalize import (
    normalize_blocks,
)

from assembly.block_order import (
    assign_reading_order,
)

from assembly.table_merge import (
    merge_cross_page_tables,
)

from assembly.document_map import (
    build_document_map,
)


class DocumentAssembler:

    def __init__(
        self,
        profiles: list[PageProfile] | None = None
    ):
        self.profiles = profiles or []

    def assemble(
        self,
        blocks: list[Any],
        page_count: int | None = None
    ) -> AssemblyResult:

        warnings = []

        blocks = normalize_blocks(blocks)

        blocks = merge_cross_page_tables(
            blocks
        )

        blocks = assign_reading_order(
            blocks
        )

        document_map = build_document_map(
            blocks
        )

        if page_count is None:
            page_count = document_map["page_count"]

        return AssemblyResult(
            blocks=blocks,
            page_count=page_count,
            block_count=len(blocks),
            warnings=warnings,
            metadata={
                "document_map": document_map
            }
        )

    def assemble_page(
        self,
        regions: list[Region],
        page_width: float,
        page_height: float
    ) -> list[Region]:

        warnings = validate_regions(
            regions,
            page_width,
            page_height
        )

        if warnings:
            for region in regions:
                if region.region_id in " ".join(warnings):
                    region.confidence *= 0.8

        ordered = reconstruct_reading_order(
            regions
        )

        return ordered