"""Deterministic numeric checks. A mismatch is flagged. The source value stays as read."""

from dataclasses import dataclass, field
import re

from pipeline.schema import Block

_SKIP = {"", "-", "—", "n/a", "na", "nil"}


@dataclass
class ArithmeticReport:
    checks_run: int = 0
    mismatches: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)


def parse_number(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        if value != value or value in {float("inf"), float("-inf")}:
            return None
        return float(value)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if raw.casefold() in _SKIP:
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    cleaned = raw.replace(",", "").replace("%", "").replace("(", "").replace(")", "").strip()
    cleaned = re.sub(r"^[^\d.+-]+|[^\d.]+$", "", cleaned)
    if not cleaned or cleaned in {".", "+", "-"}:
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return -number if negative else number


def numbers_close(left: float, right: float) -> bool:
    scale = max(abs(left), abs(right), 1.0)
    return abs(left - right) <= max(0.05, scale * 0.01)


def _cell_text(cell) -> str:
    if isinstance(cell, dict):
        text = cell.get("text")
        if text is None or text == "":
            value = cell.get("value")
            return "" if value is None else str(value)
        return str(text)
    return "" if cell is None else str(cell)


def _table_grid(content: dict) -> tuple[list[str], list[list[str]]]:
    rows = content.get("rows")
    if not isinstance(rows, list):
        return [], []
    body = []
    for row in rows:
        if isinstance(row, dict):
            body.append([_cell_text(cell) for cell in row.get("cells") or []])
        elif isinstance(row, list):
            body.append([_cell_text(cell) for cell in row])
    headers = content.get("headers")
    if not isinstance(headers, list):
        header_rows = content.get("header_rows")
        if isinstance(header_rows, list) and header_rows:
            headers = header_rows[-1]
        else:
            headers = []
    return [str(header) for header in headers], body


def _label(row: list[str]) -> str:
    return row[0].strip().casefold() if row else ""


def _is_revenue(label: str) -> bool:
    return any(word in label for word in ("revenue", "sales", "turnover"))


def _is_cost(label: str) -> bool:
    return any(word in label for word in ("cost", "expense", "cogs", "opex"))


def _is_profit(label: str) -> bool:
    return any(word in label for word in ("profit", "ebitda", "ebit", "earnings"))


def _is_quarter(label: str) -> bool:
    return bool(re.fullmatch(r"q[1-4]", label.strip())) or label.strip() in {
        "first quarter",
        "second quarter",
        "third quarter",
        "fourth quarter",
    }


def _is_total(label: str) -> bool:
    text = label.strip()
    return text in {"total", "fy", "annual", "full year", "year"} or text.startswith("total")


def _numeric_columns(rows: list[list[str]]) -> list[int]:
    width = max((len(row) for row in rows), default=0)
    columns = []
    for index in range(1, width):
        values = [parse_number(row[index]) for row in rows if len(row) > index and row[index].strip()]
        parsed = [value for value in values if value is not None]
        if parsed and len(parsed) == len(values):
            columns.append(index)
    return columns


def _check_profit(body: list[list[str]], report: ArithmeticReport) -> None:
    revenue = [row for row in body if _is_revenue(_label(row))]
    cost = [row for row in body if _is_cost(_label(row))]
    profit = [row for row in body if _is_profit(_label(row))]
    if not revenue or not cost or not profit:
        return
    if len(revenue) > 1 or len(cost) > 1 or len(profit) > 1:
        report.ambiguous.append("more than one revenue, cost, or profit row")
        return
    for column in _numeric_columns(body):
        values = []
        missing = False
        for row in (revenue[0], cost[0], profit[0]):
            if len(row) <= column:
                missing = True
                break
            number = parse_number(row[column])
            if number is None:
                missing = True
                break
            values.append(number)
        if missing:
            report.ambiguous.append(f"profit check column {column} is not fully numeric")
            continue
        report.checks_run += 1
        expected = values[0] - values[1]
        if not numbers_close(expected, values[2]):
            report.mismatches.append(
                f"column {column}: revenue {values[0]} - cost {values[1]} = {expected}, profit cell is {values[2]}"
            )


def _check_quarters(body: list[list[str]], report: ArithmeticReport) -> None:
    quarters = [row for row in body if _is_quarter(_label(row))]
    totals = [row for row in body if _is_total(_label(row))]
    if len(quarters) < 2 or len(totals) != 1:
        return
    for column in _numeric_columns(quarters + totals):
        numbers = []
        missing = False
        for row in quarters:
            if len(row) <= column:
                missing = True
                break
            number = parse_number(row[column])
            if number is None:
                missing = True
                break
            numbers.append(number)
        total_row = totals[0]
        total = parse_number(total_row[column]) if len(total_row) > column else None
        if missing or total is None:
            report.ambiguous.append(f"quarter check column {column} is not fully numeric")
            continue
        report.checks_run += 1
        expected = sum(numbers)
        if not numbers_close(expected, total):
            report.mismatches.append(
                f"column {column}: quarters sum to {expected}, total cell is {total}"
            )


def _check_header_quarters(headers: list[str], body: list[list[str]], report: ArithmeticReport) -> None:
    names = [header.strip().casefold() for header in headers]
    quarter_indexes = [index for index, name in enumerate(names) if _is_quarter(name)]
    total_indexes = [index for index, name in enumerate(names) if _is_total(name)]
    if len(quarter_indexes) < 2 or len(total_indexes) != 1:
        return
    total_index = total_indexes[0]
    for row in body:
        numbers = []
        missing = False
        for index in quarter_indexes:
            if index >= len(row):
                missing = True
                break
            number = parse_number(row[index])
            if number is None:
                missing = True
                break
            numbers.append(number)
        total = parse_number(row[total_index]) if total_index < len(row) else None
        if missing or total is None:
            continue
        report.checks_run += 1
        expected = sum(numbers)
        if not numbers_close(expected, total):
            report.mismatches.append(
                f"row {_label(row) or 'values'}: quarters sum to {expected}, total cell is {total}"
            )


def check_arithmetic(block: Block) -> ArithmeticReport:
    report = ArithmeticReport()
    if block.type != "table" or not isinstance(block.content, dict):
        return report
    headers, body = _table_grid(block.content)
    if not body:
        return report
    _check_profit(body, report)
    _check_quarters(body, report)
    _check_header_quarters(headers, body, report)
    return report
