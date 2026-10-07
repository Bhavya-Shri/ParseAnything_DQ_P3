# P3 Audit Log

Running log for Person 3 (extraction). Each entry records what changed, why, and the check that followed.

Repo: https://github.com/Bhavya-Shri/ParseAnything_DQ_P3.git
Branch: `feat/p3-extraction`
Guide: `P3_GUIDE.md`

---

## 2026-10-07 — Guide and repo start

- Added `P3_GUIDE.md` as the step order for extraction work.
- Initialized this repo on `feat/p3-extraction` and pointed `origin` at the GitHub remote.
- Added `.gitignore`, `.env.example`, `requirements.txt`, and this audit file.
- Chose Python 3.12 for `.venv`. The machine default is 3.13, and PaddlePaddle wheels do not reliably support 3.13.

Status: Step 1 (environment and engine spike) is in progress. No extractor code yet.

---

## 2026-10-07 — Step 1 complete: engines read real sample values

- Created `.venv` with Python 3.12 and pinned `requirements.txt` to the versions that installed.
- Generated `sample_docs/`: `simple.pdf`, `scanned.pdf`, `table.pdf`, `equation.pdf`, `chart.pdf`, `sample.docx`, `sample.xlsx`, `sample.pptx`.
- `scripts/make_samples.py` and `scripts/spike_engines.py` use `pymupdf` (the `fitz` import is deprecated in 1.28).

Spike results, all four required engines:

| Engine | Result | Value read |
|---|---|---|
| PyMuPDF 1.28.2 | PASS | `simple.pdf` first line `Annual Financial Report 2025`, 12 words, bbox `[72.0, 60.65, 128.03, 85.38]` |
| Docling 2.135.0 | PASS | Markdown preview starts with `Annual Financial Report 2025` and the FY2025 sentence |
| PaddleOCR 3.7.0 | PASS | `Scanned revenue note total is 128.5 crore.` |
| openpyxl 3.1.5 | PASS | Sheet `Financials`, cell `B2` = `128.5` |

Two setup constraints, both recorded in the spike script:

- Docling's default pipeline tries to download a RapidOCR model from `modelscope.cn`, which timed out. The digital spike turns OCR off (`do_ocr=False`). Scanned pages stay on PaddleOCR.
- PaddlePaddle 3.3.1 on this Windows CPU crashes inside oneDNN (`ConvertPirAttribute2RuntimeAttribute`). The spike sets `enable_mkldnn=False`.

Machine for this run: CPU, no GPU. Step 1 exit check passed. Next is Step 2, the extractor interface.

- Added `.gitattributes` so PDF and Office samples stay binary. Git had warned it would rewrite line endings in those files.

---

## 2026-10-07 — Step 2 complete: extractor interface

- Added `extractors/base.py` with `Extractor.can_handle` and `Extractor.extract`.
- Added `extract(region, context) -> list[Block]` in `extractors/__init__.py`. This is the function P1 should call.
- `route="skip"` returns no blocks. Any other route with no registered extractor returns one `status="failed"` block and does not raise. An extractor that throws is caught the same way. The error code sits in `history`.
- `extractors/utils.py` builds every block through `make_block`, converts bottom-left boxes with `to_top_left`, and crops a page image with `crop_region`.
- P1 has not published `pipeline/schema.py` in this repo. `extractors/schema_stub.py` is a temporary copy of the Block contract. `extractors/schema_ref.py` imports P1's module when it exists and the stub until then. Delete the stub once the real schema is here. Do not add fields to the stub.
- Routes that return real content later: `native_text`, `ocr`, `docling_table`, `paddle_table`, `chart`, `formula`, `office`. They fail clearly until those steps land.

Check: `pytest tests/test_extractors.py` — 9 passed. Docling and PaddleOCR were not imported.

Contract for P1 and P2:

```python
extract(region, context) -> list[Block]
```

`region` needs `id`, `type`, `page`, `bbox`, `route`, `is_scanned`. `context` carries `file_path`, `format`, `page_size`, `page_image`, `words`, and an optional `docling_item`.

Next is Step 3, native text on `simple.pdf`.

---

## 2026-10-07 — Step 3 complete: native text

- Added `extractors/native_text.py` and registered it on `route="native_text"`.
- PyMuPDF words inside the region become heading and paragraph blocks. A line at 16pt or larger is a heading. Wrapped lines in the same paragraph stay one block.
- Each block has `content.text`, a four-number bbox, `page_start`, and `extractor="pymupdf"`. With no second reading, `confidence.extraction` is `0.90`.
- Docling is not called from this extractor. When `context["docling_item"]` is already present, the strings are compared. Agreement at 0.98 or above sets confidence to `0.97`. A disagreement keeps the PyMuPDF text, stores the Docling text in `history`, and sets `needs_review`.
- `simple.pdf` returns the heading `Annual Financial Report 2025` and the FY2025 paragraph. A bbox around the heading does not include the paragraph.

Check: `pytest tests/test_extractors.py` — 13 passed. Docling and PaddleOCR were not imported.

Next is Step 4, OCR on `scanned.pdf`.
