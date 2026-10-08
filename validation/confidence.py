"""Weighted trust score for one block.

The weights are an implementation heuristic. They are not a DQCL requirement.
Change them in WEIGHTS. Each triple is (extraction, structure, source_quality)
and sums to 1.
"""

from dataclasses import dataclass

from pipeline.schema import Block, ConfidenceInfo

# extraction, structure, source_quality
_TEXT = (0.60, 0.25, 0.15)
_TABLE = (0.45, 0.40, 0.15)
_VISUAL = (0.50, 0.30, 0.20)
_EQUATION = (0.65, 0.25, 0.10)
_NUMERIC = (0.65, 0.20, 0.15)

WEIGHTS: dict[str, tuple[float, float, float]] = {
    "paragraph": _TEXT,
    "heading": _TEXT,
    "list": _TEXT,
    "caption": _TEXT,
    "footnote": _TEXT,
    "header": _TEXT,
    "footer": _TEXT,
    "table": _TABLE,
    "chart": _VISUAL,
    "figure": _VISUAL,
    "equation": _EQUATION,
    "numeric": _NUMERIC,
}


@dataclass(frozen=True)
class ConfidenceScore:
    final: float | None
    valid: bool
    reason: str | None = None


def component_weights(block_type: str) -> tuple[float, float, float] | None:
    if not isinstance(block_type, str):
        return None
    return WEIGHTS.get(block_type)


def _component(name: str, value) -> str | None:
    if isinstance(value, bool) or value is None:
        return f"{name} is missing"
    if isinstance(value, (int, float)):
        if value != value or value in {float("inf"), float("-inf")}:
            return f"{name} is not a finite number"
        if value < 0.0 or value > 1.0:
            return f"{name} is outside [0, 1]"
        return None
    return f"{name} is not a number"


def _round4(value: float) -> float:
    rounded = round(value + 0.0, 4)
    if rounded < 0.0:
        return 0.0
    if rounded > 1.0:
        return 1.0
    return rounded


def score_confidence(extraction, structure, source_quality, block_type: str) -> ConfidenceScore:
    """Weighted sum of the three components. Invalid input does not invent a score."""
    weights = component_weights(block_type)
    if weights is None:
        return ConfidenceScore(final=None, valid=False, reason="block type has no weight configuration")

    for name, value in (
        ("extraction", extraction),
        ("structure", structure),
        ("source_quality", source_quality),
    ):
        problem = _component(name, value)
        if problem is not None:
            return ConfidenceScore(final=None, valid=False, reason=problem)

    extraction_weight, structure_weight, source_weight = weights
    final = (
        extraction_weight * float(extraction)
        + structure_weight * float(structure)
        + source_weight * float(source_quality)
    )
    return ConfidenceScore(final=_round4(final), valid=True)


SOURCE_PENALTIES = {
    "scanned": 0.25,
    "ocr_extractor": 0.15,
    "ocr_low_conf": 0.30,
    "vlm_unavailable": 0.10,
    "figure_not_read": 0.20,
    "failed": 0.40,
    "weak_history": 0.10,
}

_OCR_EXTRACTORS = {"paddleocr", "paddleocr_table"}


def measure_source_quality(block: Block) -> float:
    """Turn the extractor, scan flag, and flags into confidence.source_quality."""
    score = 1.0
    layout = block.links.get("layout") or {}
    if layout.get("is_scanned"):
        score -= SOURCE_PENALTIES["scanned"]
    if block.extractor in _OCR_EXTRACTORS:
        score -= SOURCE_PENALTIES["ocr_extractor"]
    flags = set(block.flags)
    if "ocr_low_conf" in flags:
        score -= SOURCE_PENALTIES["ocr_low_conf"]
    if "vlm_unavailable" in flags:
        score -= SOURCE_PENALTIES["vlm_unavailable"]
    if "figure_not_read" in flags:
        score -= SOURCE_PENALTIES["figure_not_read"]
    if block.status == "failed":
        score -= SOURCE_PENALTIES["failed"]
    for entry in block.history:
        if not isinstance(entry, dict):
            continue
        seen = entry.get("confidence")
        if isinstance(seen, (int, float)) and not isinstance(seen, bool) and seen < 0.70:
            score -= SOURCE_PENALTIES["weak_history"]
            break
    return _round4(score)


def apply_confidence(block: Block) -> tuple[Block, ConfidenceScore]:
    """Fill unmeasured structure and source quality, then set final.

    A component left at 0.0 by P3 is unmeasured. A value already above 0 is kept.
    confidence.extraction is never changed.
    """
    from validation.structural_checks import measure_structure

    structure = block.confidence.structure
    source_quality = block.confidence.source_quality
    if structure == 0.0:
        structure = measure_structure(block)
    if source_quality == 0.0:
        source_quality = measure_source_quality(block)
    score = score_confidence(
        block.confidence.extraction,
        structure,
        source_quality,
        block.type,
    )
    if not score.valid or score.final is None:
        return block, score
    confidence = block.confidence.model_copy(
        update={
            "structure": structure,
            "source_quality": source_quality,
            "final": score.final,
        }
    )
    return block.model_copy(update={"confidence": confidence}), score


def confidence_view(info: ConfidenceInfo) -> tuple[float, float, float]:
    return info.extraction, info.structure, info.source_quality
