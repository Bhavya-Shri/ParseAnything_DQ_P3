"""Fail-safe. Uncertain content is flagged and left as extracted."""

from pipeline.schema import Block


def decline_repair(block: Block) -> tuple[Block, list[str]]:
    """Refuse to write a corrected value back into the block."""
    flagged = {"arith_mismatch", "verification_conflict", "arithmetic_ambiguous", "empty_content"}
    if not flagged.intersection(block.flags):
        return block, []
    return block, ["repair_declined"]
