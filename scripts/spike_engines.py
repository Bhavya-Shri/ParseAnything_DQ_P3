"""Step 1 spike. Each engine must print a real value from a sample file.

A failure is recorded and does not hide the other engines.
"""

from pathlib import Path
import traceback

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = ROOT / "sample_docs"
REPORT = ROOT / "outputs" / "spike_report.txt"


def _section(name: str) -> str:
    return f"\n## {name}\n"


def spike_pymupdf() -> str:
    import fitz

    path = SAMPLE_DIR / "simple.pdf"
    doc = fitz.open(path)
    page = doc[0]
    words = page.get_text("words")
    text = page.get_text("text").strip().splitlines()
    first = text[0] if text else ""
    box = list(words[0][:4]) if words else []
    doc.close()
    return (
        f"PASS pymupdf {fitz.__doc__.splitlines()[0] if fitz.__doc__ else 'pymupdf'}\n"
        f"file={path.name} words={len(words)} first_line={first!r} first_bbox={box}\n"
    )


def spike_docling() -> str:
    from docling.document_converter import DocumentConverter

    path = SAMPLE_DIR / "simple.pdf"
    result = DocumentConverter().convert(str(path))
    markdown = result.document.export_to_markdown().strip()
    preview = " ".join(markdown.split())[:180]
    return f"PASS docling preview={preview!r}\n"


def spike_paddleocr() -> str:
    import fitz
    from paddleocr import PaddleOCR

    pdf_path = SAMPLE_DIR / "scanned.pdf"
    image_path = ROOT / "outputs" / "scanned_page.png"
    doc = fitz.open(pdf_path)
    pix = doc[0].get_pixmap(dpi=150)
    pix.save(str(image_path))
    doc.close()

    ocr = PaddleOCR(lang="en")
    if hasattr(ocr, "predict"):
        raw = ocr.predict(str(image_path))
    else:
        raw = ocr.ocr(str(image_path))
    text = _first_ocr_text(raw)
    return f"PASS paddleocr text={text!r}\n"


def _first_ocr_text(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, list):
        for item in raw:
            found = _first_ocr_text(item)
            if found:
                return found
        return ""
    if isinstance(raw, dict):
        for key in ("rec_texts", "text", "transcription"):
            value = raw.get(key)
            if isinstance(value, list) and value:
                return str(value[0])
            if isinstance(value, str) and value:
                return value
        for value in raw.values():
            found = _first_ocr_text(value)
            if found:
                return found
        return ""
    if isinstance(raw, tuple) and len(raw) >= 2:
        # Legacy PaddleOCR line: (box, (text, confidence))
        candidate = raw[1]
        if isinstance(candidate, (list, tuple)) and candidate:
            return str(candidate[0])
    return ""


def spike_openpyxl() -> str:
    from openpyxl import load_workbook

    path = SAMPLE_DIR / "sample.xlsx"
    book = load_workbook(path)
    sheet = book["Financials"]
    value = sheet["B2"].value
    book.close()
    return f"PASS openpyxl sheet=Financials cell=B2 value={value!r}\n"


def main() -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    parts = ["P3 Step 1 engine spike\n"]
    runners = [
        ("pymupdf", spike_pymupdf),
        ("docling", spike_docling),
        ("paddleocr", spike_paddleocr),
        ("openpyxl", spike_openpyxl),
    ]
    failed = 0
    for name, runner in runners:
        try:
            parts.append(_section(name))
            parts.append(runner())
        except Exception as exc:
            failed += 1
            parts.append(_section(name))
            parts.append(f"FAIL {name} {type(exc).__name__}: {exc}\n")
            parts.append(traceback.format_exc())
    report = "".join(parts)
    REPORT.write_text(report, encoding="utf-8")
    print(report)
    if failed:
        raise SystemExit(f"{failed} engine spike(s) failed. See {REPORT}")


if __name__ == "__main__":
    main()
