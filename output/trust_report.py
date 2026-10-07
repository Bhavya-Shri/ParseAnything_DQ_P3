from pipeline.schema import DocumentResult

def write_trust_report(doc: DocumentResult, output_path: str):
    """
    Generates a human-readable trust report for judges.
    Shows: coverage, confidence, arithmetic checks, repairs, cost.
    """
    lines = []
    tr = doc.trust_report
    m = doc.metrics

    lines.append("=" * 60)
    lines.append("  PARSEANYTHING — TRUST REPORT")
    lines.append("=" * 60)
    lines.append(f"  Document : {doc.filename}")
    lines.append(f"  Format   : {doc.format.upper()}")
    lines.append(f"  Pages    : {doc.page_count}")
    lines.append(f"  Status   : {doc.status.upper()}")
    lines.append("")

    # Block statistics
    lines.append("--- Block Summary ---")
    total = tr.get("total_blocks", len(doc.blocks))
    lines.append(f"  Total blocks    : {total}")
    lines.append(f"  Verified        : {tr.get('verified', 0)}")
    lines.append(f"  Accepted        : {tr.get('accepted', 0)}")
    lines.append(f"  Needs review    : {tr.get('needs_review', 0)}")
    lines.append(f"  Failed          : {tr.get('failed', 0)}")
    lines.append("")

    # Arithmetic checks
    lines.append("--- Arithmetic Audit ---")
    ar = tr.get("arithmetic_checks_run", 0)
    ap = tr.get("arithmetic_checks_passed", 0)
    af = tr.get("arithmetic_checks_failed", 0)
    lines.append(f"  Checks run      : {ar}")
    lines.append(f"  Passed          : {ap}")
    lines.append(f"  Failed          : {af}")
    lines.append(f"  Repaired cells  : {tr.get('repaired_cells', 0)}")
    if ar > 0:
        pct = round(100 * ap / ar, 1)
        lines.append(f"  Pass rate       : {pct}%")
    lines.append("")

    # Document map coverage
    if doc.document_map:
        lines.append("--- Document Map Coverage ---")
        lines.append(f"  Sections in map : {len(doc.document_map)}")
        for entry in doc.document_map:
            lines.append(f"  [{entry.get('kind','?').upper()}] {entry.get('title','')} (p.{entry.get('page','?')})")
        lines.append("")

    # Errors
    if doc.errors:
        lines.append("--- Errors ---")
        for e in doc.errors:
            lines.append(f"  [{e.get('error_code')}] {e.get('message')} (stage: {e.get('stage')})")
        lines.append("")

    # Flagged blocks
    flagged = [b for b in doc.blocks if b.status in ("needs_review", "failed")]
    if flagged:
        lines.append("--- Flagged Blocks ---")
        for b in flagged:
            lines.append(f"  {b.id} | {b.type} | p.{b.page_start} | "
                         f"confidence={b.confidence.final:.2f} | risk={b.risk} | flags={b.flags}")
        lines.append("")

    # Performance and cost
    lines.append("--- Performance ---")
    lines.append(f"  Total time      : {m.get('total_time_seconds', 0):.2f}s")
    lines.append(f"  Pages/sec       : {m.get('pages_per_second', 0):.2f}")
    lines.append(f"  VLM calls       : {m.get('vlm_calls', 0)}")
    lines.append(f"  OCR pages       : {m.get('ocr_pages', 0)}")
    lines.append("")
    lines.append("=" * 60)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return "\n".join(lines)
