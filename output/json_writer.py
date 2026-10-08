import json
from pipeline.schema import DocumentResult

def render_json(doc: DocumentResult) -> str:
    """Same JSON write_json saves to disk."""
    return json.dumps(doc.model_dump(), indent=2)


def write_json(doc: DocumentResult, output_path: str):
    """Serialize DocumentResult to JSON."""
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(render_json(doc))
