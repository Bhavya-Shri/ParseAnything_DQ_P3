"""Equation regions become LaTeX. The formula model reads the crop. A parse check decides the status."""

import os
import re
from difflib import SequenceMatcher

import pymupdf

from extractors.base import Extractor
from extractors.utils import failed_block, make_block, region_field

_ENGINE = None
_CARET = re.compile(r"\^([A-Za-z0-9])(?!})")


class EquationExtractor(Extractor):
    name = "formula"

    def can_handle(self, region) -> bool:
        route = region_field(region, "route")
        if route == "formula":
            return True
        if route not in (None, ""):
            return False
        return region_field(region, "type") == "equation"

    def extract(self, region, context) -> list:
        context = context or {}
        path = context.get("file_path")
        if not path:
            return [_fail(region, "Equation extraction needs a file")]
        try:
            native, bbox = _native_formula(path, region)
        except Exception as exc:
            return [_fail(region, f"{type(exc).__name__}: {exc}")]
        model = ""
        model_note = ""
        try:
            model = _model_formula(region, context)
        except Exception as exc:
            model_note = f"{type(exc).__name__}: {exc}"

        chosen, parsed, other = _choose(native, model)
        if not chosen:
            return [_fail(region, model_note or "No formula text recognized")]

        page_number = int(region_field(region, "page", 1) or 1)
        history = [
            {"engine": "pymupdf", "confidence": 0.9 if native else 0.0, "note": native},
            {"engine": self.name, "confidence": 0.85 if parsed else 0.4, "note": model or model_note},
        ]
        flags = []
        status = "accepted"
        if not parsed:
            status = "needs_review"
            flags.append("formula_parse_fail")
            history.append({"engine": "vlm", "confidence": 0.0, "note": "vlm_unavailable"})
        elif other and _similarity(chosen, other) < 0.8:
            status = "needs_review"
            history.append(
                {
                    "engine": "compare",
                    "confidence": _similarity(chosen, other),
                    "note": "text layer and formula model disagree",
                    "error_code": "EXTRACTION_CONFLICT",
                }
            )
        else:
            other = ""
        return [
            make_block(
                extractor=self.name,
                bbox=bbox or _region_or_empty(region),
                page_start=page_number if page_number >= 1 else 1,
                extraction=0.9 if parsed else 0.4,
                block_type="equation",
                content={
                    "latex": chosen,
                    "parsed": parsed,
                    "candidates": [other] if other and other != chosen else [],
                },
                region_id=str(region_field(region, "id", "region")),
                status=status,
                flags=flags,
                source_file=str(path),
                history=history,
            )
        ]


def latex_parses(latex: str) -> bool:
    """True when the string is syntactically plausible LaTeX."""
    text = (latex or "").strip()
    if not text or text.count("{") != text.count("}"):
        return False
    try:
        from pylatexenc.latexwalker import LatexWalker

        nodes, _, _ = LatexWalker(text).get_latex_nodes()
    except Exception:
        return False
    return bool(nodes)


def _choose(native: str, model: str) -> tuple[str, bool, str]:
    native_text = _normalize(native)
    model_text = _normalize(model)
    native_ok = latex_parses(native_text) if native_text else False
    model_ok = latex_parses(model_text) if model_text else False
    if model_ok and (
        not native_text or not native_ok or _similarity(model_text, native_text) >= 0.8
    ):
        return model_text, True, native_text
    if native_ok:
        return native_text, True, model_text
    if model_text:
        return model_text, False, native_text
    if native_text:
        return native_text, False, model_text
    return "", False, ""


def _normalize(text: str) -> str:
    cleaned = " ".join((text or "").split())
    return _CARET.sub(r"^{\1}", cleaned)


def _native_formula(path, region) -> tuple[str, list[float] | None]:
    page_number = int(region_field(region, "page", 1) or 1)
    document = pymupdf.open(path)
    try:
        index = page_number - 1 if page_number >= 1 else 0
        if index < 0 or index >= document.page_count:
            raise ValueError(f"Page {page_number} is outside the PDF")
        page = document[index]
        box = region_field(region, "bbox")
        region_box = [float(value) for value in box] if box and len(box) == 4 else [
            page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1
        ]
        grouped: dict[tuple, list] = {}
        for word in page.get_text("words"):
            cx = (word[0] + word[2]) / 2
            cy = (word[1] + word[3]) / 2
            if region_box[0] <= cx <= region_box[2] and region_box[1] <= cy <= region_box[3]:
                grouped.setdefault((word[5], word[6]), []).append(word)
    finally:
        document.close()
    if not grouped:
        return "", None
    lines = []
    for words in grouped.values():
        words.sort(key=lambda item: item[0])
        text = " ".join(item[4] for item in words)
        bbox = [
            min(item[0] for item in words),
            min(item[1] for item in words),
            max(item[2] for item in words),
            max(item[3] for item in words),
        ]
        lines.append((text, bbox, _math_score(text)))
    lines.sort(key=lambda item: item[2], reverse=True)
    return lines[0][0], lines[0][1]


def _model_formula(region, context) -> str:
    from extractors.ocr import _open_crop_source, _save_crop

    image, page_size, region_box = _open_crop_source(region, context)
    if image is None:
        return ""
    from extractors.utils import crop_region

    crop = crop_region(image, region_box, page_size)
    if crop.width < 2 or crop.height < 2 or _blank(crop):
        return ""
    crop_path = _save_crop(crop, region)
    raw = _engine().predict(
        str(crop_path),
        use_layout_detection=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
    )
    return _latex_from_result(raw)


def _engine():
    global _ENGINE
    if _ENGINE is None:
        os.environ["FLAGS_use_mkldnn"] = "0"
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        from paddleocr import FormulaRecognitionPipeline

        _ENGINE = FormulaRecognitionPipeline(
            enable_mkldnn=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_layout_detection=False,
        )
    return _ENGINE


def _latex_from_result(raw) -> str:
    pieces = []
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        results = _value(item, "formula_res_list") or []
        for result in results:
            formula = _value(result, "rec_formula")
            if formula is None:
                continue
            text = str(formula).strip()
            if text:
                pieces.append(text)
    return " ".join(pieces)


def _blank(image) -> bool:
    gray = image.convert("L")
    sample = list(gray.resize((32, 32)).get_flattened_data())
    return max(sample) - min(sample) < 12


def _math_score(text: str) -> int:
    return sum(text.count(symbol) for symbol in "=^_{}\\")


def _similarity(left: str, right: str) -> float:
    a = " ".join(left.lower().split())
    b = " ".join(right.lower().split())
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _region_or_empty(region) -> list[float]:
    bbox = region_field(region, "bbox")
    if bbox and len(bbox) == 4:
        return [float(value) for value in bbox]
    return [0.0, 0.0, 0.0, 0.0]


def _value(item, key):
    try:
        if isinstance(item, dict):
            return item.get(key)
        return item[key]
    except Exception:
        return None


def _fail(region, message: str):
    return failed_block(
        region,
        error_code="FORMULA_FAILED",
        message=message,
        extractor="formula",
    )
