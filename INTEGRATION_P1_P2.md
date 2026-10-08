# Integrating P3 extraction

The call is now inside this repo. `parse_document(path)` runs P2 on a PDF, maps each region onto a P3 route, calls `extract`, then runs P2 assembly. A DOCX, XLSX, or PPTX skips layout and calls `extract_document(path)`. P2 route names `native`, `table`, `equation`, and `vlm` are translated before they reach `extract`. `figure` stays `figure` and returns a review block. `skip` still returns nothing.



P3 is frozen on branch `feat/p3-extraction` in `https://github.com/Bhavya-Shri/ParseAnything_DQ_P3.git` (commit `d10fb0c`).

P3 reads one region and returns blocks. It does not build the document, choose reading order, repair numbers, or draw the UI.

| Person | Owns | Calls |
|---|---|---|
| P1 | Ingest, `pipeline/schema.py`, `pipeline/orchestrator.py`, final JSON and Markdown | `extract(region, context)` and `extract_document(path)` |
| P2 | Regions, routes, reading order, units such as crore and percent | Produces the `region` dict. Reads `reading_order` back after extraction. |
| P3 | The extractors in this repo | Already done. Do not add routes here. |

Python is 3.12. From the repo root:

```text
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest tests -q
```

The last full run was 34 passed. The first OCR or formula call downloads Paddle models into the user cache. On this Windows machine, oneDNN is already turned off inside the extractors.

---

## Shared contract

Both of you use this. Do not invent a second block type.

### What P1 passes in

```python
from extractors import extract, extract_document

blocks = extract(region, context)
```

`region` comes from P2. `context` comes from P1.

```python
region = {
    "id": "r12",
    "type": "text",          # text, table, chart, equation, figure, heading, paragraph
    "page": 1,               # 1-based. Office files do not use this.
    "bbox": [x1, y1, x2, y2],  # PDF points. Origin is the top-left of the page.
    "route": "native_text",
    "is_scanned": False,
}

context = {
    "file_path": "sample_docs/table.pdf",
    "format": "pdf",         # pdf, docx, xlsx, pptx, png, jpg
    "page_size": {"width": 612.0, "height": 792.0},   # optional
    "page_image": None,      # optional PIL image or image path for this page
    "words": [],             # optional; P3 reads the PDF itself when this is empty
    "docling_item": None,    # optional text for a digital-text cross-read
}
```

`extract` returns `list[Block]`. A bad region returns one block with `status="failed"`. It does not raise, and it does not stop the rest of the document.

`route="skip"` is the one case that returns `[]`. Use it for a decorative image P2 has already rejected.

If `route` is missing, P3 tries `can_handle`. That fallback is narrow. P2 should set `route` on every region.

### What you get back

`content` is `Any`. The shape depends on `type`. Every other field is the same.

| Field | Who writes it | Value from P3 |
|---|---|---|
| `id` | P3, temporary | `blk_<region id>_<index>`. P1 may renumber. |
| `type` | P3 | `heading`, `paragraph`, `list`, `table`, `figure`, `chart`, `equation` |
| `content` | P3 | See the shapes below. |
| `page_start` | P3 | Region page. `0` for XLSX and DOCX. Slide number for PPTX. |
| `page_end` | P3, then P2 | Same as `page_start` on a single page. P2 changes it when a table is merged onto a later page. |
| `bbox` | P3 | Four numbers, top-left origin. `[0,0,0,0]` when there is no page. |
| `bbox_by_page` | P3, then P2 | `{ "<page>": bbox }` when a page exists, otherwise `{}`. P2 adds later pages on a merged table. |
| `reading_order` | P2 | `extract()` leaves `0`. `parse_document` copies the region order. |
| `order_confidence` | P2 | `extract()` leaves `0.0`. `parse_document` copies `region.metadata["order_confidence"]`. Office files get `1.0` because the file order is native. |
| `links.layout` | P2, copied by the bridge | Header, footer, column, scan flag, route, and bbox warnings. Office uses `source="office"`. |
| `links.table_merge` | P2 | `merged`, `merge_confidence`, `merge_reasons`, `table_continuation`. `merged` is false until a continuation is merged. |
| `region` | P3 | The region id that produced the block. |
| `extractor` | P3 | `pymupdf`, `paddleocr`, `paddleocr_table`, `docling`, `formula`, `chart`, `vlm`, `openpyxl`, `python-docx`, `python-pptx` |
| `confidence.extraction` | P3 | Evidence score from 0 to 1. |
| `confidence.final` | P4 | Copy of `extraction` for now. P4 replaces it with `C = E × S × Q`. |
| `confidence.structure`, `confidence.source_quality` | P4 | `0.0`. |
| `risk` | P4 | `"LOW"` placeholder. |
| `status` | P3 | `accepted`, `needs_review`, or `failed`. |
| `flags` | P3 | `ocr_low_conf`, `formula_parse_fail`, `vlm_unavailable`, or the error code in lowercase. |
| `history` | P3 | One dict per engine: `engine`, `confidence`, `note`. Failures also have `error_code`. |
| `source.file` | P3 | Path that was read. |
| `source.page` | P3 | Page, or `None` for XLSX and DOCX. |
| `source.sheet`, `source.cell_range` | P3 | XLSX only. |
| `source.slide` | P3 | PPTX only. |

Serialize with `block.model_dump()`.

### Content shapes

Paragraph, list, caption. Headings add `level`.

```json
{ "text": "The company delivered strong financial performance during FY2025.", "level": 1 }
```

OCR paragraphs also include `lines`: each line has `text`, `bbox`, `confidence`, and `words`.

Table. Do not flatten this into a paragraph. `repaired` stays false. `unit` and `scale` stay null. P2 fills units from captions and headers.

```json
{
  "header_rows": [["Year", "Revenue", "EBITDA"]],
  "column_paths": ["Year", "Revenue", "EBITDA"],
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
          "bbox": [0, 0, 0, 0],
          "confidence": 0.95,
          "repaired": false
        }
      ]
    }
  ],
  "records": []
}
```

`records` is a flat view of the body. The grid is the source of truth. A merged cell is one cell with `row_span` or `col_span`.

Chart. `agreement` is `null` when only one path ran. Do not treat null as verified.

```json
{
  "chart_type": "bar",
  "title": "Figure 1 Revenue",
  "x_axis": {"label": null, "ticks": ["2023", "2024", "2025"]},
  "y_axis": {"label": "Revenue", "unit": null},
  "series": [
    {
      "name": "Revenue",
      "points": [
        {"label": "2023", "value": 92.4},
        {"label": "2024", "value": 110.7},
        {"label": "2025", "value": 128.5}
      ],
      "method": "geometry"
    }
  ],
  "agreement": null,
  "candidates": []
}
```

PPTX charts use `method` `pptx_native` instead of `geometry`.

Equation.

```json
{ "latex": "E = mc^{2}", "parsed": true, "candidates": [] }
```

On `equation.pdf` the text layer parses, and the formula model returned a different string. That block is `needs_review`, with `EXTRACTION_CONFLICT` in `history` and the other string in `candidates`.

### Failure codes

Read `history[0]["error_code"]` when `status` is `failed`.

| Code | Meaning |
|---|---|
| `OCR_FAILED` | The crop produced no usable text, and the VLM did not recover it. |
| `TABLE_FAILED` | No grid could be built. |
| `CHART_FAILED` | No values could be read. |
| `FORMULA_FAILED` | No formula text at all. |
| `EXTRACTION_CONFLICT` | Two engines disagreed. Status is `needs_review`, not `failed`. The first reading is kept. |
| `INTERNAL_ERROR` | Unknown route, missing file, or an unexpected exception. |

### Routes

| `route` | Use it when | Sample that passed |
|---|---|---|
| `native_text` | Digital PDF text. Not scanned. | `sample_docs/simple.pdf` |
| `ocr` | Scanned page or a crop with no text layer. | `sample_docs/scanned.pdf` |
| `docling_table` | Digital table. Ruled lines are read from the PDF. | `sample_docs/table.pdf` |
| `paddle_table` | Scanned table. | HTML parser only. The live model was not run. |
| `formula` | A region that is an equation, not inline math in a paragraph. | `sample_docs/equation.pdf` |
| `chart` | A bar chart with printed values, or a PPTX chart. | `sample_docs/chart.pdf`, `sample_docs/sample.pptx` |
| `office` | A whole DOCX, XLSX, or PPTX. Prefer `extract_document`. | `sample.docx`, `sample.xlsx`, `sample.pptx` |
| `skip` | Decorative image. Returns `[]`. | — |

Anything else returns one failed block whose note names the route.

### Limits you must not demo as done

- `paddle_table` will try the Paddle table model. That download and run was not part of the sample suite. Failure is `TABLE_FAILED`.
- A digital table with no ruled lines falls back to Docling. `table.pdf` has ruled lines, so that fallback was not run.
- The VLM runs only after OCR finds nothing or is under 0.70 confidence, after LaTeX fails to parse, or when a chart caption has no readable bars. No API key was set. A missing key adds `vlm_unavailable` and continues. Put `VLM_API_KEY`, `VLM_MODEL`, and `VLM_BASE_URL` in `.env`. Do not commit `.env`.
- Line charts, and bar charts with no numbers printed on the bars, are not read. A caption with no bars becomes a `figure` with `status="needs_review"`.
- P3 does not merge a table onto the next page.
- P3 does not set `unit`, `scale`, or `repaired`.

---

## P1 — what to do

You own the orchestrator and the real schema. P3 never creates `pipeline/orchestrator.py` or `pipeline/schema.py`.

### 1. Point the orchestrator at these two functions

```python
from extractors import extract, extract_document

def extract_file(path: str, regions: list[dict]) -> list:
    suffix = path.lower().rsplit(".", 1)[-1]
    if suffix in {"docx", "xlsx", "pptx"}:
        return extract_document(path)
    blocks = []
    for region in regions:
        blocks.extend(extract(region, {"file_path": path, "format": suffix}))
    return blocks
```

Call `extract_document(path)` once per Office file. Do not cut a spreadsheet or a slide into page regions first. XLSX blocks have `source.page is None`, `page_start == 0`, and `bbox == [0, 0, 0, 0]`. The provenance is `source.sheet` and `source.cell_range`. PPTX uses `source.slide` and a shape bbox in points (EMU divided by 12700). DOCX has no page bbox until you convert it to PDF yourself. If you do that conversion, say so in `history`. P3 does not convert DOCX to PDF.

For a PDF or an image, loop the regions P2 gave you. One region, one `extract` call. Pass the same `file_path` each time.

`page_image` is optional. If you omit it, P3 renders the page from `file_path` at 150 DPI for OCR, formulas, and charts. If you pass it, also pass `page_size` in PDF points:

```python
context = {
    "file_path": path,
    "format": "pdf",
    "page_size": {"width": page.rect.width, "height": page.rect.height},
    "page_image": image,
}
```

The image must be the full page, not a crop. P3 crops `region["bbox"]` itself.

### 2. Collect failures, then keep going

```python
for block in extract(region, context):
    if block.status == "failed":
        document_errors.append({
            "region": region["id"],
            "code": block.history[0].get("error_code"),
            "note": block.history[0].get("note"),
        })
    document_blocks.append(block)
```

Do not wrap `extract` in a retry loop. Do not drop failed blocks if P5 needs to show the miss. `needs_review` is not a failure. Keep the block and show `history`.

### 3. Replace the schema stub without renaming fields

Until `pipeline/schema.py` exists, P3 loads `extractors/schema_stub.py`. The loader is `extractors/schema_ref.py`: it imports `pipeline.schema` when that module imports, and uses the stub otherwise.

When you add the real file, keep these names: `Block`, `ConfidenceInfo`, `SourceInfo`, and the fields listed in the shared contract. `content` stays `Any`. Do not make P3 add fields to the stub. If you need a new field, add it on your schema. P3 will not fill a field it does not know about.

After your schema imports cleanly, tell P3. The stub can be deleted then. Do not delete it before `from pipeline.schema import Block` works.

`reading_order` must stay writable. P3 writes `0`. P2 overwrites it before you serialize the final document.

### 4. Emit JSON and Markdown from the blocks

Suggested document JSON:

```json
{
  "file": "sample_docs/simple.pdf",
  "blocks": [],
  "errors": []
}
```

`blocks` is `[block.model_dump() for block in blocks]` after P2 has set reading order.

Markdown, in `reading_order`:

| `type` | Emit |
|---|---|
| `heading` | `#` repeated `content["level"]` times, then `content["text"]`. Default level 1. |
| `paragraph`, `list` | `content["text"]` |
| `table` | A markdown table from `header_rows` and `rows`. Use cell `text`, not `value`. |
| `equation` | A fenced block with `content["latex"]`. If `parsed` is false or status is `needs_review`, add a note. |
| `chart` | The title and each `series[].points` as `label: value`. Say the method. If `agreement` is null, do not write "verified". |
| `figure` | The caption in `content["text"]` and the crop path if present. |
| `failed` | Skip the body. The error list already has the code. |

### 5. Runtime notes

- Install from `requirements.txt` on Python 3.12. Paddle wheels on 3.13 were unreliable here.
- The first call to `ocr` or `formula` downloads models. Give that call a few minutes.
- Crops are written under `outputs/crops/`. That folder is gitignored except `.gitkeep`.
- VLM is off unless `.env` has a key. Integration tests should pass with no key.
- Do not import `paddleocr` or `docling` in the orchestrator at import time if you can avoid it. `from extractors import extract` does not load those engines. They load on the first region that needs them.

### 6. P1 acceptance check

From the repo root, after your orchestrator can call `extract`:

1. `simple.pdf` with `route="native_text"` and a full-page bbox returns a heading `Annual Financial Report 2025` and a paragraph that contains `FY2025`.
2. `scanned.pdf` with `route="ocr"` returns text containing `128.5` and `crore`.
3. `table.pdf` with `route="docling_table"` returns one `table` block. A cell text is `128.5`, `value` is `128.5`, `repaired` is false, and that cell has a four-number bbox.
4. `equation.pdf` with `route="formula"` returns `latex` containing `E` and a boolean `parsed`.
5. `chart.pdf` with `route="chart"` returns points `92.4`, `110.7`, and `128.5`.
6. `extract_document("sample_docs/sample.xlsx")` has sheet `Financials` and cell text `128.5`.
7. `extract_document("sample_docs/sample.docx")` has heading `Annual Financial Report 2025`.
8. `extract_document("sample_docs/sample.pptx")` has title `Revenue Growth` and a chart point `128.5`.
9. `extract({"id": "x", "route": "nope", "page": 1, "bbox": [0, 0, 1, 1]}, {"file_path": "sample_docs/simple.pdf"})` returns one failed block and does not raise.

---

## P2 — what to do

You classify the page and choose the route. P3 will not second-guess a route you set. A wrong route is the main way to get a failed block or a bad read.

You also assign reading order after the blocks come back, and you attach units. P3 leaves `reading_order` at `0`, `order_confidence` at `0.0`, and cell `unit` / `scale` at null.

### 1. Emit this region for every PDF region

```python
{
    "id": "r3",
    "type": "table",
    "page": 1,
    "bbox": [72.0, 80.0, 432.0, 164.0],
    "route": "docling_table",
    "is_scanned": False,
}
```

Rules:

- `page` is 1-based.
- `bbox` is `[x1, y1, x2, y2]` in PDF points. The origin is the top-left. `x1 < x2` and `y1 < y2`. PyMuPDF's `get_text("words")` is already in this system. If your layout model uses bottom-left or pixels, convert before the region leaves your code.
- The bbox should cover the whole object. A table bbox that cuts off the header drops those cells. A formula bbox should cover the equation line, not the caption, when you can separate them.
- Set `route` every time. The fallback when `route` is missing only catches digital text, scanned text, and tables. It does not catch charts or equations.
- `is_scanned` must agree with the route. Digital text with `is_scanned=True` will not take `native_text`.

### 2. Pick the route

| What you see | `route` | `is_scanned` | `type` |
|---|---|---|---|
| Digital text or a heading | `native_text` | `False` | `text`, `heading`, or `paragraph` |
| Scanned text | `ocr` | `True` | `text` |
| Digital table, including ruled financial tables | `docling_table` | `False` | `table` |
| Scanned table | `paddle_table` | `True` | `table` |
| Display equation | `formula` | `False` or `True` | `equation` |
| Bar chart, or a figure you are willing to fail honestly | `chart` | either | `chart` |
| Logo, line, decoration | `figure` or `skip` | either | `figure` |
| Whole DOCX, XLSX, or PPTX | Do not emit page regions. Tell P1 to call `extract_document`. | — | — |

More specific rules:

- Inline math stays in the paragraph. Route the paragraph as `native_text`. Route `formula` only when the region is the equation.
- A figure with no caption, no "Figure N", and no native series should be `skip` or left as a figure you do not send. If you send `route="chart"` and there are no bars, you get a `figure` block with `needs_review`, or `CHART_FAILED` on a blank crop. P3 will not invent series.
- Do not send a chart region for a PPTX file's embedded chart if P1 is already calling `extract_document`. That call returns the native series. A second `route="chart"` on the same PPTX also works and returns the same series.
- Do not ask P3 to merge a table that continues on the next page. Emit one region per page. Join them yourself if the demo needs one table.
- Multi-column pages are your reading-order problem. P3 returns the blocks inside each bbox and does not order them across the page.

### 3. After extraction, set order and units

P3 returns blocks in the order of the regions you passed, and inside a region in its own local order. `extract()` still leaves `reading_order` at `0` and `order_confidence` at `0.0`. `parse_document` copies both from the region before assembly, and stores the layout checks on `links.layout`. A merged table's notes land on `links.table_merge` because `Block` has no metadata field.

For tables and charts, read headers and nearby captions and set:

- cell `unit` and `scale` (`crore`, `million`, `percent`)
- chart `y_axis.unit` when the caption supports it

P3 leaves those null on purpose, including on `chart.pdf`, whose caption is `Figure 1 Revenue` and whose values are `92.4`, `110.7`, `128.5`.

If two blocks disagree with the prose around them, that check belongs to P4. Leave P3's `history` intact so P4 can see which engine ran.

### 4. How to read a needs_review block

| Situation | What you will see | What you should do |
|---|---|---|
| Formula model disagrees with the text layer | `status="needs_review"`, `content["parsed"]=true`, other string in `candidates` | Keep `content["latex"]`. Do not drop `candidates`. |
| LaTeX does not parse and no VLM key is set | `formula_parse_fail` and `vlm_unavailable` | Show the raw string. Do not mark it verified. |
| OCR confidence under 0.70 | flag `ocr_low_conf` | Keep the text. P4 may ask for another read. |
| Chart has only one method | `agreement` is `null` | Order it like any other block. Do not treat it as double-checked. |
| Caption and no bars | `type="figure"`, `status="needs_review"` | It is a figure, not a chart. No series. |

### 5. Coordinate check before you hand regions to P1

On `sample_docs/simple.pdf` the heading words sit near `y` 60 to 85, not near the bottom of the 792-point page. If your boxes come out around `y` 700 for that heading, the origin is still bottom-left and P3 will read the wrong strip of the page.

A full-page box `[0, 0, 612, 792]` is valid and is what the sample tests use. Tighter boxes are better once your layout model exists.

### 6. P2 acceptance check

Build regions by hand for the samples, pass them through `extract`, and check:

1. `simple.pdf`, `native_text`, full page: heading text `Annual Financial Report 2025`, bbox length 4, `reading_order == 0` before you touch it.
2. Same file, bbox `[0, 0, 10, 10]`: no block that contains the heading. A tight box must not leak the rest of the page.
3. `scanned.pdf`, `ocr`, `is_scanned=True`: text contains `128.5`.
4. `table.pdf`, `docling_table`: one table, headers include `Year`, `Revenue`, `EBITDA`, a cell bbox has four numbers.
5. `equation.pdf`, `formula`: `content["latex"]` and `content["parsed"]` is a bool.
6. `chart.pdf`, `chart`: `chart_type == "bar"` and at least the points above.
7. A region with `route="skip"` returns `[]`.
8. A region with `route="made-up"` returns `status="failed"` and does not raise.

Then run your real layout output through the same function. If a sample passes with a hand-built box and fails with your box, the bug is the box or the route, not the extractor.

---

## What neither of you should change in this repo

- Do not add a route. Unknown routes already fail clearly.
- Do not add fields to `extractors/schema_stub.py`.
- Do not vendor a second copy of Paddle or Docling. Call `extract`.
- Do not send a full page image to the VLM. `read_crop` exists for P4 and takes one crop. P3 already calls it at the escalation points above.
- `vlm_call_count()` is the cost counter. Read it. Do not keep a second counter.
