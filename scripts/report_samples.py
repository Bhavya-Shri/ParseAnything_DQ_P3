"""Run parse_document on the kept sample files and write a short JSON report."""

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.orchestrator import parse_document

SAMPLE_DIR = ROOT / "sample_docs"
OUT = ROOT / "outputs" / "sample_parse_report.json"

FILES = [
    "11_empty.pdf",
    "11_notes.txt",
    "04_corrupt_pdf.pdf",
    "simple.pdf",
    "table.pdf",
    "03_borderless_table.pdf",
    "03_two_column.pdf",
    "04_ruled_cross_page_table.pdf",
    "chart.pdf",
    "equation.pdf",
    "sample.docx",
    "sample.xlsx",
    "sample.pptx",
    "scanned.pdf",
    "02_phone_scan_table.png",
    "fin_rep.pdf",
]


def _preview(block) -> str:
    content = block.content
    if isinstance(content, dict):
        if content.get("text"):
            return str(content["text"])[:80]
        if content.get("latex"):
            return str(content["latex"])[:80]
        rows = content.get("rows") or []
        cells = []
        for row in rows[:2]:
            for cell in row.get("cells") or []:
                if cell.get("text"):
                    cells.append(str(cell["text"]))
        if cells:
            return " | ".join(cells)[:80]
        points = ((content.get("series") or [{}])[0].get("points") or [])
        if points:
            return ", ".join(str(point.get("value")) for point in points[:4])
    return str(content)[:80]


def _summarize(doc) -> dict:
    counts: dict[str, int] = {}
    extractors: dict[str, int] = {}
    for block in doc.blocks:
        counts[block.type] = counts.get(block.type, 0) + 1
        extractors[block.extractor] = extractors.get(block.extractor, 0) + 1
    merged = [
        block.id
        for block in doc.blocks
        if (block.links.get("table_merge") or {}).get("merged")
    ]
    return {
        "status": doc.status,
        "pages": doc.page_count,
        "blocks": len(doc.blocks),
        "types": counts,
        "extractors": extractors,
        "merged_tables": merged,
        "errors": [
            {"code": error.get("error_code"), "message": error.get("message")}
            for error in doc.errors
        ],
        "flags": sorted({flag for block in doc.blocks for flag in block.flags}),
        "previews": [
            {"type": block.type, "status": block.status, "text": _preview(block)}
            for block in doc.blocks[:8]
        ],
        "ready_for": doc.metrics.get("ready_for"),
        "seconds": doc.metrics.get("total_time_seconds"),
    }


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = []
    if OUT.exists():
        report = json.loads(OUT.read_text(encoding="utf-8"))
    done = {item["file"] for item in report}
    for name in FILES:
        if name in done:
            print("skip", name, flush=True)
            continue
        path = SAMPLE_DIR / name
        print("run", name, flush=True)
        try:
            doc = parse_document(str(path))
            item = {"file": name, **_summarize(doc)}
        except Exception as exc:
            item = {"file": name, "status": "crash", "error": f"{type(exc).__name__}: {exc}"}
        report.append(item)
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k: item[k] for k in item if k != "previews"}), flush=True)


if __name__ == "__main__":
    main()
