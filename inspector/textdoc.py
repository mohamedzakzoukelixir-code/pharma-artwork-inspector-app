"""Text-document checks: wording, font, size, bold/italic/underline, colour, numbering, tables, codes.

Everything is read from the PDF text layer (no OCR). When a page has few or no text-layer words but many
vector paths (outlined text), word-level checks cannot run: the page gets a vector outline comparison
instead, which detects any glyph shape or position change but cannot say which word changed.
"""
import difflib
import re
from collections import Counter
import pymupdf
from . import status as S
from .status import make
from .pdf_analysis import normalize_text

TOL_PT = 0.5
TOL_SIZE = 0.05
MAX_ROWS = 150
CODE_RE = re.compile(r"\b(?:[A-Za-z]{1,5}\d{4,}(?:[-/]\d+)*|\d{8,})\b")
NUM_RE = re.compile(r"^\s*(\(?\d{1,3}(?:\.\d{1,3})*[.)]?|\(?[A-Za-z][.)]|[\u2022\u25cf\u25aa\u2013\-*])\s+(?=\S)")
RED, ORANGE, MAGENTA, BLUE = (230, 20, 20), (240, 140, 0), (200, 0, 200), (20, 90, 220)


def _family(font):
    f = font.split("+")[-1]
    return re.sub(r"[-,](Bold|Italic|Oblique|BoldItalic|BoldOblique|Regular|MT|PS)+.*$", "", f, flags=re.I)


def _style(font, flags):
    f = font.lower()
    bold = bool(flags & 16) or "bold" in f or "black" in f or "heavy" in f
    italic = bool(flags & 2) or "italic" in f or "oblique" in f
    return bold, italic


def _underlines(draws):
    out = []
    for d in draws:
        for it in d["items"]:
            if it[0] == "l":
                p, q = it[1], it[2]
                if abs(p[1] - q[1]) < 0.6:
                    out.append((min(p[0], q[0]), max(p[0], q[0]), (p[1] + q[1]) / 2))
            elif it[0] == "re":
                r = it[1]
                if r[3] - r[1] < 1.6 and r[2] - r[0] > 2:
                    out.append((r[0], r[2], (r[1] + r[3]) / 2))
    return out


def _underlined(bbox, lines):
    x0, y0, x1, y1 = bbox
    w = max(x1 - x0, 0.01)
    for a, b, y in lines:
        if y1 - 3.5 <= y <= y1 + 1.5:
            ov = min(x1, b) - max(x0, a)
            if ov / w >= 0.6:
                return True
    return False


def _outline_keys(draws):
    keys = []
    for d in draws:
        r = d["rect"]
        f = d.get("fill")
        keys.append((round(r[0] * 2), round(r[1] * 2), round(r[2] * 2), round(r[3] * 2), len(d["items"]),
                     tuple(round(v, 2) for v in f) if f else None))
    return keys


def extract(data):
    """Per-page text-document facts. Not JSON-stored in the main analysis (kept in memory)."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    pages = []
    for page in doc:
        draws = page.get_cdrawings()
        ul = _underlines(draws)
        words, lines = [], []
        raw = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP, sort=True)
        for block in raw["blocks"]:
            for line in block.get("lines", []):
                parts = []
                for sp in line["spans"]:
                    bold, italic = _style(sp["font"], sp["flags"])
                    cur, cb = "", None
                    def flush():
                        nonlocal cur, cb
                        if cur.strip():
                            bb = tuple(cb)
                            words.append({"text": normalize_text(cur), "font": _family(sp["font"]), "face": sp["font"].split("+")[-1],
                                          "size": round(sp["size"], 2), "bold": bold, "italic": italic,
                                          "underline": _underlined(bb, ul), "color": "#%06x" % sp["color"],
                                          "super": bool(sp["flags"] & 1), "bbox": bb, "line": len(lines)})
                        cur, cb = "", None
                    for ch in sp["chars"]:
                        if ch["c"].isspace():
                            flush(); continue
                        cur += ch["c"]
                        b = ch["bbox"]
                        cb = list(b) if cb is None else [min(cb[0], b[0]), min(cb[1], b[1]), max(cb[2], b[2]), max(cb[3], b[3])]
                    flush()
                    parts.append("".join(c["c"] for c in sp["chars"]))
                txt = normalize_text("".join(parts)).strip()
                if txt:
                    lines.append({"text": txt, "bbox": tuple(line["bbox"])})
        tables = []
        if len(draws) > 600:
            tables = "skipped"
        else:
          try:
            for t in page.find_tables().tables:
                cells = t.extract()
                tables.append({"bbox": tuple(t.bbox), "rows": len(cells), "cols": max((len(r) for r in cells), default=0),
                               "cells": [[normalize_text(c or "").strip() for c in r] for r in cells]})
          except Exception:
            tables = None
        pages.append({"w": page.rect.width, "h": page.rect.height, "words": words, "lines": lines, "tables": tables,
                      "outlines": _outline_keys(draws)})
    doc.close()
    return pages


def _hl(bb, color, s, pad=2):
    return {"x": int(bb[0] * s) - pad, "y": int(bb[1] * s) - pad, "w": int((bb[2] - bb[0]) * s) + 2 * pad,
            "h": int((bb[3] - bb[1]) * s) + 2 * pad, "color": color}


def _ctx(words, i):
    return " ".join(w["text"] for w in words[max(0, i - 3):i])


def compare(ref_data, cand_data, n, dpi=100):
    """Returns (rows, highlights) where highlights = {page: ([ref regions], [cand regions])} in pixels at dpi."""
    A, B = extract(ref_data), extract(cand_data)
    rows, hl, thin = [], {}, []
    s = dpi / 72
    for pi in range(n):
        a, b = A[pi], B[pi]
        pg = pi + 1
        ra, rb = [], []
        wa, wb = a["words"], b["words"]
        # --- outlined / image-only page detection
        few = max(len(wa), len(wb)) < 15 and max(len(a["outlines"]), len(b["outlines"])) > 150
        if few or (len(a["outlines"]) > 400 and len(wa) < 80):
            rows.append(make("Text document: outlined text", S.REVIEW,
                             f"Few text-layer words ({len(wa)} Reference, {len(wb)} Candidate) but many vector paths ({len(a['outlines'])}/{len(b['outlines'])}). "
                             "Body text is probably converted to outlines: wording, font, size, bold and underline CANNOT be read as text. "
                             "Compared by vector outline geometry instead (below) and by visual diff. OCR is used only on changed regions (see OCR rows).", pg))
        outlined = few or (len(a["outlines"]) > 400 and len(wa) < 80)
        if outlined or max(len(wa), len(wb)) < 15:
            thin.append(pg)
        # --- wording
        if wa or wb:
            sm = difflib.SequenceMatcher(None, [w["text"] for w in wa], [w["text"] for w in wb], autojunk=False)
            ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
            if not ops:
                rows.append(make("Wording (word by word)", S.REVIEW if outlined else S.PASS,
                                 f"{len(wa)} text-layer words identical, including punctuation, case and digits" + (". ONLY these words were read: the outlined body text is not verified as wording" if outlined else ""), pg))
            else:
                rows.append(make("Wording (word by word)", S.FAIL, f"{len(ops)} difference(s) in {len(wa)} Reference / {len(wb)} Candidate words", pg))
                for k, (op, i1, i2, j1, j2) in enumerate(ops):
                    for w in wa[i1:i2]: ra.append(_hl(w["bbox"], RED, s))
                    for w in wb[j1:j2]: rb.append(_hl(w["bbox"], RED, s))
                    if k < MAX_ROWS:
                        kind = {"replace": "changed", "delete": "missing in Candidate", "insert": "added in Candidate"}[op]
                        rows.append(make("Wording difference", S.FAIL,
                                         f"{kind}. After '{_ctx(wa, i1) or _ctx(wb, j1) or '(start)'}': Reference '{' '.join(w['text'] for w in wa[i1:i2]) or '-'}' | Candidate '{' '.join(w['text'] for w in wb[j1:j2]) or '-'}'", pg))
                if len(ops) > MAX_ROWS:
                    rows.append(make("Wording difference", S.FAIL, f"{len(ops) - MAX_ROWS} more difference(s) not listed; see highlights and JSON", pg))
            # --- style of matching words
            bad = Counter()
            shown = 0
            for op, i1, i2, j1, j2 in sm.get_opcodes():
                if op != "equal":
                    continue
                for k in range(i2 - i1):
                    p, q = wa[i1 + k], wb[j1 + k]
                    d = []
                    if p["font"] != q["font"]: d.append(("Font family", f"{p['face']} -> {q['face']}"))
                    if abs(p["size"] - q["size"]) > TOL_SIZE: d.append(("Font size", f"{p['size']} -> {q['size']} pt"))
                    if p["bold"] != q["bold"]: d.append(("Bold", f"{'bold' if p['bold'] else 'regular'} -> {'bold' if q['bold'] else 'regular'}"))
                    if p["italic"] != q["italic"]: d.append(("Italic", f"{'italic' if p['italic'] else 'upright'} -> {'italic' if q['italic'] else 'upright'}"))
                    if p["underline"] != q["underline"]: d.append(("Underline", f"{'underlined' if p['underline'] else 'none'} -> {'underlined' if q['underline'] else 'none'}"))
                    if p["super"] != q["super"]: d.append(("Superscript", f"{p['super']} -> {q['super']}"))
                    if p["color"] != q["color"]: d.append(("Text colour", f"{p['color']} -> {q['color']} (RGB; ICC/spot not evaluated)"))
                    for kind, det in d:
                        bad[kind] += 1
                        if shown < MAX_ROWS:
                            shown += 1
                            rows.append(make(f"Format: {kind}", S.FAIL, f"'{p['text'][:40]}': {det}", pg))
                    if d:
                        ra.append(_hl(p["bbox"], ORANGE, s)); rb.append(_hl(q["bbox"], ORANGE, s))
            matched = sum(i2 - i1 for op, i1, i2, j1, j2 in sm.get_opcodes() if op == "equal")
            if not bad:
                rows.append(make("Format (font, size, bold, italic, underline, colour)", S.REVIEW if outlined else S.PASS,
                                 ("Outlined body NOT checked. " if outlined else "") + f"{matched} matching words: same font family, size (+-{TOL_SIZE} pt), bold, italic, underline and colour. Underline is detected from thin lines under the text.", pg))
            else:
                rows.append(make("Format (font, size, bold, italic, underline, colour)", S.FAIL,
                                 f"{sum(bad.values())} format difference(s): " + ", ".join(f"{k} x{v}" for k, v in bad.items()), pg))
            if shown >= MAX_ROWS:
                rows.append(make("Format difference", S.FAIL, "More format differences exist than listed; see highlights", pg))
        else:
            rows.append(make("Wording (word by word)", S.NOT_VERIFIABLE, "No text layer on this page in either file. OCR is used only on changed regions (see OCR rows).", pg))
        # --- numbering
        na = [(m.group(1).strip(), ln["text"][:40]) for ln in a["lines"] for m in [NUM_RE.match(ln["text"])] if m]
        nb = [(m.group(1).strip(), ln["text"][:40]) for ln in b["lines"] for m in [NUM_RE.match(ln["text"])] if m]
        if na or nb:
            la, lb = [x[0] for x in na], [x[0] for x in nb]
            if la == lb:
                rows.append(make("Numbering / bullets", S.PASS, f"{len(la)} numbered or bulleted line(s), identical sequence", pg))
            else:
                sm2 = difflib.SequenceMatcher(None, la, lb, autojunk=False)
                dd = [f"Reference {la[i1:i2] or '-'} vs Candidate {lb[j1:j2] or '-'}" for op, i1, i2, j1, j2 in sm2.get_opcodes() if op != "equal"]
                rows.append(make("Numbering / bullets", S.FAIL, "; ".join(dd[:10]), pg))
            for label, lst in (("Reference", la), ("Candidate", lb)):
                nums = [tuple(int(t) for t in re.findall(r"\d+", x)) for x in lst if re.fullmatch(r"\(?\d{1,3}(?:\.\d{1,3})*[.)]?", x)]
                for p, q in zip(nums, nums[1:]):
                    if len(p) == len(q) and p[:-1] == q[:-1] and q[-1] not in (p[-1] + 1, 1) and q[-1] != p[-1]:
                        rows.append(make("Numbering continuity", S.REVIEW, f"{label}: numbering jumps from {'.'.join(map(str, p))} to {'.'.join(map(str, q))}", pg))
                        break
        # --- tables
        if a["tables"] == "skipped" or b["tables"] == "skipped":
            rows.append(make("Tables", S.NOT_VERIFIABLE, "Page is vector-heavy (outlined text): ruled-table detection was skipped for speed. Check tables visually.", pg))
        elif a["tables"] is None or b["tables"] is None:
            rows.append(make("Tables", S.NOT_VERIFIABLE, "Table detection failed on this page", pg))
        elif not a["tables"] and not b["tables"]:
            rows.append(make("Tables", S.NOT_VERIFIABLE, "No ruled tables detected in either file (borderless or outlined tables are not detected)", pg))
        else:
            ta, tb = a["tables"], b["tables"]
            if len(ta) != len(tb):
                rows.append(make("Tables", S.FAIL, f"Table count: Reference {len(ta)}, Candidate {len(tb)}", pg))
                for t in ta[len(tb):]: ra.append(_hl(t["bbox"], BLUE, s))
                for t in tb[len(ta):]: rb.append(_hl(t["bbox"], BLUE, s))
            for k, (x, y) in enumerate(zip(ta, tb), 1):
                if (x["rows"], x["cols"]) != (y["rows"], y["cols"]):
                    rows.append(make(f"Table {k} structure", S.FAIL, f"Reference {x['rows']}x{x['cols']}, Candidate {y['rows']}x{y['cols']} (rows x columns)", pg))
                    ra.append(_hl(x["bbox"], BLUE, s)); rb.append(_hl(y["bbox"], BLUE, s))
                    continue
                diffs = [(r, c, x["cells"][r][c], y["cells"][r][c]) for r in range(x["rows"]) for c in range(min(x["cols"], len(x["cells"][r]), len(y["cells"][r])))
                         if x["cells"][r][c] != y["cells"][r][c]]
                if diffs:
                    rows.append(make(f"Table {k} content", S.FAIL, f"{len(diffs)} cell(s) differ", pg))
                    for r, c, p, q in diffs[:MAX_ROWS]:
                        rows.append(make(f"Table {k} cell r{r + 1}c{c + 1}", S.FAIL, f"Reference '{p}' | Candidate '{q}'", pg))
                    ra.append(_hl(x["bbox"], BLUE, s)); rb.append(_hl(y["bbox"], BLUE, s))
                else:
                    rows.append(make(f"Table {k}", S.PASS, f"{x['rows']}x{x['cols']} cells, all text identical", pg))
        # --- codes and footer
        ca = Counter(m for ln in a["lines"] for m in CODE_RE.findall(ln["text"]))
        cb = Counter(m for ln in b["lines"] for m in CODE_RE.findall(ln["text"]))
        if ca or cb:
            if ca == cb:
                rows.append(make("Codes (item / batch / document codes)", S.PASS, "Same codes: " + ", ".join(sorted(ca)), pg))
            else:
                rows.append(make("Codes (item / batch / document codes)", S.FAIL,
                                 f"Only in Reference: {sorted((ca - cb).elements()) or '-'}; only in Candidate: {sorted((cb - ca).elements()) or '-'}", pg))
                for ws, rr, cnt in ((wa, ra, cb), (wb, rb, ca)):
                    for w in ws:
                        if CODE_RE.search(w["text"]) and CODE_RE.search(w["text"]).group(0) not in cnt:
                            rr.append(_hl(w["bbox"], MAGENTA, s))
        else:
            rows.append(make("Codes (item / batch / document codes)", S.NOT_VERIFIABLE, "No code-like text found in the text layer (may be outlined or an image)", pg))
        def foot(pg_):
            lim = pg_["h"] * 0.88
            return [ln["text"] for ln in pg_["lines"] if ln["bbox"][1] >= lim]
        fa, fb = foot(a), foot(b)
        if fa or fb:
            rows.append(make("Footer text (bottom 12% of page)", S.PASS if fa == fb else S.FAIL,
                             f"{len(fa)} line(s) identical" if fa == fb else f"Reference {fa} | Candidate {fb}", pg))
        else:
            rows.append(make("Footer text (bottom 12% of page)", S.NOT_VERIFIABLE, "No text-layer text in the footer area of either file", pg))
        # --- vector outline geometry (detects changes in outlined text and artwork)
        oa, ob = Counter(a["outlines"]), Counter(b["outlines"])
        if oa or ob:
            if oa == ob:
                rows.append(make("Vector outline geometry", S.PASS, f"{sum(oa.values())} paths identical in shape, position (0.5 pt grid) and fill", pg))
            else:
                da, db = oa - ob, ob - oa
                rows.append(make("Vector outline geometry", S.FAIL,
                                 f"{sum(da.values())} path(s) only in Reference, {sum(db.values())} only in Candidate (of {sum(oa.values())}/{sum(ob.values())}). Outlined text shifted, changed or removed. Page sizes: {a['w']:.1f}x{a['h']:.1f} vs {b['w']:.1f}x{b['h']:.1f} pt", pg))
                for keys, rr in ((da, ra), (db, rb)):
                    for k in list(keys.elements())[:3000]:
                        rr.append(_hl([k[0] / 2, k[1] / 2, k[2] / 2, k[3] / 2], MAGENTA, s, 1))
        hl[pg] = (ra, rb)
    return rows, hl, thin
