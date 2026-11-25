import pymupdf
from inspector import engine, status as S, textdoc


def _doc(variant):
    d = pymupdf.open()
    p = d.new_page(width=595, height=842)
    p.insert_text((50, 60), "1. Introduction", fontname="hebo", fontsize=14)
    p.insert_text((50, 90), "Store below 30 degrees in the original package.", fontname="helv", fontsize=11)
    p.insert_text((50, 110), "2. Dosage", fontname="helv", fontsize=11)
    p.insert_text((50, 130), "Take one tablet daily with water.", fontname="helv", fontsize=11)
    p.insert_text((50, 150), "Important warning", fontname="helv", fontsize=11)
    p.draw_line((50, 152), (130, 152), width=0.7)
    for r in range(3):
        for c in range(2):
            p.draw_rect(pymupdf.Rect(50 + c * 100, 200 + r * 25, 150 + c * 100, 225 + r * 25), width=0.8)
            p.insert_text((55 + c * 100, 217 + r * 25), f"R{r}C{c}", fontname="helv", fontsize=10)
    p.insert_text((50, 800), "PL010021-01", fontname="helv", fontsize=9)
    if variant == "same":
        pass
    else:
        pass
    return d


def _bytes(mod=None):
    d = pymupdf.open()
    p = d.new_page(width=595, height=842)
    m = mod or {}
    p.insert_text((50, 60), m.get("h", "1. Introduction"), fontname="hebo" if not m.get("nobold") else "helv", fontsize=14)
    p.insert_text((50, 90), m.get("t1", "Store below 30 degrees in the original package."), fontname="helv", fontsize=m.get("size", 11))
    p.insert_text((50, 110), m.get("n2", "2. Dosage"), fontname="helv", fontsize=11)
    p.insert_text((50, 130), "Take one tablet daily with water.", fontname=m.get("font", "helv"), fontsize=11)
    p.insert_text((50, 150), "Important warning", fontname="helv", fontsize=11)
    if not m.get("nounder"):
        p.draw_line((50, 152), (130, 152), width=0.7)
    for r in range(3):
        for c in range(2):
            p.draw_rect(pymupdf.Rect(50 + c * 100, 200 + r * 25, 150 + c * 100, 225 + r * 25), width=0.8)
            txt = m.get("cell", "R%dC%d" % (r, c)) if (r, c) == (1, 1) else "R%dC%d" % (r, c)
            p.insert_text((55 + c * 100, 217 + r * 25), txt, fontname="helv", fontsize=10)
    p.insert_text((50, 800), m.get("code", "PL010021-01"), fontname="helv", fontsize=9)
    out = d.tobytes()
    d.close()
    return out


def _rows(mod):
    res, ov = engine.run(_bytes(), _bytes(mod), None, 72, 40, False)
    return res, ov


def _fail(res, key):
    return [r for r in res["rows"] if r["status"] == S.FAIL and key in r["check"]]


def test_identical_text_doc_passes_text_checks():
    res, _ = _rows({})
    for key in ("Wording (word by word)", "Format (font", "Numbering", "Codes", "Footer text", "Vector outline"):
        rs = [r for r in res["rows"] if key in r["check"]]
        assert rs and all(r["status"] == S.PASS for r in rs), (key, rs)
    assert not res["counts"][S.FAIL]


def test_wording_change_and_highlight():
    res, ov = _rows({"t1": "Store below 25 degrees in the original package."})
    assert _fail(res, "Wording difference")
    hl = [k for k in ov if "Candidate (text" in str(k)]
    assert hl and ov[hl[0]][1]


def test_size_bold_underline_font_detected():
    assert any("Font size" in r["check"] for r in _rows({"size": 12})[0]["rows"] if r["status"] == S.FAIL)
    assert _fail(_rows({"nobold": 1})[0], "Bold")
    assert _fail(_rows({"nounder": 1})[0], "Underline")
    assert _fail(_rows({"font": "tiro"})[0], "Font family")


def test_numbering_table_and_code_detected():
    assert _fail(_rows({"n2": "3. Dosage"})[0], "Numbering")
    assert _fail(_rows({"cell": "XX"})[0], "Table 1")
    assert _fail(_rows({"code": "PL010021-02"})[0], "Codes")
    assert _fail(_rows({"code": "PL010021-02"})[0], "Footer")


def test_untextual_page_never_passes_wording():
    d = pymupdf.open(); d.new_page(width=300, height=300)
    b = d.tobytes()
    res, _ = engine.run(b, b, None, 72, 40, False)
    w = [r for r in res["rows"] if r["check"].startswith("Wording")]
    assert w and all(r["status"] == S.NOT_VERIFIABLE for r in w)


def test_highlight_pdf_and_html_report():
    from inspector import report
    res, ov = engine.run(_bytes(), _bytes({"t1": "Store below 25 degrees in the original package.", "size": 12, "cell": "XX", "code": "PL010021-02"}), None, 72, 40, False)
    pdf = report.highlights_pdf(ov)
    assert pdf and pdf[:4] == b"%PDF"
    assert "Highlighted" in report.to_html(res, "a.pdf", "b.pdf", ov) or "diff page" in report.to_html(res, "a.pdf", "b.pdf", ov)
