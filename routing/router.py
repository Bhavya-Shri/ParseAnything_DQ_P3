from .route_models import PageProfile, Region, RouteDecision


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _region_complexity(region: Region) -> float:
    score = 0.0

    if region.region_type in (
        "table",
        "formula",
        "chart",
        "figure",
    ):
        score += 0.35

    if region.source in (
        "layout_model",
        "pp_structure_v3",
    ):
        score += 0.15

    if region.confidence < 0.60:
        score += 0.25

    if region.metadata.get(
        "order_ambiguous",
        False
    ):
        score += 0.15

    if region.is_full_width:
        score += 0.05

    return _clamp(score)


def _choose_route(
    region,
    profile,
    risk
):
    region_type = region.region_type

    if region_type == "table":
        return "table", "table_extractor"

    if region_type == "formula":
        return "equation", "equation_extractor"

    if region_type == "chart":
        return "chart", "chart_extractor"

    if region_type == "figure":
        return "figure", "figure_extractor"

    if risk in (
        "HIGH",
        "CRITICAL",
    ):
        return "vlm", "vlm_fallback"

    if region.metadata.get(
        "order_ambiguous",
        False
    ):
        return "vlm", "vlm_fallback"

    if profile.is_scanned:

        if risk in (
            "HIGH",
            "CRITICAL",
        ):
            return "vlm", "vlm_fallback"

        return "ocr", "ocr_extractor"

    if region.source in (
        "layout_model",
        "pp_structure_v3",
    ):

        if region.confidence < 0.50:
            return "vlm", "vlm_fallback"

    if region.confidence < 0.45:
        return "ocr", "ocr_extractor"

    return "native", "native_text_extractor"


def _calculate_confidence(
    region,
    profile,
    route,
    risk
):
    confidence = 0.90

    confidence += (
        region.confidence - 0.75
    ) * 0.30

    if profile.is_scanned:

        if route == "ocr":
            confidence += 0.03

        elif route == "native":
            confidence -= 0.25

    if region.source in (
        "layout_model",
        "pp_structure_v3",
    ):
        confidence += 0.02

    if risk == "HIGH":
        confidence -= 0.05

    elif risk == "CRITICAL":
        confidence -= 0.10

    complexity = _region_complexity(
        region
    )

    confidence -= complexity * 0.10

    return _clamp(confidence)


def _reason(
    region,
    profile,
    route,
    risk
):
    if region.region_type == "table":
        return "Region identified as table"

    if region.region_type == "formula":
        return "Region identified as equation or formula"

    if region.region_type == "chart":
        return "Region identified as chart"

    if region.region_type == "figure":
        return "Region identified as figure"

    if risk in (
        "HIGH",
        "CRITICAL",
    ):
        return "High-risk region requires visual fallback"

    if region.metadata.get(
        "order_ambiguous",
        False
    ):
        return "Ambiguous reading order requires visual fallback"

    if profile.is_scanned and route == "ocr":
        return "Scanned page requires OCR"

    if route == "vlm":
        return "Region requires visual fallback"

    if route == "ocr":
        return "Native extraction confidence is too low"

    return "Native document text is suitable"


def _priority(
    region,
    risk
):
    if risk == "CRITICAL":
        return "critical"

    if risk == "HIGH":
        return "high"

    if region.region_type in (
        "table",
        "formula",
        "chart",
    ):
        return "high"

    if region.metadata.get(
        "order_ambiguous",
        False
    ):
        return "high"

    return "normal"


def route_region(
    region,
    profile,
    risk="LOW"
):
    route, extractor = _choose_route(
        region,
        profile,
        risk
    )

    confidence = _calculate_confidence(
        region,
        profile,
        route,
        risk
    )

    reason = _reason(
        region,
        profile,
        route,
        risk
    )

    priority = _priority(
        region,
        risk
    )

    return RouteDecision(
        region_id=region.region_id,
        route=route,
        extractor=extractor,
        confidence=confidence,
        reason=reason,
        priority=priority,
    )


def route_regions(
    regions,
    profile,
    risk="LOW"
):
    decisions = []

    for region in regions:
        decisions.append(
            route_region(
                region,
                profile,
                risk
            )
        )

    return decisions