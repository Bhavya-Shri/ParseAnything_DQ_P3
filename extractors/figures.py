"""A figure that is not a chart. The block keeps the region and asks for review.

P3 does not invent what the picture shows. P4 can verify it later.
"""

from extractors.base import Extractor
from extractors.utils import make_block, region_field


class FigureExtractor(Extractor):
    name = "figure"

    def can_handle(self, region) -> bool:
        return region_field(region, "route") == "figure"

    def extract(self, region, context) -> list:
        context = context or {}
        text = str(region_field(region, "text", "") or "").strip() or None
        bbox = region_field(region, "bbox") or [0.0, 0.0, 0.0, 0.0]
        page = int(region_field(region, "page", 1) or 1)
        return [
            make_block(
                extractor=self.name,
                bbox=list(bbox),
                page_start=page if page >= 1 else 1,
                extraction=0.4,
                block_type="figure",
                content={"text": text},
                region_id=str(region_field(region, "id", "region")),
                status="needs_review",
                flags=["figure_not_read"],
                source_file=str(context.get("file_path") or ""),
                history=[{"engine": self.name, "confidence": 0.4, "note": "figure kept for review"}],
            )
        ]
