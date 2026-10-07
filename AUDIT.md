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
