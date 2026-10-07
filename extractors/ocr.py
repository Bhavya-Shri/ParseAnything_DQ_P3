"""OCR for a scanned region. PaddleOCR runs on the crop. The raw crop is kept for evidence."""

import os
from pathlib import Path

import pymupdf

from extractors.base import Extractor
from extractors.utils import crop_region, failed_block, make_block, region_field

_ENGINE = None
_LOW_CONFIDENCE = 0.70
_RENDER_DPI = 150
_ROOT = Path(__file__).resolve().parent.parent


class OcrExtractor(Extractor):
    name = "paddleocr"

    def can_handle(self, region) -> bool:
        route = region_field(region, "route")
        if route not in (None, "", "ocr"):
            return False
        if route == "ocr":
            return True
        return bool(region_field(region, "is_scanned")) and region_field(region, "type") in (
            None,
            "",
            "text",
        )

    def extract(self, region, context) -> list:
        context = context or {}
        try:
            image, page_size, region_box = _open_crop_source(region, context)
        except Exception as exc:
            return [
                failed_block(
                    region,
                    error_code="OCR_FAILED",
                    message=str(exc),
                    extractor=self.name,
                )
            ]
        if image is None:
            return [
                failed_block(
                    region,
                    error_code="OCR_FAILED",
                    message="OCR needs a page image or a PDF file",
                    extractor=self.name,
                )
            ]

        crop = crop_region(image, region_box, page_size)
        crop_path = _save_crop(crop, region)
        scale_x = image.width / float(page_size["width"])
        scale_y = image.height / float(page_size["height"])
        ocr_path, angle = _prepare_ocr_image(crop, crop_path)

        try:
            raw = _engine().predict(str(ocr_path))
            lines = _parse_lines(raw, region_box, scale_x, scale_y, angle, crop.size)
        except Exception as exc:
            return [
                failed_block(
                    region,
                    error_code="OCR_FAILED",
                    message=f"{type(exc).__name__}: {exc}. crop={crop_path}",
                    extractor=self.name,
                )
            ]
        if not lines:
            return [_empty_or_vlm(region, context, crop, crop_path)]

        extraction = _weighted_confidence(lines)
        text = " ".join(line["text"] for line in lines)
        boxes = [line["bbox"] for line in lines]
        page_number = int(region_field(region, "page", 1) or 1)
        flags = []
        status = "accepted"
        history = [
            {
                "engine": self.name,
                "confidence": extraction,
                "note": "ocr",
                "crop": str(crop_path),
            }
        ]
        if extraction < _LOW_CONFIDENCE:
            flags.append("ocr_low_conf")
            vlm = _read_vlm(crop, "ocr")
            history.append(_vlm_entry(vlm))
            if "vlm_unavailable" in vlm.get("flags", []):
                flags.append("vlm_unavailable")
            elif vlm.get("text") and _different(text, vlm["text"]):
                status = "needs_review"
        return [
            make_block(
                extractor=self.name,
                bbox=_union(boxes),
                page_start=page_number if page_number >= 1 else 1,
                extraction=extraction,
                block_type="paragraph",
                content={"text": text, "lines": lines},
                region_id=str(region_field(region, "id", "region")),
                status=status,
                flags=flags,
                source_file=str(context.get("file_path") or ""),
                history=history,
            )
        ]


def _empty_or_vlm(region, context, crop, crop_path):
    vlm = _read_vlm(crop, "ocr")
    page_number = int(region_field(region, "page", 1) or 1)
    if vlm.get("text") and "vlm_unavailable" not in vlm.get("flags", []):
        box = region_field(region, "bbox") or [0.0, 0.0, 0.0, 0.0]
        return make_block(
            extractor="vlm",
            bbox=[float(value) for value in box],
            page_start=page_number if page_number >= 1 else 1,
            extraction=float(vlm["confidence"]),
            block_type="paragraph",
            content={"text": vlm["text"], "lines": []},
            region_id=str(region_field(region, "id", "region")),
            source_file=str(context.get("file_path") or ""),
            history=[
                {
                    "engine": "paddleocr",
                    "confidence": 0.0,
                    "note": f"No text recognized. crop={crop_path}",
                    "error_code": "OCR_FAILED",
                    "crop": str(crop_path),
                },
                _vlm_entry(vlm),
            ],
        )
    block = failed_block(
        region,
        error_code="OCR_FAILED",
        message=f"No text recognized. crop={crop_path}",
        extractor="paddleocr",
    )
    block.history.append(_vlm_entry(vlm))
    if "vlm_unavailable" in vlm.get("flags", []):
        block.flags.append("vlm_unavailable")
    return block


def _read_vlm(crop, task: str, hint: str = "") -> dict:
    from extractors.vlm import read_crop

    try:
        return read_crop(crop, task, hint)
    except Exception as exc:
        return {
            "text": "",
            "confidence": 0.0,
            "task": task,
            "flags": [],
            "note": f"{type(exc).__name__}: {exc}",
        }


def _vlm_entry(vlm: dict) -> dict:
    return {
        "engine": "vlm",
        "confidence": float(vlm.get("confidence") or 0.0),
        "note": vlm.get("note") or vlm.get("text") or "vlm_unavailable",
        "task": vlm.get("task", "ocr"),
    }


def _different(left: str, right: str) -> bool:
    from difflib import SequenceMatcher

    a = " ".join(left.lower().split())
    b = " ".join(right.lower().split())
    if not a or not b:
        return False
    return SequenceMatcher(None, a, b).ratio() < 0.8


def _engine():
    global _ENGINE
    if _ENGINE is None:
        os.environ["FLAGS_use_mkldnn"] = "0"
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        from paddleocr import PaddleOCR

        _ENGINE = PaddleOCR(
            lang="en",
            enable_mkldnn=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            return_word_box=True,
        )
    return _ENGINE


def _open_crop_source(region, context):
    page_image = context.get("page_image")
    page_size = context.get("page_size")
    path = context.get("file_path")
    page_number = int(region_field(region, "page", 1) or 1)
    if page_image is not None and page_size:
        from PIL import Image

        image = page_image if hasattr(page_image, "crop") else Image.open(page_image)
        box = _region_box(region, float(page_size["width"]), float(page_size["height"]))
        return image, page_size, box
    if not path or not Path(path).is_file():
        return None, None, None
    document = pymupdf.open(path)
    try:
        index = page_number - 1 if page_number >= 1 else 0
        if index < 0 or index >= document.page_count:
            raise ValueError(f"Page {page_number} is outside the PDF")
        page = document[index]
        pixmap = page.get_pixmap(dpi=_RENDER_DPI)
        from PIL import Image

        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        size = {"width": float(page.rect.width), "height": float(page.rect.height)}
        box = _region_box(region, size["width"], size["height"])
        return image, size, box
    finally:
        document.close()


def _region_box(region, width: float, height: float) -> list[float]:
    bbox = region_field(region, "bbox")
    if not bbox or len(bbox) != 4:
        return [0.0, 0.0, width, height]
    return [float(value) for value in bbox]


def _save_crop(crop, region) -> Path:
    folder = _ROOT / "outputs" / "crops"
    folder.mkdir(parents=True, exist_ok=True)
    region_id = str(region_field(region, "id", "region")).replace("/", "_")
    page = region_field(region, "page", 1)
    path = folder / f"{region_id}_p{page}.png"
    crop.save(path)
    return path


def _prepare_ocr_image(crop, crop_path: Path) -> tuple[Path, float]:
    """Return the image Paddle should read, and the deskew angle applied to it.

    The file at crop_path is the untouched crop. A cleaned copy is a sibling file.
    """
    import cv2
    import numpy as np

    rgb = np.array(crop.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    contrast = float(gray.std())
    angle = _skew_angle(gray)
    if blur >= 80 and contrast >= 25 and abs(angle) <= 2:
        return crop_path, 0.0

    working = rgb[:, :, ::-1].copy()
    if abs(angle) > 2:
        working = _rotate(working, angle)
    gray = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    binary = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )
    cleaned = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    cleaned_path = crop_path.with_name(crop_path.stem + "_ocr.png")
    cv2.imwrite(str(cleaned_path), cleaned)
    return cleaned_path, angle if abs(angle) > 2 else 0.0


def _skew_angle(gray) -> float:
    import cv2
    import numpy as np

    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(binary > 0))
    if len(coords) < 50:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    elif angle > 45:
        angle = angle - 90
    return float(angle)


def _rotate(image, angle: float):
    import cv2

    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image, matrix, (width, height), borderValue=(255, 255, 255)
    )


def _parse_lines(raw, region_box, scale_x, scale_y, angle, crop_size) -> list[dict]:
    lines = []
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        texts = _as_list(_get(item, "rec_texts", []))
        scores = _as_list(_get(item, "rec_scores", []))
        boxes = _get(item, "rec_boxes", [])
        word_texts = _get(item, "text_word", None)
        word_regions = _get(item, "text_word_region", None)
        for index, text in enumerate(texts):
            value = str(text).strip()
            if not value:
                continue
            score = float(scores[index]) if index < len(scores) else 0.0
            pixel_box = _box_at(boxes, index)
            page_box = _to_page(pixel_box, region_box, scale_x, scale_y, angle, crop_size)
            words = _words_for_line(
                index, word_texts, word_regions, score, region_box, scale_x, scale_y, angle, crop_size
            )
            lines.append(
                {
                    "text": value,
                    "bbox": page_box,
                    "confidence": max(0.0, min(1.0, score)),
                    "words": words,
                }
            )
    return lines


def _words_for_line(index, word_texts, word_regions, score, region_box, scale_x, scale_y, angle, crop_size):
    if _empty(word_texts) or index >= len(word_texts):
        return []
    texts = _as_list(word_texts[index])
    regions = [] if _empty(word_regions) or index >= len(word_regions) else word_regions[index]
    words = []
    for word_index, word in enumerate(texts):
        label = str(word).strip()
        if not label:
            continue
        polygon = regions[word_index] if word_index < len(regions) else None
        pixel_box = _polygon_bbox(polygon) if polygon is not None else [0, 0, 0, 0]
        words.append(
            {
                "text": label,
                "bbox": _to_page(pixel_box, region_box, scale_x, scale_y, angle, crop_size),
                "confidence": max(0.0, min(1.0, score)),
            }
        )
    return words


def _box_at(boxes, index) -> list[float]:
    try:
        box = boxes[index]
    except Exception:
        return [0, 0, 0, 0]
    if hasattr(box, "tolist"):
        box = box.tolist()
    if len(box) == 4 and not isinstance(box[0], (list, tuple)):
        return [float(value) for value in box]
    return _polygon_bbox(box)


def _polygon_bbox(polygon) -> list[float]:
    if hasattr(polygon, "tolist"):
        polygon = polygon.tolist()
    xs = [float(point[0]) for point in polygon]
    ys = [float(point[1]) for point in polygon]
    return [min(xs), min(ys), max(xs), max(ys)]


def _to_page(pixel_box, region_box, scale_x, scale_y, angle, crop_size) -> list[float]:
    x1, y1, x2, y2 = (float(value) for value in pixel_box)
    if angle:
        width, height = crop_size
        corners = [
            _unrotate(x1, y1, angle, width / 2, height / 2),
            _unrotate(x2, y1, angle, width / 2, height / 2),
            _unrotate(x2, y2, angle, width / 2, height / 2),
            _unrotate(x1, y2, angle, width / 2, height / 2),
        ]
        xs = [point[0] for point in corners]
        ys = [point[1] for point in corners]
        x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
    return [
        region_box[0] + x1 / scale_x,
        region_box[1] + y1 / scale_y,
        region_box[0] + x2 / scale_x,
        region_box[1] + y2 / scale_y,
    ]


def _unrotate(x, y, angle, cx, cy) -> tuple[float, float]:
    import math

    theta = math.radians(-angle)
    dx, dy = x - cx, y - cy
    return (
        cx + dx * math.cos(theta) - dy * math.sin(theta),
        cy + dx * math.sin(theta) + dy * math.cos(theta),
    )


def _weighted_confidence(lines: list[dict]) -> float:
    weight = 0
    total = 0.0
    for line in lines:
        count = max(len(line["text"]), 1)
        total += line["confidence"] * count
        weight += count
    if weight == 0:
        return 0.0
    score = total / weight
    return max(0.0, min(1.0, score))


def _as_list(value):
    if value is None:
        return []
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        value = value.tolist()
    return list(value)


def _empty(value) -> bool:
    if value is None:
        return True
    size = getattr(value, "size", None)
    if size is not None:
        return size == 0
    return len(value) == 0


def _get(item, key, default=None):
    try:
        if isinstance(item, dict):
            return item.get(key, default)
        return item[key]
    except Exception:
        return default


def _union(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]
