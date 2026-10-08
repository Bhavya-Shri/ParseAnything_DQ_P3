"""Structure score from layout and content evidence already on the block.

Penalties are a heuristic. Change them in STRUCTURE_PENALTIES.
"""

from pipeline.schema import Block

STRUCTURE_PENALTIES = {
    "invalid_bbox": 0.25,
    "order_ambiguous": 0.20,
    "weak_route": 0.15,
    "layout_warning": 0.05,
    "empty_content": 0.40,
    "missing_rows": 0.40,
    "ragged_table": 0.20,
    "arith_mismatch": 0.25,
    "equation_unparsed": 0.35,
    "chart_disagreement": 0.30,
}


def _bbox_problem(bbox) -> str | None:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return "bbox_invalid"
    try:
        x1, y1, x2, y2 = (float(value) for value in bbox)
    except (TypeError, ValueError):
        return "bbox_invalid"
    if x2 < x1 or y2 < y1:
        return "bbox_invalid"
    return None


def _empty_content(content) -> bool:
    if content is None:
        return True
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, dict):
        if not content:
            return True
        text = content.get("text")
        if isinstance(text, str) and not text.strip() and "rows" not in content and "latex" not in content:
            return True
        rows = content.get("rows")
        if isinstance(rows, list) and len(rows) == 0 and "text" not in content:
            return True
    return False


def structural_flags(block: Block) -> list[str]:
    flags = []
    problem = _bbox_problem(block.bbox)
    if problem is not None:
        flags.append(problem)
    if _empty_content(block.content):
        flags.append("empty_content")

    content = block.content if isinstance(block.content, dict) else {}
    if block.type == "table":
        rows = content.get("rows") if isinstance(content, dict) else None
        if not isinstance(rows, list) or len(rows) == 0:
            flags.append("table_missing_rows")
    if block.type == "equation" and isinstance(content, dict) and content.get("parsed") is False:
        flags.append("equation_unparsed")
    if block.type in {"chart", "figure"} and isinstance(content, dict) and content.get("agreement") is False:
        flags.append("chart_disagreement")
    return flags


def _clip(value: float) -> float:
    rounded = round(value + 0.0, 4)
    if rounded < 0.0:
        return 0.0
    if rounded > 1.0:
        return 1.0
    return rounded


def _ragged_table(rows: list) -> bool:
    widths = []
    for row in rows:
        if isinstance(row, dict):
            widths.append(len(row.get("cells") or []))
        elif isinstance(row, list):
            widths.append(len(row))
    return len(set(widths)) > 1


def measure_structure(block: Block) -> float:
    """Turn P2 layout evidence and the block shape into confidence.structure."""
    score = block.order_confidence if block.order_confidence > 0 else 0.75
    layout = block.links.get("layout") or {}
    penalties = STRUCTURE_PENALTIES
    if layout.get("bbox_valid") is False:
        score -= penalties["invalid_bbox"]
    if layout.get("order_ambiguous"):
        score -= penalties["order_ambiguous"]
    route_confidence = layout.get("route_confidence")
    if isinstance(route_confidence, (int, float)) and not isinstance(route_confidence, bool):
        if route_confidence < 0.5:
            score -= penalties["weak_route"]
    warnings = layout.get("warnings") or []
    if isinstance(warnings, list) and warnings:
        score -= min(0.20, penalties["layout_warning"] * len(warnings))

    content = block.content if isinstance(block.content, dict) else None
    if _empty_content(block.content):
        score -= penalties["empty_content"]
    if block.type == "table":
        rows = content.get("rows") if isinstance(content, dict) else None
        if not isinstance(rows, list) or len(rows) == 0:
            score -= penalties["missing_rows"]
        elif _ragged_table(rows):
            score -= penalties["ragged_table"]
        from validation.arithmetic_checks import check_arithmetic

        if check_arithmetic(block).mismatches:
            score -= penalties["arith_mismatch"]
    if block.type == "equation" and isinstance(content, dict) and content.get("parsed") is False:
        score -= penalties["equation_unparsed"]
    if block.type in {"chart", "figure"} and isinstance(content, dict) and content.get("agreement") is False:
        score -= penalties["chart_disagreement"]
    return _clip(score)
