"""One crop, one VLM call. Credentials come from the environment or .env. A missing key does not raise."""

import base64
import io
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

_CALLS = 0
_TASKS = ("ocr", "table_cell", "latex", "chart")
_CAP = 0.85
_PROMPTS = {
    "ocr": "Read the text in this cropped region. Reply with JSON keys text and confidence.",
    "table_cell": "Read this one table cell. Reply with JSON keys text and confidence.",
    "latex": "Transcribe this equation crop as LaTeX. Reply with JSON keys text and confidence.",
    "chart": (
        "Read this bar or line chart crop. Reply with JSON keys json and confidence. "
        "json has chart_type, title, and series of points with label and value."
    ),
}


def read_crop(image, task: str, hint: str = "", *, agreed: bool = False) -> dict:
    """Read one crop. Confidence is capped at 0.85 unless a second engine already agrees."""
    if task not in _TASKS:
        return _failed(task, f"unknown task {task}")
    if image is None:
        return _failed(task, "VLM needs a crop")
    settings = _settings()
    if not settings["api_key"] or not settings["model"]:
        return _failed(task, "VLM_API_KEY is not set", flags=["vlm_unavailable"])

    global _CALLS
    _CALLS += 1
    try:
        raw = _complete(image, task, hint, settings)
    except Exception as exc:
        return _failed(task, f"{type(exc).__name__}: {exc}")
    parsed = _parse_payload(raw, task)
    parsed["confidence"] = _cap(parsed["confidence"], agreed)
    return parsed


def vlm_call_count() -> int:
    """How many times the client was invoked. A missing key does not count."""
    return _CALLS


def _complete(image, task: str, hint: str, settings: dict) -> str:
    prompt = _PROMPTS[task]
    if hint:
        prompt = f"{prompt} Hint: {hint}"
    payload = {
        "model": settings["model"],
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": _data_url(image)}},
                ],
            }
        ],
    }
    request = urllib.request.Request(
        settings["url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    content = body["choices"][0]["message"]["content"]
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    return str(content)


def _settings() -> dict:
    _load_dotenv()
    base = os.environ.get("VLM_BASE_URL", "").strip() or "https://api.openai.com/v1"
    return {
        "api_key": os.environ.get("VLM_API_KEY", "").strip(),
        "model": os.environ.get("VLM_MODEL", "").strip(),
        "url": base.rstrip("/") + "/chat/completions",
    }


def _load_dotenv() -> None:
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parse_payload(raw: str, task: str) -> dict:
    text = (raw or "").strip()
    fenced = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    fenced = re.sub(r"\s*```$", "", fenced).strip()
    try:
        data = json.loads(fenced)
    except json.JSONDecodeError:
        data = {"text": text, "confidence": 0.5}
    if not isinstance(data, dict):
        data = {"text": text, "confidence": 0.5}
    confidence = _as_confidence(data.get("confidence", 0.5))
    if task == "chart":
        payload = data.get("json", data)
        if not isinstance(payload, dict):
            payload = {"text": str(payload)}
        return {"json": payload, "confidence": confidence, "task": task, "flags": []}
    return {
        "text": str(data.get("text", text)).strip(),
        "confidence": confidence,
        "task": task,
        "flags": [],
    }


def _data_url(image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _cap(confidence: float, agreed: bool) -> float:
    value = _as_confidence(confidence)
    if agreed:
        return value
    return min(value, _CAP)


def _as_confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.5
    return max(0.0, min(1.0, number))


def _failed(task: str, note: str, flags: list[str] | None = None) -> dict:
    return {
        "text": "",
        "confidence": 0.0,
        "task": task,
        "flags": list(flags or []),
        "note": note,
    }
