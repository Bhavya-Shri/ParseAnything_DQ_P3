"""Risk is separate from the confidence score. Levels stay inside the shared contract."""

import re

from pipeline.schema import Block, RiskLevel

_MONEY = re.compile(
    r"(\$|₹|€|£|\binr\b|\busd\b|\brs\.?\b|\bcrore\b|\blakh\b|\bmillion\b|\bbillion\b"
    r"|\brevenue\b|\bprofit\b|\bebitda\b|\bpercent\b|%)",
    re.IGNORECASE,
)
_DATE = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b"
    r"|\bfy\s*\d{2,4}\b",
    re.IGNORECASE,
)
_LEGAL = re.compile(
    r"event of default|material adverse|indemnif|governing law|covenant",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d")


def _blob(block: Block) -> str:
    content = block.content
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        parts = []
        for value in content.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.append(" ".join(str(item) for item in value))
        return " ".join(parts)
    return "" if content is None else str(content)


def _has_number(text: str) -> bool:
    return _NUMBER.search(text) is not None


def assign_risk(block: Block) -> RiskLevel:
    text = _blob(block)
    if _LEGAL.search(text):
        return "CRITICAL"
    if block.type == "table":
        return "CRITICAL" if _has_number(text) else "HIGH"
    if block.type == "numeric":
        return "CRITICAL" if _MONEY.search(text) else "HIGH"
    if block.type in {"chart", "figure", "equation"}:
        return "HIGH"
    if _MONEY.search(text) or _DATE.search(text):
        return "HIGH"
    return "LOW"


def apply_risk(block: Block) -> Block:
    return block.model_copy(update={"risk": assign_risk(block)})
