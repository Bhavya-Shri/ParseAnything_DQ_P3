"""Local reader for ParseAnything. Serves the page and runs parse_document."""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
UPLOADS = ROOT / "outputs" / "uploads"
ALLOWED = {".pdf", ".docx", ".xlsx", ".pptx", ".png", ".jpg", ".jpeg"}

sys.path.insert(0, str(ROOT))


def sample_rows() -> list[dict]:
    rows = []
    folder = ROOT / "sample_docs"
    if not folder.is_dir():
        return rows
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in ALLOWED:
            continue
        rows.append(
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "slow": path.stat().st_size > 1_000_000,
            }
        )
    return rows


def parse_file(path: Path) -> dict:
    from output.json_writer import render_json
    from output.markdown_writer import render_markdown
    from pipeline.orchestrator import parse_document

    document = parse_document(str(path))
    return {
        "document": document.model_dump(mode="json"),
        "markdown": render_markdown(document),
        "json": render_json(document),
    }


def _safe_sample(name: str) -> Path:
    cleaned = Path(name).name
    path = (ROOT / "sample_docs" / cleaned).resolve()
    if path.parent != (ROOT / "sample_docs").resolve() or path.suffix.lower() not in ALLOWED:
        raise ValueError("That sample is not available.")
    if not path.is_file():
        raise ValueError("That sample is not on disk.")
    return path


def _save_upload(filename: str, payload: bytes) -> Path:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError("Use a PDF, Office file, or image.")
    if not payload:
        raise ValueError("The upload was empty.")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    target = UPLOADS / Path(filename).name
    target.write_bytes(payload)
    return target


def _file_from_multipart(body: bytes, boundary: str) -> tuple[str, bytes]:
    marker = ("--" + boundary).encode("utf-8")
    for part in body.split(marker):
        if b"Content-Disposition" not in part:
            continue
        header, _, content = part.partition(b"\r\n\r\n")
        text = header.decode("utf-8", "replace")
        if 'filename="' not in text:
            continue
        filename = text.split('filename="', 1)[1].split('"', 1)[0]
        if content.endswith(b"\r\n"):
            content = content[:-2]
        return filename, content
    raise ValueError("No file was attached.")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, payload, content_type: str) -> None:
        if isinstance(payload, str):
            body = payload.encode("utf-8")
        else:
            body = payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/app.js":
            self._send(200, (STATIC / "app.js").read_bytes(), "text/javascript; charset=utf-8")
            return
        if path == "/styles.css":
            self._send(200, (STATIC / "styles.css").read_bytes(), "text/css; charset=utf-8")
            return
        if path == "/api/samples":
            self._json(200, {"samples": sample_rows()})
            return
        self._json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/parse":
            self._json(404, {"error": "Not found"})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b""
        ctype = self.headers.get("Content-Type", "")
        try:
            if ctype.startswith("application/json"):
                data = json.loads(raw.decode("utf-8") or "{}")
                path = _safe_sample(str(data.get("sample") or ""))
            elif "multipart/form-data" in ctype and "boundary=" in ctype:
                boundary = ctype.split("boundary=", 1)[1].split(";", 1)[0].strip().strip('"')
                filename, payload = _file_from_multipart(raw, boundary)
                path = _save_upload(filename, payload)
            else:
                raise ValueError("Send a sample name or a file.")
            self._json(200, parse_file(path))
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("ParseAnything reader at http://127.0.0.1:8765", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
