# ParseAnything

ParseAnything reads a PDF, Word document, spreadsheet, slide deck, or scan and returns the content in reading order, with a box, an extractor, a confidence score, and a risk level for every block.

The same parse path serves the local page and the command line. A file goes through ingest, layout and reading order, extraction, then trust scoring. The page shows the Markdown and JSON those writers produce.

## What you get

Each block has a type, the extracted content, the page and box, the reading order, the extractor, four confidence numbers (extraction, structure, source quality, final), and a risk of `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`.

The page at `http://127.0.0.1:8765` has four views after a file is read:

| View | What it shows |
|---|---|
| Markdown and JSON | The writer output. Each box has a Copy button. |
| Reading | The blocks in reading order, with type, risk, score, and extractor. |
| Regions | Page, box, region, extractor, score, and risk. |
| Precedence | Which block comes before which. Select a block for its source and scores. |

Accepted files: PDF, DOCX, XLSX, PPTX, PNG, JPG.

## Run the page

Python 3.12 is required. The machine default of 3.13 is unreliable with Paddle.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app\server.py
```

Open http://127.0.0.1:8765. Drop a file, or choose **Open the sample report**. Uploads are saved in `outputs/uploads`.

The page is static HTML, CSS, and JavaScript in `app/static`. `app/server.py` accepts the file, calls `parse_document`, then returns the document plus the Markdown from `output/markdown_writer.py` and the JSON from `output/json_writer.py`.

## Run the command line

```powershell
.\.venv\Scripts\python cli.py sample_docs\sample.docx --out-md outputs\sample.md --out-json outputs\sample.json
```

`--timeout N` stops a parse after N seconds. Without it, a parse runs until it finishes.

```powershell
docker build -t parseanything .
docker run --rm -v ${PWD}/sample_docs:/data parseanything /data/sample.docx --out-md /data/out.md --out-json /data/out.json
```

## Pipeline

| Stage | Role |
|---|---|
| Ingest | Opens a PDF with PyMuPDF. Office files use their native readers. Images are treated as scans. |
| Layout | Finds regions, splits columns, and sets reading order. A table that continues onto the next page is merged. |
| Extract | Reads text, ruled tables, borderless tables, charts, equations, and figures. Borderless tables use Docling one page at a time. |
| Trust | Fills structure, source quality, the final confidence, and risk. Extracted text is left as the extractor wrote it. |

A high-risk block can be compared with a second result in `validation/verification.py`. The live parse does not run a second extractor. With no second result, nothing is marked verified.

## Tests

```powershell
.\.venv\Scripts\python -m pytest tests/test_p4.py tests/test_p3_pipeline.py tests/test_office.py tests/test_handoff.py
```

The first PDF test loads the layout model, so the run takes a few minutes.

## Layout

```
app/            local reader and the page
pipeline/       ingest and parse_document
routing/        regions, columns, reading order
extractors/     text, tables, charts, equations, figures, office
assembly/       block assembly and cross-page table merge
validation/     confidence, risk, arithmetic, verification
output/         Markdown and JSON writers
sample_docs/    small files used by the tests and the sample report
```

`sample_docs/fin_rep.pdf` is a large third-party report and is not in the repository. A 216-page parse of it finished as `partial` in about 28 minutes.

## Limits

- A nonempty corrupt PDF can come back `complete` with zero blocks.
- The phone-scan table in `sample_docs/02_phone_scan_table.png` returns `TABLE_FAILED` after the title is read.
- Chart and figure regions that the model cannot read stay flagged. Their text is not invented.
- Paddle is started with oneDNN off (`FLAGS_use_mkldnn=0`, `enable_mkldnn=False`).
