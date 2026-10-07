"""VLM fallback. The client is mocked. This file does not call a live model."""

from PIL import Image

from extractors.vlm import read_crop, vlm_call_count


def _ready(monkeypatch, payload: str):
    monkeypatch.setenv("VLM_API_KEY", "test-key")
    monkeypatch.setenv("VLM_MODEL", "test-model")
    monkeypatch.setenv("VLM_BASE_URL", "https://example.invalid/v1")
    seen = {}

    def fake_complete(image, task, hint, settings):
        seen["size"] = image.size
        seen["task"] = task
        seen["hint"] = hint
        seen["model"] = settings["model"]
        return payload

    monkeypatch.setattr("extractors.vlm._complete", fake_complete)
    return seen


def test_read_crop_caps_confidence_and_counts(monkeypatch):
    seen = _ready(monkeypatch, '{"text": "128.5 crore", "confidence": 0.99}')
    image = Image.new("RGB", (40, 20), "white")
    before = vlm_call_count()
    result = read_crop(image, "ocr", hint="revenue")
    assert seen["size"] == (40, 20)
    assert seen["task"] == "ocr"
    assert seen["hint"] == "revenue"
    assert result["text"] == "128.5 crore"
    assert result["confidence"] == 0.85
    assert result["task"] == "ocr"
    assert vlm_call_count() == before + 1


def test_agreement_keeps_the_reported_confidence(monkeypatch):
    _ready(monkeypatch, '{"text": "E = mc^{2}", "confidence": 0.99}')
    result = read_crop(Image.new("RGB", (8, 8), "white"), "latex", agreed=True)
    assert result["text"] == "E = mc^{2}"
    assert result["confidence"] == 0.99


def test_chart_task_returns_json(monkeypatch):
    _ready(
        monkeypatch,
        '{"json": {"chart_type": "bar", "series": [{"points": [{"label": "2023", "value": 92.4}]}]}, "confidence": 0.91}',
    )
    result = read_crop(Image.new("RGB", (12, 12), "white"), "chart")
    assert result["json"]["chart_type"] == "bar"
    assert result["confidence"] == 0.85


def test_missing_key_does_not_call_or_raise(monkeypatch):
    monkeypatch.delenv("VLM_API_KEY", raising=False)
    monkeypatch.delenv("VLM_MODEL", raising=False)
    monkeypatch.setattr("extractors.vlm._load_dotenv", lambda: None)

    def fake_complete(*args, **kwargs):
        raise AssertionError("client should not run")

    monkeypatch.setattr("extractors.vlm._complete", fake_complete)
    before = vlm_call_count()
    result = read_crop(Image.new("RGB", (4, 4), "white"), "latex")
    assert result["confidence"] == 0.0
    assert "vlm_unavailable" in result["flags"]
    assert vlm_call_count() == before


def test_client_error_does_not_raise(monkeypatch):
    monkeypatch.setenv("VLM_API_KEY", "test-key")
    monkeypatch.setenv("VLM_MODEL", "test-model")
    monkeypatch.setattr("extractors.vlm._load_dotenv", lambda: None)

    def fake_complete(*args, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr("extractors.vlm._complete", fake_complete)
    result = read_crop(Image.new("RGB", (4, 4), "white"), "table_cell")
    assert result["confidence"] == 0.0
    assert "down" in result["note"]
    assert "vlm_unavailable" not in result["flags"]
