"""Compare a primary block with a secondary result supplied by the extraction layer.

P4 does not run a second extractor. Agreement can mark the block verified.
A conflict is flagged and the primary content is left in place.
"""

from pipeline.schema import Block, VerificationResult

from validation.arithmetic_checks import numbers_close, parse_number


def verification_required(block: Block) -> bool:
    return block.risk in {"HIGH", "CRITICAL"}


def results_agree(primary, secondary) -> bool:
    if primary == secondary:
        return True
    if isinstance(primary, str) and isinstance(secondary, str):
        left = " ".join(primary.split()).casefold()
        right = " ".join(secondary.split()).casefold()
        return left == right
    left = parse_number(primary)
    right = parse_number(secondary)
    if left is not None and right is not None:
        return numbers_close(left, right)
    return False


def apply_verification(block: Block, secondary=None) -> tuple[Block, list[str]]:
    """Return the block and any new flags. Content is not replaced."""
    flags: list[str] = []
    if secondary is None:
        if verification_required(block) and block.status != "failed":
            flags.append("verification_required")
            if block.status != "needs_review":
                block = block.model_copy(update={"status": "unaudited"})
        return block, flags

    agreed = results_agree(block.content, secondary)
    verification = VerificationResult(
        method="secondary_result",
        agreement=1.0 if agreed else 0.0,
        conflict=not agreed,
        secondary_value=secondary,
    )
    if agreed:
        status = "verified" if block.status != "failed" else "failed"
    else:
        flags.append("verification_conflict")
        status = "failed" if block.status == "failed" else "needs_review"
    return block.model_copy(update={"verification": verification, "status": status}), flags
