"""P4 trust assessment. Call assess_block on assembled Blocks. This does not extract or reorder."""

from dataclasses import dataclass, field

from pydantic import ValidationError

from pipeline.schema import Block

from validation.arithmetic_checks import check_arithmetic
from validation.confidence import apply_confidence
from validation.repair import decline_repair
from validation.risk import apply_risk
from validation.structural_checks import structural_flags
from validation.verification import apply_verification


def _add_flags(block: Block, flags: list[str]) -> Block:
    current = list(block.flags)
    for flag in flags:
        if flag not in current:
            current.append(flag)
    if current == list(block.flags):
        return block
    return block.model_copy(update={"flags": current})


@dataclass
class TrustResult:
    block: Block | None
    ok: bool
    flags: list[str] = field(default_factory=list)
    reason: str | None = None


def apply_trust(blocks: list[Block]) -> list[Block]:
    """Score assembled blocks. Content, order, extraction, status, and flags stay as received."""
    scored = []
    for block in blocks:
        if not isinstance(block, Block):
            raise TypeError("apply_trust expects Blocks from pipeline.schema")
        updated, _score = apply_confidence(block.model_copy(deep=True))
        scored.append(apply_risk(updated))
    return scored


def trust_summary(blocks: list[Block]) -> dict:
    counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    finals = []
    for block in blocks:
        counts[block.risk] = counts.get(block.risk, 0) + 1
        finals.append(block.confidence.final)
    mean = round(sum(finals) / len(finals), 4) if finals else None
    return {"total_blocks": len(blocks), "mean_final": mean, "risk_counts": counts}


def assess_block(block: Block, secondary=None) -> Block:
    """Score one assembled block. The returned block is a copy. Content is unchanged."""
    if not isinstance(block, Block):
        raise TypeError("assess_block expects a Block from pipeline.schema")

    updated = block.model_copy(deep=True)
    flags = structural_flags(updated)
    updated, score = apply_confidence(updated)
    if not score.valid:
        flags.append("confidence_invalid")

    updated = apply_risk(updated)
    arithmetic = check_arithmetic(updated)
    if arithmetic.mismatches:
        flags.append("arith_mismatch")
    if arithmetic.ambiguous:
        flags.append("arithmetic_ambiguous")

    updated = _add_flags(updated, flags)
    updated, verification_flags = apply_verification(updated, secondary)
    updated = _add_flags(updated, verification_flags)

    if "arith_mismatch" in updated.flags or "arithmetic_ambiguous" in updated.flags:
        if updated.status != "failed":
            updated = updated.model_copy(update={"status": "needs_review"})

    updated, repair_flags = decline_repair(updated)
    updated = _add_flags(updated, repair_flags)

    serious = {
        "empty_content",
        "bbox_invalid",
        "table_missing_rows",
        "equation_unparsed",
        "chart_disagreement",
        "confidence_invalid",
    }
    if serious.intersection(updated.flags) and updated.status not in {"failed", "needs_review"}:
        updated = updated.model_copy(update={"status": "needs_review"})
    return updated


def assess(data, secondary=None) -> TrustResult:
    """Assess a Block, or reject an input that is not a valid Block."""
    if isinstance(data, Block):
        block = assess_block(data, secondary)
        return TrustResult(block=block, ok=True, flags=list(block.flags))
    if not isinstance(data, dict):
        return TrustResult(block=None, ok=False, flags=["ambiguous_input"], reason="input is not a Block")
    try:
        block = Block.model_validate(data)
    except ValidationError as exc:
        return TrustResult(
            block=None,
            ok=False,
            flags=["ambiguous_input"],
            reason=str(exc.errors()[0]["msg"]) if exc.errors() else "invalid block",
        )
    assessed = assess_block(block, secondary)
    return TrustResult(block=assessed, ok=True, flags=list(assessed.flags))
