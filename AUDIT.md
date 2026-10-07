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

---

## 2026-10-08 — Step 4 complete: OCR

- Added `extractors/ocr.py` and registered it on `route="ocr"`.
- The page is rendered, the region is cropped, and the raw crop is saved under `outputs/crops/`. That path is stored in `history`. A cleaned copy is sent to PaddleOCR only when the crop is blurry, low-contrast, or skewed. The raw file is not overwritten.
- PaddleOCR runs with `enable_mkldnn=False`, the same Windows CPU workaround as the Step 1 spike. Word boxes are requested. Line confidence is the character-weighted mean. Below `0.70` the block gets `ocr_low_conf`. No VLM call.
- `scanned.pdf` returns one paragraph block whose text includes `128.5` and `crore`, with a four-number bbox and a confidence between 0 and 1.
- A blank page returns one failed block with `OCR_FAILED` and does not crash.
- A missing route no longer sends every scanned region through OCR ahead of another registered handler. OCR takes `route="ocr"`, or a scanned text region when no route was set.

Check: `pytest tests/test_extractors.py tests/test_ocr.py` — 15 passed.

Next is Step 5, tables on `table.pdf`.

---

## 2026-10-08 — Step 5 complete: tables

- Added `extractors/tables.py` and registered `docling_table` and `paddle_table`.
- A ruled digital table is read from the PDF vector grid. Each cell is filled with the PyMuPDF words inside that rectangle. `table.pdf` returns one `table` block, not a paragraph. The header is `Year`, `Revenue`, `EBITDA`. The cell `128.5` keeps its own bbox, numeric value, and `repaired: false`.
- Every body row has the same column count after spans. A colspan in the header still lines up with the body.
- When a digital page has no ruled grid, the same route falls back to Docling with OCR off and refills each cell from PyMuPDF words. That path was not needed for `table.pdf`.
- `paddle_table` calls PaddleOCR table recognition on the crop and parses the HTML plus cell boxes. It is not run by the default test, so it does not download the table models until a scanned table is sent.
- Nothing here merges a table onto the next page, and nothing repairs a digit.

Check: `pytest tests/test_tables.py tests/test_extractors.py` — 16 passed.

Next is Step 6, Office files.

---

## 2026-10-08 — Step 6 complete: Office files

- Added `extractors/office.py`. P1 can call `extract_document(path)` for a whole file, or `extract(region, context)` with `route="office"`.
- XLSX uses openpyxl. `sample.xlsx` returns one table block for sheet `Financials`, range including `B2`, cell text `128.5`, value `128.5`. There is no page. Provenance is `sheet` plus `cell_range`. Formulas and number formats are kept when a cell has them. Merged cells become spans.
- DOCX uses python-docx. The sample heading is `Annual Financial Report 2025` at level 1, plus the FY2025 paragraph. No page bbox, because Word does not have one until a PDF conversion.
- PPTX uses python-pptx. The slide title is `Revenue Growth`. The chart series is the embedded data, method `pptx_native`, including the point `128.5`. Agreement is left unset because a second chart path has not run. Shape boxes are in slide points.
- No vision model is used.

Check: `pytest tests/test_office.py tests/test_tables.py tests/test_extractors.py` — 20 passed.

Next is Step 7, equations on `equation.pdf`.

---

## 2026-10-08 — Step 7 complete: equations

- Added `extractors/equations.py` and registered `route="formula"`.
- The crop goes to PaddleOCR formula recognition (`PP-FormulaNet_plus-M`), with oneDNN turned off. A blank crop is not sent to the model.
- The LaTeX string is checked with pylatexenc. `parsed: true` keeps the block accepted. A string that does not parse sets `formula_parse_fail`, status `needs_review`, and a history note that the VLM fallback is not available yet.
- On `equation.pdf` the text layer is `E = mc^2`, stored as `E = mc^{2}`, and `parsed` is true. The formula model returned `E=m c\cdot2`. Both strings are kept. Status is `needs_review` with `EXTRACTION_CONFLICT`, because the two readings do not match. The text layer stays in `latex`.
- A blank page returns one failed block with `FORMULA_FAILED` and does not raise.
- Formula recognition needed the PaddleX OCR extra packages that were not already installed: einops, ftfy, premailer, scikit-learn, sentencepiece, tiktoken. Those are pinned in `requirements.txt`, along with pylatexenc.

Check: `pytest tests/test_extractors.py tests/test_equations.py tests/test_office.py tests/test_tables.py` — 23 passed.

Next is Step 8, charts.

---

## 2026-10-08 — Step 8 complete: charts

- Added `extractors/charts.py` and registered `route="chart"`. The extractor only runs when P2 sets that route.
- A PPTX sent on this route uses the embedded series, method `pptx_native`. `sample.pptx` still has the Revenue points, including `128.5`. `agreement` stays null because a second path has not run.
- `chart.pdf` is a drawn bar chart. The bars are the filled rectangles that share a baseline. Each value is the number printed above that bar, and each tick is the label printed below it. The series is `Revenue` from the caption `Figure 1 Revenue`. Points are `2023`/`92.4`, `2024`/`110.7`, `2025`/`128.5`. Method is `geometry`. `agreement` is null. The unit is left empty.
- A caption with no bars becomes a `figure` block, status `needs_review`, with the caption text and a crop path. No series is invented. A blank page returns `CHART_FAILED` and does not raise.
- Pixel measurement with OpenCV is not used. This sample's values are already printed on the bars.

Check: `pytest tests/test_extractors.py tests/test_charts.py tests/test_equations.py tests/test_office.py tests/test_tables.py` — 27 passed.

Next is Step 9, the VLM fallback.

---

## 2026-10-08 — Step 9 complete: VLM fallback

- Added `extractors/vlm.py`. `read_crop(image, task, hint)` sends one crop to an OpenAI-compatible chat endpoint. The task is `ocr`, `table_cell`, `latex`, or `chart`. `vlm_call_count()` is the count P5 can show. Both are exported from `extractors`.
- The key, model, and base URL come from the environment or `.env`. A missing key returns `vlm_unavailable` and does not raise or increment the count. A client error is returned on the result and does not raise. Reported confidence is capped at 0.85 unless the caller passes `agreed=True`.
- Escalation only: empty or low-confidence OCR, an equation whose LaTeX does not parse, and a chart caption with no readable bars. Tables are left raw. A successful OCR read and a parsed equation do not call the VLM.
- No live call was made. There is no key in this environment. The default test mocks the client.

Check: `pytest tests/test_vlm.py tests/test_extractors.py tests/test_charts.py tests/test_equations.py tests/test_office.py tests/test_tables.py` — 32 passed. `pytest tests/test_ocr.py` — 2 passed.

Next is Step 10, handoff and freeze.

---

## 2026-10-08 — Step 10 complete: handoff

P1 imports `extract(region, context)` from `extractors`. This repo has no `pipeline/orchestrator.py`. Office files can also use `extract_document(path)`. The route list at the top of `extractors/__init__.py` is frozen: `skip`, `native_text`, `ocr`, `docling_table`, `paddle_table`, `office`, `formula`, `chart`. An unknown route returns one failed block.

Checklist:

- Native text works on `simple.pdf`.
- OCR works on `scanned.pdf`.
- Tables work on `table.pdf`, with a bbox on each cell.
- `equation.pdf` returns LaTeX, `parsed` is true, and the formula-model disagreement is flagged.
- Charts: bar values on `chart.pdf`, native series on `sample.pptx`. Line charts and charts without printed values are not read.
- DOCX, XLSX, and PPTX work on the samples.
- The VLM fallback exists and is not called on a clean page.
- A failed region does not raise.
- Blocks are built with `Block`, an extractor name, and a bbox or sheet/cell provenance.

Not claimed:

- The live `paddle_table` model was not run. A failure returns `TABLE_FAILED`.
- Docling's table fallback was not needed for `table.pdf` and was not run.
- No live VLM call. A missing key returns `vlm_unavailable`.
- `pipeline/schema.py` is not in this repo. Blocks use the local stub until P1's schema arrives.

Check: `pytest tests/test_extractors.py tests/test_ocr.py tests/test_tables.py tests/test_equations.py tests/test_office.py tests/test_charts.py tests/test_vlm.py` — 34 passed.

No new extractors after this.

---

## 2026-10-08 — Integration guide for P1 and P2

- Added `INTEGRATION_P1_P2.md`. It is the handoff for the frozen branch.
- P1 gets the orchestrator calls: `extract(region, context)` for PDF regions, `extract_document(path)` for DOCX, XLSX, and PPTX, plus how to swap in `pipeline/schema.py`.
- P2 gets the region dict, the route table, coordinate rules, and what to fill after extraction (`reading_order`, units).
- The shared section lists content shapes, failure codes, and the paths that were not run.

---

## 2026-10-08 — P1 and P2 wired to P3

- Brought P1's `pipeline/`, `output/`, and `cli.py`, and P2's `routing/` and `assembly/`, into this repo from the Person-2 tree.
- `parse_document` on a PDF runs P2, then `extract` for each region. Office files call `extract_document` and skip layout.
- P2 route names are mapped in `pipeline/p3_bridge.py`: `native` to `native_text`, `table` to `docling_table` or `paddle_table`, `equation` to `formula`, `figure` to `skip`, and `vlm` back to the text route. Reading order from P2 is written onto the blocks after extraction, then P2 assembly runs.
- The markdown writer reads `content["text"]`, table rows, and `content["latex"]`.
- Layout detection uses `enable_mkldnn=False`. Docling is imported only when an Office file goes through ingestion.
- `simple.pdf`, `sample.docx`, and `sample.xlsx` pass through `parse_document`.

Check: the wired pipeline plus the extractor, schema, and office tests passed. One collection test failed because Docling was imported at startup. That import is now lazy, and `pytest tests/test_extractors.py tests/test_schema.py tests/test_pipeline.py tests/test_failures.py tests/test_office.py` passed 54.
