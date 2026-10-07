import logging

import pymupdf

logger = logging.getLogger(__name__)


def ingest_document(file_path: str, preflight_data: dict) -> dict:
    """
    Phase B & C — Document ingestion.

    PDFs:
        PyMuPDF provides native text and page geometry.
        P2 handles visual/layout detection.

    Office documents:
        Docling handles universal document ingestion.
    """

    format_type = preflight_data["format"]

    result = {
        "docling_document": None,
        "docling_dict": None,
        "pymupdf_doc": None,
        "page_dimensions": {}
    }

    # --------------------------------------------------
    # PDF ingestion
    # --------------------------------------------------
    if format_type == "pdf":
        try:
            logger.info("Loading PDF with PyMuPDF...")

            pdf_doc = pymupdf.open(file_path)
            result["pymupdf_doc"] = pdf_doc

            for page_num in range(len(pdf_doc)):
                page = pdf_doc.load_page(page_num)
                rect = page.rect

                result["page_dimensions"][str(page_num + 1)] = {
                    "width": float(rect.width),
                    "height": float(rect.height)
                }

            logger.info(
                f"PyMuPDF loaded {len(pdf_doc)} pages."
            )

            return result

        except Exception as e:
            logger.error(f"PyMuPDF ingestion failed: {e}")
            raise e

    # --------------------------------------------------
    # Office / other document ingestion
    # --------------------------------------------------
    try:
        logger.info("Starting Docling ingestion...")

        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        doc_result = converter.convert(file_path)

        result["docling_document"] = doc_result.document
        result["docling_dict"] = (
            doc_result.document.export_to_dict()
        )

        logger.info("Docling ingestion complete.")

    except Exception as e:
        logger.error(f"Docling ingestion failed: {e}")
        raise e

    # --------------------------------------------------
    # Docling page geometry
    # --------------------------------------------------
    try:
        for page_number, page in result["docling_document"].pages.items():
            size = getattr(page, "size", None)

            if size is not None:
                width = float(getattr(size, "width", 0.0))
                height = float(getattr(size, "height", 0.0))

                result["page_dimensions"][str(page_number)] = {
                    "width": width,
                    "height": height
                }

    except Exception as e:
        logger.warning(
            f"Could not read Docling page dimensions: {e}"
        )

    return result