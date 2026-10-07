"""Turn P2 regions into P3 calls, then hand the blocks back to P2 assembly."""

import time

from assembly.assembler import DocumentAssembler
from pipeline.schema import Block, DocumentResult

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
    "figure": "skip",
}


def document_from_office(file_path, preflight, doc_id, start_time) -> DocumentResult:
    from extractors import extract_document

    blocks = extract_document(file_path)
    errors = _errors(blocks, preflight["trace_id"])
    assembled, document_map = _assemble(blocks)
    return _result(
        preflight,
        doc_id,
        start_time,
        assembled,
        errors,
        page_count=_page_count(assembled),
        page_sizes={},
        metrics={"office": True},
        document_map=document_map,
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
        for index, block in enumerate(produced):
            data = block.model_dump()
            data["page_number"] = data.get("page_start")
            data["reading_order"] = None if base is None else int(base) * 100 + index
            raw.append(data)
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
    return _result(
        preflight,
        doc_id,
        start_time,
        assembled,
        errors,
        page_count=page_count,
        page_sizes=page_sizes,
        metrics={"p2_region_count": len(regions), "p2_route_count": route_count},
        document_map=document_map,
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


def _assemble(blocks) -> tuple[list[Block], list]:
    raw = []
    for block in blocks:
        data = block.model_dump()
        data["page_number"] = data.get("page_start")
        data["reading_order"] = None
        raw.append(data)
    return _assemble_raw(raw)


def _assemble_raw(raw: list[dict]) -> tuple[list[Block], list]:
    if not raw:
        return [], []
    result = DocumentAssembler().assemble(raw)
    blocks = []
    for item in result.blocks:
        if item.get("reading_order") is None:
            item["reading_order"] = 0
        item.pop("page_number", None)
        blocks.append(Block.model_validate(item))
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
        metrics=metrics,
    )
