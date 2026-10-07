import json
from pipeline.schema import DocumentResult

def write_json(doc: DocumentResult, output_path: str):
    """Serialize DocumentResult to JSON."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(doc.model_dump(), f, indent=2)
