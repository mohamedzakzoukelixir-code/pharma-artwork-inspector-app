import pymupdf
import pytest
from inspector import pdf_analysis as P, compare as C, engine, specs, report, status as S
from inspector.pdf_analysis import UnsupportedPDF


def statuses(res, check):
    return [r["status"] for r in res["rows"] if r["check"] == check]


def run(a, b, **kw):
    res, _ = engine.run(a, b, do_barcode=False, **kw)
    return res


# --- native analysis
def test_analyze_basics(pdf):
    a = P.analyze(pdf())
    assert a["page_count"] == 1 and a["pages"][0]["width_pt"] == 300
    assert a["pages"][0]["boxes"]["MediaBox"] == [0, 0, 300, 200]
    assert a["pages"][0]["spans"][0]["text"] == "Dose 20 mg"


def test_multi_page(pdf):
    a = P.analyze(pdf(pages=(("p1", 12, (0, 0, 0)), ("p2", 12, (0, 0, 0)), ("p3", 12, (0, 0, 0)))))
    assert a["page_count"] == 3 and [p["index"] for p in a["pages"]] == [1, 2, 3]


def test_trimbox_read():
    doc = pymupdf.open(); pg = doc.new_page(width=200, height=100)
    doc.xref_set_key(pg.xref, "TrimBox", "[10 10 190 90]")
    a = P.analyze(doc.tobytes())
    assert a["pages"][0]["boxes"]["TrimBox"] == [10, 10, 190, 90]
    assert a["pages"][0]["boxes"]["BleedBox"] is None


def test_corrupt_and_unsupported():
    with pytest.raises(UnsupportedPDF):
        P.analyze(b"not a pdf")
    with pytest.raises(UnsupportedPDF):
        P.analyze(b"")


# --- identical files
def test_identical_has_no_fail(pdf):
    res = run(pdf(), pdf())
    assert res["counts"][S.FAIL] == 0
    assert "unverified" in res["overall"]  # standing limitations keep it from claiming full pass


def test_never_pass_for_unconfigured(pdf):
    res = run(pdf(), pdf())
    assert statuses(res, "Dimensional spec check") == [S.NOT_CONFIGURED]
    assert statuses(res, "Regulatory / compliance rules") == [S.NOT_CONFIGURED]
    assert statuses(res, "OCR") == [S.NOT_IMPLEMENTED]


# --- differences
def test_text_difference(pdf):
    res = run(pdf(), pdf(pages=(("Dose 40 mg", 12, (0, 0, 0)),)))
    assert S.FAIL in statuses(res, "Text (embedded text layer)")
    assert any("20" in r["detail"] and "40" in r["detail"] for r in res["rows"] if r["check"] == "Text difference")
    assert S.FAIL in statuses(res, "Visual (pixel) comparison")


def test_size_difference(pdf):
    res = run(pdf(), pdf(size=(310, 200)))
    assert S.FAIL in statuses(res, "Page size")
    assert statuses(res, "Visual (pixel) comparison") == [S.NOT_VERIFIABLE]


def test_page_count_difference(pdf):
    two = pdf(pages=(("a", 12, (0, 0, 0)), ("b", 12, (0, 0, 0))))
    res = run(pdf(pages=(("a", 12, (0, 0, 0)),)), two)
    assert statuses(res, "Page count") == [S.FAIL]


def test_font_size_color_changes(pdf):
    res = run(pdf(), pdf(pages=(("Dose 20 mg", 14, (1, 0, 0)),)))
    detail = " ".join(r["detail"] for r in res["rows"] if r["check"] == "Text style/position")
    assert "size" in detail and "color" in detail


def test_font_resource_change(pdf):
    res = run(pdf(), pdf(font="tiro"))
    assert S.FAIL in statuses(res, "Font resources")


def test_non_embedded_font_needs_review(pdf):
    res = run(pdf(), pdf())
    assert S.REVIEW in statuses(res, "Font embedding")  # base-14 helv is not embedded


def test_embedded_font_detected():
    doc = pymupdf.open(); pg = doc.new_page()
    import glob, os
    ttf = next(iter(glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)), None)
    if not ttf:
        pytest.skip("no TTF available to embed")
    pg.insert_font(fontname="F0", fontfile=ttf)
    pg.insert_text((20, 50), "Hello", fontname="F0")
    a = P.analyze(doc.tobytes())
    assert a["pages"][0]["fonts"][0]["embedded"] is True


def test_image_difference(pdf):
    res = run(pdf(image=(1, 0, 0)), pdf(image=(0, 0, 1)))
    assert S.FAIL in statuses(res, "Visual (pixel) comparison")


def test_no_text_is_not_verifiable():
    doc = pymupdf.open(); doc.new_page(width=100, height=100)
    b = doc.tobytes()
    res = run(b, b)
    assert statuses(res, "Text") == [S.NOT_VERIFIABLE]


def test_annotation_difference(pdf):
    doc = pymupdf.open(stream=pdf(), filetype="pdf")
    doc[0].add_text_annot((50, 50), "check this")
    res = run(pdf(), doc.tobytes())
    assert statuses(res, "Annotations / comments") == [S.FAIL]


# --- barcodes
def test_barcode_decodes_and_compares():
    import zxingcpp
    import numpy as np
    from PIL import Image
    img = np.asarray(zxingcpp.write_barcode_to_image(zxingcpp.create_barcode('6224010704473', zxingcpp.BarcodeFormat.EAN13)))
    img = np.kron(img, np.ones((3, 3), dtype=img.dtype))
    from inspector import barcodes as B
    doc = pymupdf.open(); pg = doc.new_page(width=300, height=200)
    import io
    buf = io.BytesIO(); Image.fromarray(img).save(buf, "PNG")
    pg.insert_image(pymupdf.Rect(20, 20, 280, 120), stream=buf.getvalue())
    data = doc.tobytes()
    rows = B.compare_barcodes(lambda d: P.render_page(data, 0, d), lambda d: P.render_page(data, 0, d), 1)
    assert rows[0]["status"] == S.PASS and "6224010704473" in rows[0]["detail"]


def test_barcode_absent_not_verifiable(pdf):
    from inspector import barcodes as B
    rows = B.compare_barcodes(lambda d: P.render_page(pdf(), 0, d), lambda d: P.render_page(pdf(), 0, d), 1)
    assert rows[0]["status"] == S.NOT_VERIFIABLE


# --- dimensional spec
def test_spec_pass_fail_and_gaps(pdf):
    a = P.analyze(pdf(size=(283.465, 141.732)))  # 100 x 50 mm
    ok = '{"unit":"mm","source":"SPEC-1 v2","expected":{"width":100,"height":50},"tolerance":0.5}'
    assert [r["status"] for r in specs.check(a, ok)] == [S.PASS, S.PASS]
    bad = ok.replace('"width":100', '"width":105')
    assert S.FAIL in [r["status"] for r in specs.check(a, bad)]
    assert specs.check(a, "")[0]["status"] == S.NOT_CONFIGURED
    assert specs.check(a, '{"unit":"mm","source":"x","expected":{"width":100}}')[0]["status"] == S.NOT_CONFIGURED  # no tolerance
    assert specs.check(a, "{bad json")[0]["status"] == S.NOT_VERIFIABLE
    assert specs.check(a, '{"unit":"mm"}')[0]["status"] == S.NOT_VERIFIABLE


# --- report
def test_report_contains_disclaimer_and_unverified(pdf):
    res = run(pdf(), pdf())
    h = report.to_html(res, "ref.pdf", "cand.pdf")
    assert "not a certificate" in h.lower()
    assert "Not Implemented" in h and "sha256" in h
    import json
    j = json.loads(report.to_json(res, "ref.pdf", "cand.pdf"))
    assert "disclaimer" in j and j["counts"]["Fail"] == 0


# --- improvements: Arabic, colors, spot inks, ppi, boxes
def test_arabic_presentation_forms_normalized(pdf):
    from inspector.pdf_analysis import normalize_text
    assert normalize_text("\ufee3\ufeb4\ufe9f\ufee0") == "\u0645\u0633\u062c\u0644"  # isolated/initial forms -> base letters


def test_arabic_digit_style_flagged():
    assert pymupdf.Font("helv")  # sanity
    from inspector import compare as C
    a = {"pages": [{"spans": [{"text": "20"}], "text_extractable": True}]}
    b = {"pages": [{"spans": [{"text": "\u0662\u0660"}], "text_extractable": True}]}
    rows = C.compare_text(a, b, 1)
    assert any(r["check"] == "Digit style" and r["status"] == S.REVIEW for r in rows)


def test_vector_color_change(pdf):
    res = run(pdf(image=(1, 0, 0)), pdf(image=(0, 1, 0)))
    assert S.FAIL in statuses(res, "Vector fill colors")
    res2 = run(pdf(image=(1, 0, 0)), pdf(image=(1, 0, 0)))
    assert statuses(res2, "Vector fill colors") == [S.PASS]


def test_spot_color_names_compared():
    def mk(name):
        doc = pymupdf.open(); doc.new_page()
        x = doc.get_new_xref()
        doc.update_object(x, f"[/Separation /{name} /DeviceCMYK << /FunctionType 2 /Domain [0 1] /C0 [0 0 0 0] /C1 [0 1 1 0] /N 1 >>]")
        return doc.tobytes()
    a, b = P.analyze(mk("PANTONE#20186#20C")), P.analyze(mk("PANTONE#20300#20C"))
    assert "PANTONE 186 C" in a["spot_colors"]
    rows = C.compare_colors(a, b, 1)
    assert any(r["check"].startswith("Spot colors") and r["status"] == S.FAIL for r in rows)
    same = C.compare_colors(a, a, 1)
    assert any(r["check"].startswith("Spot colors") and r["status"] == S.PASS for r in same)


def test_spot_color_none_is_not_verifiable(pdf):
    rows = C.compare_colors(P.analyze(pdf()), P.analyze(pdf()), 1)
    assert any(r["check"].startswith("Spot colors") and r["status"] == S.NOT_VERIFIABLE for r in rows)


def test_image_ppi_difference():
    from PIL import Image
    import io
    def mk(box):
        buf = io.BytesIO(); Image.new("RGB", (300, 300), "white").save(buf, "PNG")
        doc = pymupdf.open(); pg = doc.new_page(width=300, height=300)
        pg.insert_image(pymupdf.Rect(*box), stream=buf.getvalue())
        return doc.tobytes()
    a, b = P.analyze(mk((0, 0, 72, 72))), P.analyze(mk((0, 0, 144, 144)))
    rows = C.compare_image_resolution(a, b, 1)
    assert rows[0]["status"] == S.FAIL
    assert C.compare_image_resolution(a, a, 1)[0]["status"] == S.PASS


def test_spec_uses_named_box():
    doc = pymupdf.open(); pg = doc.new_page(width=300, height=200)
    doc.xref_set_key(pg.xref, "TrimBox", "[0 0 283.465 141.732]")  # 100 x 50 mm
    a = P.analyze(doc.tobytes())
    spec = '{"unit":"mm","source":"S","box":"TrimBox","expected":{"width":100,"height":50},"tolerance":0.1}'
    assert [r["status"] for r in specs.check(a, spec)] == [S.PASS, S.PASS]
    missing = spec.replace("TrimBox", "BleedBox")
    assert specs.check(a, missing)[0]["status"] == S.NOT_VERIFIABLE


def test_dimension_summary_in_mm(pdf):
    rows = C.dimension_summary(P.analyze(pdf(size=(283.465, 141.732))))
    assert any("100.00 x 50.00 mm" in r["detail"] for r in rows)


# --- v0.3.0 checks
def blank_pdf(rotation=0, title=None):
    doc = pymupdf.open(); pg = doc.new_page(width=300, height=200)
    if rotation:
        pg.set_rotation(rotation)
    if title:
        doc.set_metadata({"title": title})
    return doc.tobytes()


def test_text_layer_missing_in_candidate(pdf):
    res = run(pdf(), blank_pdf())
    assert statuses(res, "Text layer") == [S.FAIL]


def test_text_layer_absent_in_both_needs_review():
    res = run(blank_pdf(), blank_pdf())
    assert statuses(res, "Text layer") == [S.REVIEW]


def test_text_layer_present_passes(pdf):
    assert statuses(run(pdf(), pdf()), "Text layer") == [S.PASS]


def test_rotation_difference_fails():
    assert statuses(run(blank_pdf(0), blank_pdf(90)), "Page rotation") == [S.FAIL]
    assert statuses(run(blank_pdf(0), blank_pdf(0)), "Page rotation") == [S.PASS]


def test_unembedded_font_needs_review(pdf):
    res = run(pdf(), pdf())  # built-in Helvetica is not embedded
    assert S.REVIEW in statuses(res, "Font embedding")


def test_metadata_title_difference_needs_review():
    res = run(blank_pdf(title="A"), blank_pdf(title="B"))
    assert statuses(res, "Document metadata") == [S.REVIEW]
    assert statuses(run(blank_pdf(title="A"), blank_pdf(title="A")), "Document metadata") == [S.PASS]


def test_findings_sorted_failures_first(pdf):
    res = run(pdf(), pdf(pages=(("Dose 25 mg", 12, (0, 0, 0)),)))
    rows = report.sorted_rows(res["rows"])
    first_pass = next(i for i, r in enumerate(rows) if r["status"] == S.PASS)
    assert all(r["status"] != S.PASS for r in rows[:first_pass]) and rows[0]["status"] == S.FAIL


def test_csv_has_bom_and_all_rows(pdf):
    res = run(pdf(), pdf())
    out = report.to_csv(res)
    assert out.startswith("\ufeff") and out.count("\n") >= len(res["rows"])


def test_html_report_embeds_title_overlay_and_escapes(pdf):
    res, ov = engine.run(pdf(), pdf(pages=(("<b>25</b> mg", 12, (0, 0, 0)),)), do_barcode=False)
    page = report.to_html(res, "<ref>.pdf", "cand.pdf", ov)
    assert report.TITLE in page and "data:image/png;base64," in page
    assert "&lt;ref&gt;.pdf" in page and "<b>25</b>" not in page


def test_corrupt_bytes_rejected_cleanly():
    with pytest.raises(UnsupportedPDF):
        engine.run(b"not a pdf", b"not a pdf")
