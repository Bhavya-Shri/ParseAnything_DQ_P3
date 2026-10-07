from pipeline.schema import DocumentResult


def write_markdown(doc: DocumentResult, output_path: str):
    """Write blocks in reading order. Content objects stay structured."""
    lines = [f"# Document: {doc.filename}", ""]
    if doc.status == "failed":
        lines.append("**Status:** Failed")
        for error in doc.errors:
            lines.append(f"> Error ({error.get('error_code')}): {error.get('message')}")
        lines.append("")
    for block in sorted(doc.blocks, key=lambda item: item.reading_order):
        marker = " [needs review]" if block.status in {"needs_review", "failed"} else ""
        content = block.content if isinstance(block.content, dict) else {}
        if block.type == "heading":
            level = int(content.get("level") or 1)
            lines.append(f"{'#' * min(level, 6)} {_text(block.content)}{marker}")
        elif block.type in {"paragraph", "list", "caption", "footnote"}:
            lines.append(f"{_text(block.content)}{marker}")
        elif block.type == "table":
            lines.extend(_table_lines(content))
            if marker:
                lines.append(marker.strip())
        elif block.type == "equation":
            latex = content.get("latex") if isinstance(content, dict) else block.content
            lines.append(f"$$\n{latex}\n$$")
        elif block.type == "chart":
            lines.append(f"**Chart:** {_chart_summary(content)}{marker}")
        elif block.type == "figure":
            lines.append(f"**Figure:** {_text(block.content)}{marker}")
        elif block.status == "failed":
            continue
        else:
            lines.append(f"{_text(block.content)}{marker}")
        lines.append("")
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _text(content) -> str:
    if isinstance(content, dict):
        return str(content.get("text") or content.get("latex") or "")
    return str(content or "")


def _table_lines(content: dict) -> list[str]:
    headers = content.get("header_rows") or []
    header = headers[0] if headers else []
    rows = []
    for row in content.get("rows") or []:
        rows.append([cell.get("text", "") for cell in row.get("cells") or []])
    if not header and rows:
        header = [""] * len(rows[0])
    if not header:
        return ["<!-- Table Data -->"]
    width = max([len(header), *[len(row) for row in rows]] or [0])
    header = list(header) + [""] * (width - len(header))
    lines = [
        "| " + " | ".join(str(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows:
        padded = list(row) + [""] * (width - len(row))
        lines.append("| " + " | ".join(str(cell) for cell in padded) + " |")
    return lines


def _chart_summary(content: dict) -> str:
    if not isinstance(content, dict):
        return str(content or "")
    title = content.get("title") or content.get("chart_type") or "chart"
    points = []
    for series in content.get("series") or []:
        for point in series.get("points") or []:
            points.append(f"{point.get('label')} {point.get('value')}")
    detail = ", ".join(points)
    return f"{title}. {detail}" if detail else str(title)
