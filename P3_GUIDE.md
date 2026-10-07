# ParseAnything — Person 3 Extraction Guide

This is the working guide for **P3 only**. We follow it in order. One step is done when its exit check passes. We do not start the next step until that check is true.

ParseAnything takes a supported file and returns Markdown plus structured JSON. Every block carries its page, bounding box, extractor, confidence, risk, and verification status. When the system is unsure, it flags the block.

P3 answers one question: **what does this region actually contain?**

P2 decides where a region is and which route it should take. P3 runs the extractor for that route and returns blocks in the shared schema. P4 decides whether those blocks should be trusted. P1 connects the pipeline and writes the final files. P5 shows the result.

---

## 0. Boundaries

### You own

| Path | Role |
|---|---|
| `extractors/` | All extraction code |
| `extractors/base.py` | The shared extractor interface. This is your contract with the team. |
| `tests/test_extractors.py` | Interface and dispatcher tests |
| `tests/test_ocr.py` | OCR tests |
| `tests/test_tables.py` | Table tests |
| `tests/test_equations.py` | Equation tests |
| Git branch `feat/p3-extraction` | Your only branch. Do not push to `main`. |

### You do not own

| Path | Owner | Rule |
|---|---|---|
| `pipeline/schema.py` | P1 | Use `Block`. If a field is missing, ask P1. Do not edit the schema. |
| `pipeline/orchestrator.py` | P1 | P1 calls your `extract(region, context)`. |
| `routing/`, `assembly/` | P2 | Routing, reading order, cross-page table merge, furniture, document map. |
| `validation/` | P4 | Confidence formula, risk, arithmetic audit, repair, verification status. |
| `app/`, `provenance/`, `benchmark/` | P5 | UI, evidence viewer, benchmark dashboard. |

### You do not build

- Streamlit
- the trust engine
- a different JSON shape per extractor
- a new layout model
- handwriting, audio, video, model training, RAG chat, or legacy `.doc` / `.xls` / `.ppt`

### Priority if time runs out

Cut from the bottom.

| Tier | Your items |
|---|---|
| Must have | Digital PDF text, scanned PDF OCR, tables with real cell structure, bbox and extractor name on every block, a failed region that does not crash the document |
| Should have | DOCX, XLSX, PPTX, equations to LaTeX, simple bar charts, VLM only on a failed or ambiguous crop |
| Stretch | Chart geometry path (OpenCV bars and axis calibration) |
| Do not do | Training models, running a VLM on a whole page, claiming a format you did not test |

---

## 1. Where you sit in the pipeline

```text
FILE
  → P1 preflight + ingest          Docling + PyMuPDF page data
  → P2 profile + route             "this region is a scanned table"
  → P3 extract                     you return list[Block]
  → P2 assemble                    order, merge, normalize
  → P4 validate                    confidence, risk, audit, verify
  → P1 write JSON + Markdown
  → P5 show evidence
```

You are stage 5. You receive a region that P2 already classified. You return blocks. You do not decide reading order and you do not audit the numbers.

### What you receive

Agree this shape with P2 in the first hour. Until their model exists, use the same shape in tests.

```python
# region — produced by P2, consumed by P3
{
    "id": "r12",
    "type": "text | table | chart | equation | figure",
    "page": 4,
    "bbox": [x1, y1, x2, y2],          # page coordinates, origin top-left
    "route": "native_text | ocr | docling_table | paddle_table | chart | formula | office | skip",
    "is_scanned": False
}

# context — produced by P1, passed through the orchestrator
{
    "file_path": "sample_docs/table.pdf",
    "format": "pdf | docx | xlsx | pptx | png | jpg",
    "page_size": {"width": 612.0, "height": 792.0},
    "page_image": "<PIL image or path, rendered by PyMuPDF>",
    "words": [],                         # PyMuPDF words when a text layer exists
    "docling_item": None                 # optional Docling element for this region
}
```

Coordinate rule: one system only. **PDF points, origin top-left.** If PaddleOCR or OpenCV returns pixels or a bottom-left origin, convert inside `extractors/utils.py` before the block leaves your code.

### What you return

`extract(region, context) -> list[Block]`

Every extractor returns the same `Block` from `pipeline/schema.py`.

You fill:

| Field | What you put there |
|---|---|
| `id` | Temporary id such as `blk_r12_0`. P1 may renumber. |
| `type` | `heading`, `paragraph`, `list`, `table`, `figure`, `chart`, `equation`, `caption`, `footnote` |
| `content` | See section 4. Shape depends on type. Never a private schema. |
| `page_start`, `page_end` | Page numbers for this region |
| `bbox`, `bbox_by_page` | Source box in the shared coordinate system |
| `extractor` | Stable name: `pymupdf`, `docling`, `paddleocr`, `paddleocr_table`, `formula`, `chart`, `openpyxl`, `python-docx`, `python-pptx`, `vlm` |
| `confidence.extraction` | Your evidence score `E`, from 0 to 1 |
| `confidence.final` | Copy of `E` for now. P4 replaces it with `C = E × S × Q`. |
| `source` | File, page, bbox. For XLSX: sheet and cell range. For PPTX: slide and shape bbox. |
| `history` | One entry per engine tried: name, confidence, and a short result note |
| `flags` | Only extraction flags: `ocr_low_conf`, `formula_parse_fail`, `chart_disagreement` |
| `status` | `accepted` on success, `failed` when the extractor cannot read the region, `needs_review` only when two engines disagree |
| `reading_order` | `0`. P2 overwrites it. |
| `order_confidence` | `0.0`. P2 overwrites it. |
| `risk` | `LOW` placeholder. P4 overwrites it. |
| `confidence.structure`, `confidence.source_quality` | `0.0` unless you already measured them. P4 owns the final score. |

A failed region returns one block with `status="failed"` and a flag. It does not raise out of `extract()` and it does not stop the document. Put the error code in `history` so P1 can copy it into the document error list:

| Failure | Code |
|---|---|
| OCR produced nothing usable | `OCR_FAILED` |
| Table structure could not be built | `TABLE_FAILED` |
| Chart values could not be established | `CHART_FAILED` |
| Formula could not be parsed | `FORMULA_FAILED` |
| Two engines disagree | `EXTRACTION_CONFLICT` |

### The only function the rest of the team calls

```python
def extract(region, context) -> list[Block]:
    ...
```

Specialized functions stay inside `extractors/` and are reached through that dispatcher:

```text
region.route
    native_text   → native_text.py
    ocr           → ocr.py
    docling_table → tables.py      (digital)
    paddle_table  → tables.py      (scanned)
    chart         → charts.py
    formula       → equations.py
    office        → office.py
    skip          → []             (decorative image, P2 already decided)
```

If `route` is missing, fall back to `can_handle(region)`.

---

## 2. Tools and how they connect

Install once in step 1. Pin versions after the first successful run.

| Tool | You use it for | You do not use it for |
|---|---|---|
| Python 3.11+ | All extractor code | — |
| **PyMuPDF (`fitz`)** | Words inside a bbox, page render, crop of a region | Reading-order logic |
| **Docling** | Digital layout items, digital tables, Office conversion when native Office libs are not enough | Running it on every scanned page |
| **PaddleOCR** | Text on scanned pages and crops. Keep word text, bbox, and confidence. | Digital pages that already have a clean text layer |
| **PaddleOCR table recognition** | Scanned tables: rows, columns, spans, cell text | Cross-page merging |
| **PaddleOCR formula recognition** | Equation crop → LaTeX | Inline prose that is not marked as a formula |
| **OpenCV** | Deskew, denoise, and threshold on a scan crop before OCR. Stretch: bar and axis geometry. | A general image pipeline on digital pages |
| **Pillow** | Hold and save crops | UI rendering |
| **openpyxl** | XLSX cells, formulas, formats, merged ranges, sheet names | Vision on a spreadsheet |
| **python-docx** | DOCX headings, paragraphs, lists, tables | Page boxes. Those need a PDF conversion owned with P1. |
| **python-pptx** | Slide title, text frames, tables, pictures, native chart series, shape bbox | Vision when the chart already exposes its data |
| **Pydantic** | Build `Block` objects. Import P1's models. | A second model file |
| **pytest** | One test file per extractor | — |
| **VLM** (optional, key in `.env`) | One cropped region after a specialist fails or two readings disagree | Whole documents, ordinary paragraphs |

PaddleOCR and PP-Structure are shared with P2. P2 uses layout and reading-order signals. You use recognition: OCR text, table cells, formulas. Do not fork a second copy of the model-loading code if P2 already has one. Put your calls in `extractors/`.

### Inside one region

```text
region + context
    → crop the bbox from the page image          utils.py + PyMuPDF / Pillow
    → preprocess only if scanned                 OpenCV
    → run the one engine named by region.route   Docling / PaddleOCR / Office / VLM
    → if that engine fails or confidence is low  escalate once (section 3)
    → pack content into the type shape           section 4
    → return list[Block]
```

Cheap engine first. Escalate once. Record both attempts in `history`. Never drop the first reading when the second disagrees.

---

## 3. Escalation rules

P2 picks the first engine. You escalate only for that region, and only one step.

| Region | First engine | Escalate when | Second engine |
|---|---|---|---|
| Digital text | PyMuPDF words inside the bbox, cross-read with Docling text when it is present | The two texts disagree badly | Keep both in `history`, set `needs_review`. Do not OCR a clean digital page. |
| Scanned text | PaddleOCR on the crop | Mean word confidence is low, or the crop is empty | VLM on the same crop |
| Digital table | Docling structure, cells filled from PyMuPDF words | Structure is broken (ragged rows, missing header) | PaddleOCR table recognition |
| Scanned table | PaddleOCR table recognition on the preprocessed crop | A cell is empty or below 0.90 OCR confidence | Leave the cell raw. P4 may ask you later for a VLM read of that cell crop. |
| Equation | Formula recognizer → LaTeX | LaTeX does not parse | VLM crop → LaTeX. If they still disagree, `needs_review` and store both strings. |
| Chart | Caption plus one value path (model or native PPTX series) | Values are missing or the two paths disagree by more than about 3% of the axis range | Store both candidate sets, status `needs_review`. Do not pick one. |
| Decorative image | — | P2 route is `skip` | Return `[]` |
| XLSX / PPTX chart | Native cell or series data | Native data is missing | Then, and only then, a vision path |

VLM input is a crop, plus a short instruction for the type (`table cell`, `equation to LaTeX`, `bar chart to JSON`). Count every call. P4 and P5 need that count for the cost story. Do not send the full page.

---

## 4. Content shapes

These are the `content` objects inside `Block`. P1's schema keeps `content` as `Any`. The shapes below are the contract you, P2, P4, and P5 share. If a field is not in `schema.py` and you need it on the block itself, ask P1.

### Paragraph, heading, list, caption, footnote

```json
{
  "text": "Revenue grew during FY2025.",
  "level": 2
}
```

`level` is only for headings. Keep the original string. Do not normalize currency here. That parser lives in P2 `assembly/normalize.py`. You may attach an optional `numbers` list of raw numeric strings you saw, so P4 can find them.

### Table

Do not flatten a table into a paragraph.

```json
{
  "header_rows": [["", "2024", "2025"], ["", "Revenue", "Revenue"]],
  "column_paths": ["label", "2024 > Revenue", "2025 > Revenue"],
  "rows": [
    {
      "cells": [
        {
          "text": "128.5",
          "value": 128.5,
          "unit": null,
          "scale": null,
          "row_span": 1,
          "col_span": 1,
          "bbox": [410, 320, 490, 350],
          "confidence": 0.94,
          "repaired": false
        }
      ]
    }
  ],
  "records": []
}
```

Rules:

- Keep spans. A merged cell is one cell with `row_span` or `col_span`, not duplicated text.
- Multi-row headers stay as `header_rows`. `column_paths` is the flattened path, for example `Revenue > 2025`.
- Each cell keeps its own bbox, raw `text`, and OCR or text-layer `confidence`.
- `value` is a first parse when the cell is obviously numeric. Leave `unit` and `scale` null if you are not sure. P2 attaches crore, million, and percent from captions and headers.
- `repaired` stays `false`. P4 is the only person who may set it.
- `records` is an optional flat view, one dict per body row, for later LLM use. The grid is the source of truth.

### Chart

Hackathon scope: bar charts, simple line charts, charts that have a caption or a native data series. Anything else returns a figure block with the crop reference and `status="needs_review"`.

```json
{
  "chart_type": "bar",
  "title": "Revenue Growth",
  "x_axis": {"label": "Year", "ticks": ["2023", "2024", "2025"]},
  "y_axis": {"label": "Revenue", "unit": "INR crore"},
  "series": [
    {
      "name": "Revenue",
      "points": [
        {"label": "2023", "value": 92.4},
        {"label": "2024", "value": 110.7}
      ],
      "method": "pptx_native"
    }
  ],
  "agreement": true,
  "candidates": []
}
```

If path A and path B disagree, `agreement` is `false`, both sets go in `candidates`, and the block status is `needs_review`.

### Equation

```json
{
  "latex": "E = mc^2",
  "parsed": true,
  "candidates": []
}
```

Inline math inside a paragraph stays in the paragraph text unless the region was routed as `formula`.

### Office provenance

| Format | `source` | `bbox` |
|---|---|---|
| XLSX | `sheet` + `cell_range` | Empty or omitted. There is no page. |
| PPTX | `slide` + shape bbox | Shape box on the slide |
| DOCX | Heading level, paragraph, table | Page and bbox only after a PDF conversion. Record that conversion in `history`. |

---

## 5. Files you will create

Match the GitHub layout. Do not invent the `engines/` layout from the older plan.

```text
extractors/
  __init__.py          # extract(region, context) dispatcher
  base.py              # Extractor ABC
  native_text.py       # PyMuPDF + Docling text
  ocr.py               # PaddleOCR
  tables.py            # Docling tables + PaddleOCR tables
  charts.py            # chart content, native series first
  equations.py         # formula → LaTeX
  office.py            # openpyxl, python-docx, python-pptx
  vlm.py               # crop fallback
  utils.py             # crop, coordinate convert, block builder, confidence helper

tests/
  test_extractors.py
  test_ocr.py
  test_tables.py
  test_equations.py

sample_docs/           # shared, do not replace other people's files
  simple.pdf
  scanned.pdf
  table.pdf
  chart.pdf
  equation.pdf
  sample.docx
  sample.xlsx
  sample.pptx
```

`utils.py` should expose three helpers used by every extractor:

- `crop_region(page_image, bbox, page_size) -> image`
- `to_top_left(bbox, page_height, origin) -> bbox`
- `make_block(...) -> Block` so nobody hand-builds a dict with a missing field

---

## 6. Steps we follow

Each step has a goal, the tools, the integration point, and an exit check. We work in this chat one step at a time.

### Step 1 — Environment and engine spike

**Goal.** Prove the libraries run on this Windows machine before writing architecture.

**Do.**

1. Create branch `feat/p3-extraction`.
2. Create `.venv` with Python 3.11+.
3. Install, then pin: `pydantic`, `pymupdf`, `docling`, `paddleocr`, `paddlepaddle`, `opencv-python`, `pillow`, `openpyxl`, `python-docx`, `python-pptx`, `pytest`, `numpy`.
4. Put any VLM key in `.env`. Do not commit it.
5. Run four one-page spikes and save the raw printout:
   - PyMuPDF: word count and one bbox from `sample_docs/simple.pdf`
   - Docling: one text item and one table from a digital PDF
   - PaddleOCR: one text line plus confidence from `sample_docs/scanned.pdf`
   - openpyxl: one cell from `sample_docs/sample.xlsx`

**Integration.** None yet. This only proves the tools import.

**Exit check.** Each of the four spikes prints a real value. If PaddleOCR or Docling fails to install, stop and fix that before any extractor code. Note the demo machine: CPU or GPU. That choice changes timeouts later.

**Sample files.** If `sample_docs/` does not exist yet, add the smallest file that proves each spike. One digital PDF page, one scanned page, one xlsx sheet is enough for this step.

---

### Step 2 — Interface, dispatcher, and block builder

**Goal.** A fake region goes in and a valid `Block` comes out, with no real engine yet.

**Files.** `extractors/base.py`, `extractors/__init__.py`, `extractors/utils.py`, `tests/test_extractors.py`.

**Tools.** Python, Pydantic, pytest. Import `Block` from `pipeline/schema.py`. If P1 has not landed the schema, copy the contract from section 1 into a local stub and switch the import the moment `schema.py` exists. Delete the stub. Do not keep two schemas.

**Interface.**

```python
class Extractor(ABC):
    name: str

    @abstractmethod
    def can_handle(self, region) -> bool: ...

    @abstractmethod
    def extract(self, region, context) -> list[Block]: ...
```

**Dispatcher.**

```python
def extract(region, context) -> list[Block]:
    # look up region["route"]
    # on exception: return one failed block, do not raise
```

**Tests.**

- `route="skip"` returns `[]`
- an unknown route returns a failed block, not an exception
- `make_block` always sets `extractor`, `bbox`, `page_start`, and `confidence.extraction`

**Integration.** Tell P1 and P2 the function signature: `extract(region, context) -> list[Block]`. This is the hour-1 contract.

**Exit check.** `pytest tests/test_extractors.py` passes without Docling or PaddleOCR.

---

### Step 3 — Native text

**Goal.** A clean digital PDF region becomes paragraph and heading blocks with real boxes.

**File.** `extractors/native_text.py`

**Tools.** PyMuPDF first. Docling text as the cross-read when `context["docling_item"]` or a Docling document is available.

**Flow.**

```text
region bbox
  → PyMuPDF words whose boxes sit inside the region
  → group words into lines, then a paragraph or heading
  → if Docling text exists, compare the strings
  → Block(type="paragraph" or "heading")
```

**Confidence `E`.** If the two strings are almost the same, `E = 0.97`. If only PyMuPDF ran, `E = 0.90`. If they disagree, keep PyMuPDF text, store Docling text in `history`, set `status="needs_review"`, and set `E` to the similarity.

**Integration.** This is your piece of Integration 1 (about hour 6): file in, basic blocks out, JSON out. P1 calls `extract` on regions whose route is `native_text`. You can test alone by building a region that covers the whole page.

**Exit check.** `simple.pdf` returns at least one block whose `content.text` matches text you can see, and whose bbox sits on the correct page. A test in `tests/test_extractors.py` checks the text and that bbox has four numbers.

---

### Step 4 — OCR

**Goal.** A scanned page or crop returns text, word boxes, and a real confidence.

**File.** `extractors/ocr.py`

**Tools.** PyMuPDF or Pillow for the crop. OpenCV only when the page is skewed, blurry, or low contrast. PaddleOCR for detection and recognition.

**Flow.**

```text
page image → crop bbox → optional deskew/denoise → PaddleOCR
  → lines of text + word bbox + word confidence
  → Block
```

**Confidence `E`.** Mean word confidence weighted by character count. If that mean is under 0.70, add flag `ocr_low_conf`. Do not call the VLM in this step. The flag is enough for P4 to escalate later.

**Keep the original crop path in `history`** so P5 can show evidence. Do not overwrite the raw image with the thresholded image.

**Integration.** Integration 2 (about hour 10–12). P2 sets `route="ocr"` when `is_scanned` is true. You do not profile the page yourself.

**Exit check.** `tests/test_ocr.py` on `scanned.pdf` asserts non-empty text, a bbox, and `0 <= confidence.extraction <= 1`. A blank crop returns a failed block with `OCR_FAILED`, and the test process does not crash.

---

### Step 5 — Tables

**Goal.** A table region becomes one `table` block with cells, spans, and per-cell boxes. This is the must-have feature.

**File.** `extractors/tables.py`

**Tools.**

- Digital: Docling table structure, cells filled by PyMuPDF words that fall inside each cell box.
- Scanned: PaddleOCR table recognition on the preprocessed crop, then OCR text per cell.

**Flow.**

```text
table region
  → structure: rows, columns, spans, header band
  → fill each cell (text layer or OCR)
  → content shape from section 4
  → Block(type="table", extractor="docling_table" or "paddleocr_table")
```

Header band: top rows that are labels (non-numeric, or a ruled line above the numbers). Row labels: non-numeric cells in the first column. Keep indentation in the raw text if the source has it.

**You do not merge a table that continues on the next page.** Return two table blocks. P2 `assembly/table_merge.py` merges them. Give each block an accurate bbox so their merge score can use column positions.

**You do not run arithmetic or repair.** Set `repaired: false` on every cell. Low-confidence cells stay as read, with their confidence, so P4 can audit them.

**Integration.** Same checkpoint as OCR. P4 reads `rows[].cells[].text`, `value`, `bbox`, and `confidence`. P5 highlights a cell from `bbox`.

**Exit check.** `tests/test_tables.py` on `table.pdf` checks:

- block type is `table`
- every row has the same effective column count after spans
- at least one cell has a four-number bbox
- a known cell string from the sample appears in `text`
- the block is not a single flattened paragraph

---

### Step 6 — Office files

**Goal.** DOCX, XLSX, and PPTX return blocks without a vision model.

**File.** `extractors/office.py`

**Tools.** `python-docx`, `openpyxl`, `python-pptx`. Docling only if a native reader cannot see a table.

**What to extract.**

| Format | Blocks | Provenance |
|---|---|---|
| XLSX | One table block per sheet that has values. Cell value, formula, number format, merged range. | `sheet` + `cell_range` |
| PPTX | Per slide: title, text frames, tables, pictures. Charts use the embedded data series. | slide number + shape bbox |
| DOCX | Heading level, paragraphs, lists, tables from XML. | No page bbox unless P1 has converted to PDF |

PPTX chart data is exact. Use it before `charts.py` vision.

**Integration.** P1 routes Office files to `route="office"` or calls `office.extract_document(path)` once per file, because these files are not page regions. Agree that function name with P1 in this step. Return the same `Block` list.

**Exit check.** One assertion per format: an XLSX cell value, a DOCX heading string, a PPTX title or chart series number. Each matches the file, not a guess.

---

### Step 7 — Equations

**Goal.** An equation region becomes LaTeX that parses.

**File.** `extractors/equations.py`

**Tools.** PaddleOCR formula recognition. A small LaTeX parse check (the string must at least be syntactically plausible; a real render check if the library is already installed). VLM only after the parse check fails. That VLM call can be a stub until step 9, but the failure flag must exist now.

**Flow.**

```text
equation crop → formula recognizer → LaTeX → parse check
  → parsed true: status accepted
  → parsed false: flag formula_parse_fail, status needs_review
```

**Integration.** Integration 3 (about hour 16–18). P5 shows the LaTeX. P4 uses `parsed` as the structure signal.

**Exit check.** `tests/test_equations.py` on `equation.pdf` expects a non-empty `latex` string and a boolean `parsed`. A garbage crop sets `FORMULA_FAILED` or `formula_parse_fail` and does not raise.

---

### Step 8 — Charts

**Goal.** A simple bar chart, or a PPTX chart, becomes a values table. Uncertain charts are flagged, not invented.

**File.** `extractors/charts.py`

**Tools.** Native series from `python-pptx` when the source is a slide. For PDF figures: one model or VLM path on the crop, with the caption in the prompt. OpenCV geometry is stretch and comes last.

**Flow.**

```text
chart region
  → if native series exists, use it (method = pptx_native)
  → else model/VLM JSON: type, title, axes, series
  → optional geometry path for a simple bar chart
  → compare values
  → agreement true, or needs_review with both candidates
```

A figure with no caption, no "Figure N" reference, and no native series is not your problem to invent. If P2 did not route it as `chart`, return nothing.

**Integration.** P4 compares series values with prose and tables. You only store the numbers and whether your own two paths agreed.

**Exit check.** On `chart.pdf` or the PPTX sample: `chart_type`, at least two points, and `agreement` is a boolean. If you only have one path, say so in `series[].method` and leave `agreement` null rather than marking it verified.

---

### Step 9 — VLM fallback

**Goal.** One function that reads a crop and returns text for a single hard region.

**File.** `extractors/vlm.py`

**Tools.** The VLM the team picked in hour 1. Credentials from `.env` only.

**Call it from the other extractors only at the escalation points in section 3.** The function signature:

```python
def read_crop(image, task: str, hint: str = "") -> dict:
    # task in {"ocr", "table_cell", "latex", "chart"}
    # returns {"text" or "json": ..., "confidence": float <= 0.85}
```

Cap VLM self-reported confidence at **0.85** unless a second engine agrees. Append every call to `history` with the task name. If the key is missing, return a failed result and flag `vlm_unavailable`. Do not crash the document.

**Integration.** P4 may also call a second read for verification. They should call this function rather than a private client, so the cost counter stays in one place. Expose `vlm_call_count()` for P5.

**Exit check.** A unit test with the client mocked checks: crop in, structured dict out, confidence capped, call count increased by one. A live call on one equation or one blurry cell is enough as a manual spike. Do not add a live call to the default test run.

---

### Step 10 — Hand off and freeze

**Goal.** P1 can call you without reading your internals.

**Do.**

1. Confirm `extract(region, context)` is what `pipeline/orchestrator.py` imports.
2. Run the four test modules on the sample set.
3. Write down, in a short comment at the top of `extractors/__init__.py`, the route names you actually support.
4. List anything you did not test. Untested routes must fail clearly, not return empty success.
5. After the team freeze (about hour 20, or hour 29 on the full schedule), only bug fixes, speed, and sample accuracy. No new extractors.

**Exit check.** Definition of done:

```text
[ ] native text works on simple.pdf
[ ] OCR works on scanned.pdf
[ ] tables work on table.pdf, with cell bboxes
[ ] formulas work on equation.pdf, or the failure is flagged
[ ] charts work inside the declared scope, or the limit is written down
[ ] DOCX, XLSX, and PPTX work inside the declared scope
[ ] a fallback path exists and is not used on every page
[ ] a failed region does not crash extraction
[ ] every block uses Block, with extractor name and bbox or sheet/cell provenance
```

---

## 7. How you plug into each person

| Person | They give you | You give them | When |
|---|---|---|---|
| P1 | `Block` in `schema.py`, page images, words, the orchestrator call | `extract(region, context) -> list[Block]`, plus `office.extract_document(path)` | Signature in step 2. Real native text by step 3 so hour-6 integration works. |
| P2 | `region` with `type`, `page`, `bbox`, `route`, `is_scanned` | Blocks whose bbox and cell boxes use top-left page coordinates | Agree the region dict in step 2. Do not wait for their reading-order code. |
| P4 | Nothing you must wait for | Cell text, cell confidence, equation `parsed`, chart `agreement`, `history` of every engine | They can score mock blocks before you finish. Your real confidences replace the mocks. |
| P5 | Nothing | Stable `extractor` names, bboxes, and failed-block flags so the evidence panel has something to draw | They build the UI on `mock_output.json` first. |

You can build every step against `sample_docs/` and a hand-made `region` dict. You do not wait for the pipeline.

### Checkpoints to show up for

| Checkpoint | You must already have |
|---|---|
| Hour 6 | Step 3 native text on a digital PDF, returning real blocks |
| Hour 10–12 | Step 4 OCR and step 5 tables |
| Hour 16–18 | Step 7 equations and step 8 charts at least on one sample each, plus Office if the demo set includes them |
| Freeze | Step 10 checklist. No new routes after this. |

---

## 8. Test samples

| File | Step that needs it | Assert |
|---|---|---|
| `sample_docs/simple.pdf` | 3 | A visible sentence and a bbox |
| `sample_docs/scanned.pdf` | 4 | Non-empty OCR text and a confidence |
| `sample_docs/table.pdf` | 5 | Headers, one known cell, cell bbox |
| `sample_docs/equation.pdf` | 7 | LaTeX string and `parsed` |
| `sample_docs/chart.pdf` | 8 | Chart type and points, or an honest `needs_review` |
| `sample_docs/sample.docx` | 6 | One heading |
| `sample_docs/sample.xlsx` | 6 | One cell value and a cell range |
| `sample_docs/sample.pptx` | 6 and 8 | One title, and native chart values if the file has a chart |

Add `tests/test_equations.py` even though the folder list in the short ownership table sometimes omits it. The GitHub structure includes it, and equations are yours.

---

## 9. Working rules while we build

1. We implement the steps in section 6 in order. We do not open charts before tables.
2. Each extractor returns `Block`. If a test has to special-case one extractor's dict, the extractor is wrong.
3. Schema changes go through P1. We keep a note of the request instead of editing `pipeline/schema.py`.
4. One route, one engine, then at most one escalation.
5. Original text stays in `content`. Normalized units and repaired digits are not applied here.
6. We claim a format only after its sample test passes.

Next action when we start coding: **Step 1, environment and engine spike.**
