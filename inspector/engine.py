"""Run all checks and build the report structure."""
import datetime
from . import status as S, pdf_analysis as P, compare as C, barcodes as B, specs, checks as K, textdoc as T, ocr as OCR
from .status import make

STANDING_LIMITS = [
    ("OCR scope", S.REVIEW, "OCR runs only on pages without a usable text layer and only on regions where the visual comparison found differences. Its output is a reading of pixels with a confidence value, never proof of wording, font, size, bold or underline."),
    ("Colour (ICC / tint values / overprint / Delta E)", S.NOT_IMPLEMENTED, "Compared: text and vector RGB values, spot ink names, RGB render. Not evaluated: ICC conversion, tint percentages, overprint, Delta E. Screen RGB is not a colorimetric measurement."),
    ("Dieline / cut and fold lines", S.NOT_IMPLEMENTED, "Dieline extraction is not implemented."),
    ("Regulatory / compliance rules", S.NOT_CONFIGURED, "No documented rules supplied; no compliance result is issued."),
    ("Packaging material profile", S.NOT_CONFIGURED, "No approved material profile supplied."),
    ("Image registration / alignment", S.NOT_IMPLEMENTED, "Pages are compared at identical coordinates only. A shifted layout shows as differences."),
    ("Authentication, audit trail, e-signatures", S.NOT_IMPLEMENTED, "Not a GMP-validated system. Results must not be the sole basis for release decisions."),
]


def run(ref_bytes, cand_bytes, spec_text=None, dpi=100, threshold=40, do_barcode=True, do_ocr=True):
    ref, cand = P.analyze(ref_bytes), P.analyze(cand_bytes)
    n = min(ref["page_count"], cand["page_count"])
    rows = []
    rows += C.compare_pages_count(ref, cand)
    rows += C.compare_dimensions(ref, cand, n)
    rows += C.compare_text(ref, cand, n)
    rows += C.compare_fonts(ref, cand, n)
    rows += C.compare_styles(ref, cand, n)
    rows += C.compare_images(ref, cand, n)
    rows += C.compare_annotations(ref, cand, n)
    rows += C.compare_colors(ref, cand, n)
    rows += C.compare_image_resolution(ref, cand, n)
    rows += C.dimension_summary(ref)
    rows += K.check_text_layer(ref, cand, n)
    rows += K.check_font_embedding(ref, cand, n)
    rows += K.check_rotation(ref, cand, n)
    rows += K.compare_metadata(ref, cand)
    trows, thl, thin = T.compare(ref_bytes, cand_bytes, n, dpi)
    rows += trows
    pairs = [(i + 1, P.render_page(ref_bytes, i, dpi), P.render_page(cand_bytes, i, dpi)) for i in range(n)]
    vrows, overlays = C.compare_visual(pairs, dpi, threshold)
    rows += vrows
    if do_barcode:
        for i in range(n):
            rows += B.compare_barcodes(lambda d, i=i: P.render_page(ref_bytes, i, d), lambda d, i=i: P.render_page(cand_bytes, i, d), i + 1)
    else:
        rows.append(make("Barcode", S.NOT_VERIFIABLE, "Barcode step skipped by user", None, "render"))
    if do_ocr and thin:
        orows, ohl = OCR.compare(ref_bytes, cand_bytes, thin, {k: v[1] for k, v in overlays.items() if isinstance(k, int)}, dpi)
        rows += orows
        for pg, (xa, xb) in ohl.items():
            ra, rb = thl.get(pg, ([], []))
            thl[pg] = (ra + xa, rb + xb)
    elif thin:
        rows += [make("OCR wording of outlined text", S.NOT_IMPLEMENTED, "OCR was switched off for this run.", pg, "OCR") for pg in thin]
    for pg, (ra, rb) in thl.items():
        if ra or rb:
            overlays[f"{pg} Reference (text/format/table/code highlights)"] = (pairs[pg - 1][1], ra)
            overlays[f"{pg} Candidate (text/format/table/code highlights)"] = (pairs[pg - 1][2], rb)
    rows += specs.check(ref, spec_text)
    for name, st, detail in STANDING_LIMITS:
        rows.append(make(name, st, detail, None, "limitation"))
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in S.ALL}
    if counts[S.FAIL]:
        overall = "Differences found"
    elif counts[S.NOT_VERIFIABLE] or counts[S.REVIEW] or counts[S.NOT_CONFIGURED] or counts[S.NOT_IMPLEMENTED]:
        overall = "No differences in the checks that ran. Items remain unverified: human review required"
    else:
        overall = "No differences found (human review still mandatory)"
    return {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "reference": {"sha256": ref["sha256"], "pages": ref["page_count"], "metadata": ref["metadata"]},
            "candidate": {"sha256": cand["sha256"], "pages": cand["page_count"], "metadata": cand["metadata"]},
            "settings": {"dpi": dpi, "threshold": threshold, "geometry_tolerance_pt": C.TOL_PT},
            "overall": overall, "counts": counts, "rows": rows, "analysis": {"reference": ref, "candidate": cand}}, overlays
