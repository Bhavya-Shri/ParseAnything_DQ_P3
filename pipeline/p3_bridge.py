"""Turn P2 regions into P3 calls, then hand the blocks back to P2 assembly."""

import time

from assembly.assembler import DocumentAssembler
from pipeline.schema import Block, DocumentResult
from routing.layout_checks import valid_bbox

_DIRECT_ROUTES = {
    "native": "native_text",
    "native_text": "native_text",
    "ocr": "ocr",
    "docling_table": "docling_table",
    "paddle_table": "paddle_table",
    "equation": "formula",
    "formula": "formula",
    "chart": "chart",
    "office": "office",
    "skip": "skip",
    "figure": "figure",
}


def document_from_office(file_path, preflight, doc_id, start_time) -> DocumentResult:
    from extractors import extract_document

    blocks = extract_document(file_path)
    errors = _errors(blocks, preflight["trace_id"])
    assembled, document_map = _assemble(
        blocks,
        order_confidence=1.0,
        layout={"source": "office", "bbox_valid": None, "warnings": []},
    )
    trusted = _trust(assembled)
    return _result(
        preflight,
        doc_id,
        start_time,
        trusted,
        errors,
        page_count=_page_count(trusted),
        page_sizes={},
        metrics={"office": True},
        document_map=document_map,
        trust_report=_trust_summary(trusted),
    )


def document_from_regions(
    file_path,
    preflight,
    doc_id,
    start_time,
    regions,
    page_count,
    page_sizes,
    route_count,
) -> DocumentResult:
    from extractors import extract

    raw = []
    trace_id = preflight["trace_id"]
    for region in regions:
        payload = _region_dict(region)
        if payload["route"] == "skip":
            continue
        context = {"file_path": file_path, "format": preflight["format"]}
        if payload.get("page_size"):
            context["page_size"] = payload.pop("page_size")
        produced = extract(payload, context)
        base = getattr(region, "reading_order", None)
        metadata = getattr(region, "metadata", {}) or {}
        order_confidence = metadata.get("order_confidence")
        for index, block in enumerate(produced):
            data = block.model_dump()
            data["page_number"] = data.get("page_start")
            data["reading_order"] = None if base is None else int(base) * 100 + index
            if order_confidence is not None:
                data["order_confidence"] = max(0.0, min(1.0, float(order_confidence)))
            size = page_sizes.get(str(region.page_number)) or {}
            if size.get("height"):
                data["page_height"] = float(size["height"])
            links = dict(data.get("links") or {})
            links["layout"] = _layout_signals(region)
            data["links"] = links
            raw.append(data)
    raw = _drop_repeated_lines(raw)
    if not raw and preflight["format"] in {"png", "jpg", "jpeg"}:
        raw_errors = [
            {
                "status": "failed",
                "error_code": "INTERNAL_ERROR",
                "message": "Image routing is not wired. P2 regions are built from PDF pages.",
                "recoverable": False,
                "stage": "routing",
                "page": None,
                "trace_id": trace_id,
            }
        ]
        return _result(
            preflight,
            doc_id,
            start_time,
            [],
            raw_errors,
            page_count=0,
            page_sizes=page_sizes,
            metrics={"p2_region_count": len(regions), "p2_route_count": route_count},
            document_map=[],
        )
    assembled, document_map = _assemble_raw(raw)
    errors = _errors(assembled, trace_id)
    trusted = _trust(assembled)
    return _result(
        preflight,
        doc_id,
        start_time,
        trusted,
        errors,
        page_count=page_count,
        page_sizes=page_sizes,
        metrics={"p2_region_count": len(regions), "p2_route_count": route_count},
        document_map=document_map,
        trust_report=_trust_summary(trusted),
    )


def _region_dict(region) -> dict:
    metadata = getattr(region, "metadata", {}) or {}
    scanned = bool(metadata.get("is_scanned"))
    route_name = metadata.get("route") or "native"
    payload = {
        "id": region.region_id,
        "type": region.region_type,
        "page": int(region.page_number),
        "bbox": [float(value) for value in region.bbox],
        "route": _map_route(route_name, scanned),
        "is_scanned": scanned,
    }
    width = metadata.get("page_width")
    height = metadata.get("page_height")
    if width and height:
        payload["page_size"] = {"width": float(width), "height": float(height)}
    return payload


def _map_route(route: str, scanned: bool) -> str:
    if route == "table":
        return "paddle_table" if scanned else "docling_table"
    if route == "vlm":
        return "ocr" if scanned else "native_text"
    return _DIRECT_ROUTES.get(route, route)


def _layout_signals(region) -> dict:
    """Copy the layout checks P2 already ran onto the block."""
    metadata = getattr(region, "metadata", {}) or {}
    bbox = [float(value) for value in region.bbox]
    warnings = []
    if not valid_bbox(bbox):
        warnings.append("invalid bounding box")
    else:
        if bbox[0] < 0 or bbox[1] < 0:
            warnings.append("bbox starts outside page")
        width = metadata.get("page_width")
        height = metadata.get("page_height")
        if width and height and (bbox[2] > float(width) or bbox[3] > float(height)):
            warnings.append("bbox extends outside page")
    route_confidence = metadata.get("route_confidence")
    return {
        "source": "region",
        "bbox_valid": not warnings,
        "warnings": warnings,
        "is_header": bool(getattr(region, "is_header", False)),
        "is_footer": bool(getattr(region, "is_footer", False)),
        "is_full_width": bool(getattr(region, "is_full_width", False)),
        "column_id": getattr(region, "column_id", None),
        "is_scanned": bool(metadata.get("is_scanned")),
        "route": metadata.get("route"),
        "route_confidence": None if route_confidence is None else float(route_confidence),
        "route_reason": metadata.get("route_reason"),
        "order_ambiguous": bool(metadata.get("order_ambiguous")),
    }


def _drop_repeated_lines(raw: list[dict]) -> list[dict]:
    """Drop a later block that repeats the same line on the same page."""
    kept = []
    for block in raw:
        content = block.get("content")
        text = ""
        if isinstance(content, dict):
            text = " ".join(str(content.get("text") or "").split())
        bbox = block.get("bbox") or [0, 0, 0, 0]
        if text and any(
            other.get("page_start") == block.get("page_start")
            and " ".join(str((other.get("content") or {}).get("text") or "").split()) == text
            and _boxes_overlap(bbox, other.get("bbox") or [0, 0, 0, 0])
            for other in kept
            if isinstance(other.get("content"), dict)
        ):
            continue
        kept.append(block)
    return kept


def _boxes_overlap(left: list, right: list) -> bool:
    if len(left) != 4 or len(right) != 4:
        return False
    return min(left[2], right[2]) - max(left[0], right[0]) > 1 and min(left[3], right[3]) - max(left[1], right[1]) > 1


def _stamp_assembly(item: dict) -> dict:
    """Keep the table-merge result. Block has no metadata field, so it goes on links."""
    metadata = item.pop("metadata", None) or {}
    links = dict(item.get("links") or {})
    reasons = metadata.get("merge_reasons") or []
    links["table_merge"] = {
        "merged": bool(metadata.get("merged_table")),
        "merge_confidence": metadata.get("merge_confidence"),
        "merge_reasons": list(reasons),
        "table_continuation": bool(metadata.get("table_continuation")),
    }
    item["links"] = links
    item.pop("page_number", None)
    item.pop("page_height", None)
    if item.get("reading_order") is None:
        item["reading_order"] = 0
    return item


def _assemble(blocks, *, order_confidence=None, layout=None) -> tuple[list[Block], list]:
    raw = []
    for block in blocks:
        data = block.model_dump()
        data["page_number"] = data.get("page_start")
        data["reading_order"] = None
        if order_confidence is not None:
            data["order_confidence"] = float(order_confidence)
        if layout is not None:
            links = dict(data.get("links") or {})
            links["layout"] = dict(layout)
            data["links"] = links
        raw.append(data)
    return _assemble_raw(raw)


def _assemble_raw(raw: list[dict]) -> tuple[list[Block], list]:
    if not raw:
        return [], []
    result = DocumentAssembler().assemble(raw)
    blocks = []
    for item in result.blocks:
        blocks.append(Block.model_validate(_stamp_assembly(item)))
    document_map = result.metadata.get("document_map") or {}
    if isinstance(document_map, dict):
        document_map = [document_map]
    return blocks, list(document_map)


def _errors(blocks, trace_id: str) -> list[dict]:
    errors = []
    for block in blocks:
        if block.status != "failed":
            continue
        history = block.history[0] if block.history else {}
        errors.append(
            {
                "status": "failed",
                "error_code": history.get("error_code") or "INTERNAL_ERROR",
                "message": history.get("note") or "Extraction failed",
                "recoverable": True,
                "stage": "extraction",
                "page": block.page_start,
                "trace_id": trace_id,
            }
        )
    return errors


def _page_count(blocks) -> int:
    pages = [block.page_start for block in blocks if block.page_start]
    return max(pages) if pages else 0


def _trust(blocks):
    from validation import apply_trust

    return apply_trust(blocks)


def _trust_summary(blocks) -> dict:
    from validation import trust_summary

    return trust_summary(blocks)


def _result(
    preflight,
    doc_id,
    start_time,
    blocks,
    errors,
    page_count,
    page_sizes,
    metrics,
    document_map,
    trust_report=None,
) -> DocumentResult:
    if blocks and all(block.status == "failed" for block in blocks):
        status = "failed"
    elif errors:
        status = "partial"
    else:
        status = "complete"
    elapsed = time.time() - start_time
    metrics = dict(metrics)
    metrics["total_time_seconds"] = round(elapsed, 2)
    metrics["ready_for"] = "p4"
    return DocumentResult(
        document_id=doc_id,
        filename=preflight["filename"],
        format=preflight["format"],
        page_count=page_count,
        page_sizes=page_sizes,
        status=status,
        blocks=blocks,
        document_map=document_map,
        errors=errors,
        trust_report=trust_report or {},
        metrics=metrics,
    )
