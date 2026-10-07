from pipeline.schema import DocumentResult, ParseError
from pipeline.errors import ParseAnythingException
from pipeline.preflight import preflight_check
from pipeline.ingestion import ingest_document

from routing.page_profiler import profile_page
from routing.region_detector import (
    detect_native_regions,
    merge_region_sources,
)
from routing.pp_structure_adapter import (
    adapt_layout_result,
    should_use_layout_model,
)
from routing.column_detector import detect_layout_sections
from routing.reading_order import reconstruct_reading_order
from routing.router import route_regions

import logging
import os
import time
import numpy as np
import fitz

logger = logging.getLogger(__name__)


def _create_layout_model():
    """
    Create the standalone PaddleOCR layout detection model.

    P2 only needs document layout detection here.
    OCR and content extraction are handled by P3.
    """

    os.environ["FLAGS_use_mkldnn"] = "0"
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

    from paddleocr import LayoutDetection

    logger.info(
        "Initializing standalone layout detection model..."
    )

    return LayoutDetection(
        model_name="PP-DocLayout_plus-L",
        device="cpu",
        enable_mkldnn=False,
        cpu_threads=4,
    )


def _get_layout_result(model, page):
    """
    Run standalone layout detection on a rendered PDF page.
    """

    try:
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(1, 1),
            alpha=False
        )

        image = np.frombuffer(
            pixmap.samples,
            dtype=np.uint8
        )

        image = image.reshape(
            pixmap.height,
            pixmap.width,
            pixmap.n
        )

        predictions = model.predict(
            image,
            batch_size=1,
            layout_nms=True
        )

        for result in predictions:
            return result

    except Exception as e:
        logger.warning(
            f"Layout detection failed on page "
            f"{page.number + 1}: {e}"
        )

    return None


def _run_p2(ingestion_data):
    """
    Run the complete P2 routing pipeline on ingested PDF pages.

    P2 flow:

    profiling
    -> native region detection
    -> optional visual layout detection
    -> region source merging
    -> column/layout section detection
    -> reading order
    -> extractor routing
    """

    pdf_doc = ingestion_data.get(
        "pymupdf_doc"
    )

    if pdf_doc is None:
        logger.info(
            "P2 PDF routing skipped: "
            "no PyMuPDF document available."
        )
        return [], []

    all_regions = []
    all_routes = []

    layout_model = None

    try:

        for page in pdf_doc:

            # -------------------------------------------------
            # 1. PAGE PROFILING
            # -------------------------------------------------

            profile = profile_page(page)

            logger.info(
                f"P2 page {profile.page_number}: "
                f"complexity={profile.complexity}, "
                f"columns={profile.estimated_columns}"
            )

            # -------------------------------------------------
            # 2. NATIVE REGION DETECTION
            # -------------------------------------------------

            native_regions = detect_native_regions(
                page,
                profile
            )

            # -------------------------------------------------
            # 3. OPTIONAL VISUAL LAYOUT DETECTION
            # -------------------------------------------------

            layout_regions = []

            if should_use_layout_model(profile):

                if layout_model is None:
                    layout_model = _create_layout_model()

                logger.info(
                    f"P2 page {profile.page_number}: "
                    "using standalone layout detection"
                )

                layout_result = _get_layout_result(
                    layout_model,
                    page
                )

                if layout_result is not None:

                    layout_regions = (
                        adapt_layout_result(
                            layout_result,
                            profile
                        )
                    )

                    logger.info(
                        f"P2 page {profile.page_number}: "
                        f"layout detector produced "
                        f"{len(layout_regions)} regions"
                    )

            # -------------------------------------------------
            # 4. MERGE NATIVE + LAYOUT REGIONS
            # -------------------------------------------------

            regions = merge_region_sources(
                native_regions,
                layout_regions
            )

            if not regions:
                logger.info(
                    f"P2 page {profile.page_number}: "
                    "no regions detected."
                )
                continue

            # -------------------------------------------------
            # 5. COLUMN / LAYOUT SECTIONS
            # -------------------------------------------------

            sections = detect_layout_sections(
                regions,
                profile
            )

            # -------------------------------------------------
            # 6. READING ORDER
            # -------------------------------------------------

            regions = reconstruct_reading_order(
                regions,
                sections
            )

            # -------------------------------------------------
            # 7. EXTRACTOR ROUTING
            # -------------------------------------------------

            routes = route_regions(
                regions,
                profile,
                risk="LOW"
            )

            # Attach routing information to regions.

            for decision in routes:

                for region in regions:

                    if (
                        region.region_id
                        == decision.region_id
                    ):

                        region.metadata[
                            "route"
                        ] = decision.route

                        region.metadata[
                            "extractor"
                        ] = decision.extractor

                        region.metadata[
                            "route_confidence"
                        ] = decision.confidence

                        region.metadata[
                            "route_reason"
                        ] = decision.reason

                        region.metadata[
                            "priority"
                        ] = decision.priority

                        region.metadata[
                            "is_scanned"
                        ] = profile.is_scanned

                        region.metadata[
                            "page_width"
                        ] = profile.width

                        region.metadata[
                            "page_height"
                        ] = profile.height

                        break

            all_regions.extend(regions)
            all_routes.extend(routes)

            logger.info(
                f"P2 page {profile.page_number}: "
                f"{len(regions)} regions, "
                f"{len(sections)} layout sections, "
                f"{len(routes)} routing decisions"
            )

    finally:

        pdf_doc.close()

    return (
        all_regions,
        all_routes
    )


def parse_document(
    file_path: str,
    options: dict | None = None
) -> DocumentResult:

    """
    Phase D — Orchestration.

    Coordinates:

    Preflight
        ->
    Ingestion
        ->
    P2 profiling
        ->
    P2 region detection
        ->
    P2 visual layout detection
        ->
    P2 column detection
        ->
    P2 reading order
        ->
    P2 extractor routing
        ->
    P3 Extraction
        ->
    P4 Verification
    """

    options = options or {}

    start_time = time.time()

    logger.info(
        f"Starting ParseAnything pipeline "
        f"for {file_path}"
    )

    # ---------------------------------------------------------
    # 1. PREFLIGHT
    # ---------------------------------------------------------

    try:

        preflight_data = preflight_check(
            file_path
        )

    except ParseAnythingException as e:

        logger.error(
            f"Preflight failed: "
            f"{e.error.message}"
        )

        return DocumentResult(
            document_id="doc_unknown",
            filename=file_path,
            format="unknown",
            page_count=0,
            status="failed",
            blocks=[],
            errors=[
                e.error.model_dump()
            ]
        )

    doc_id = (
        f"doc_"
        f"{preflight_data['trace_id'][:8]}"
    )

    if preflight_data["format"] in {"docx", "xlsx", "pptx"}:
        from pipeline.p3_bridge import document_from_office

        return document_from_office(
            file_path,
            preflight_data,
            doc_id,
            start_time,
        )

    # ---------------------------------------------------------
    # 2. INGESTION
    # ---------------------------------------------------------

    try:

        ingestion_data = ingest_document(
            file_path,
            preflight_data
        )

        page_count = len(
            ingestion_data.get(
                "page_dimensions",
                {}
            )
        )

        if page_count == 0:

            docling_document = (
                ingestion_data.get(
                    "docling_document"
                )
            )

            if docling_document is not None:

                pages = getattr(
                    docling_document,
                    "pages",
                    {}
                )

                page_count = len(pages)

    except TimeoutError as e:

        logger.error(
            f"Ingestion Timeout: {e}"
        )

        error = ParseError(
            status="failed",
            error_code="TIMEOUT",
            message=str(e),
            recoverable=False,
            stage="ingestion",
            trace_id=preflight_data[
                "trace_id"
            ]
        )

        return DocumentResult(
            document_id=doc_id,
            filename=preflight_data[
                "filename"
            ],
            format=preflight_data[
                "format"
            ],
            page_count=0,
            status="failed",
            blocks=[],
            errors=[
                error.model_dump()
            ]
        )

    except Exception as e:

        logger.error(
            f"Ingestion failed: {e}"
        )

        error = ParseError(
            status="failed",
            error_code="INTERNAL_ERROR",
            message=str(e),
            recoverable=False,
            stage="ingestion",
            trace_id=preflight_data[
                "trace_id"
            ]
        )

        return DocumentResult(
            document_id=doc_id,
            filename=preflight_data[
                "filename"
            ],
            format=preflight_data[
                "format"
            ],
            page_count=0,
            status="failed",
            blocks=[],
            errors=[
                error.model_dump()
            ]
        )

    # ---------------------------------------------------------
    # 3. P2 ROUTING
    # ---------------------------------------------------------

    logger.info(
        "Routing document through "
        "complete P2 pipeline..."
    )

    try:

        (
            p2_regions,
            p2_routes
        ) = _run_p2(
            ingestion_data
        )

        logger.info(
            f"P2 produced "
            f"{len(p2_regions)} regions "
            f"and "
            f"{len(p2_routes)} routing decisions."
        )

    except Exception as e:

        logger.error(
            f"P2 routing failed: {e}"
        )

        error = ParseError(
            status="failed",
            error_code="P2_ROUTING_ERROR",
            message=str(e),
            recoverable=True,
            stage="routing",
            trace_id=preflight_data[
                "trace_id"
            ]
        )

        return DocumentResult(
            document_id=doc_id,
            filename=preflight_data[
                "filename"
            ],
            format=preflight_data[
                "format"
            ],
            page_count=page_count,
            page_sizes=ingestion_data.get(
                "page_dimensions",
                {}
            ),
            status="partial",
            blocks=[],
            errors=[
                error.model_dump()
            ]
        )

    # ---------------------------------------------------------
    # 4. P3 EXTRACTION AND P2 ASSEMBLY
    # ---------------------------------------------------------

    logger.info(
        "Extracting blocks through "
        "P3 extractors..."
    )

    from pipeline.p3_bridge import document_from_regions

    return document_from_regions(
        file_path,
        preflight_data,
        doc_id,
        start_time,
        p2_regions,
        page_count,
        ingestion_data.get("page_dimensions", {}),
        len(p2_routes),
    )