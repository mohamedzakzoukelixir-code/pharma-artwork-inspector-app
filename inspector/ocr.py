"""OCR of changed regions on pages whose text is outlined or image-only (no usable text layer).

OCR output is a reading of pixels, not the PDF's own text. Every result from here is labelled OCR and shows
the engine's confidence. OCR can never prove font, size, bold or underline, so those stay unverified.
Only regions where the visual comparison found differences are read, which keeps run time bounded.
"""
import difflib
import os
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
import pymupdf
from PIL import Image
from . import status as S
from .status import make

OCR_DPI = 200
PAD = 30            # px at OCR_DPI around a changed region
MAX_BAND = 700      # px tall bands
MAX_CROPS = 14      # per page
BUDGET_S = 170      # total OCR time budget
CONF_OK = 70


def available():
    return shutil.which("tesseract") is not None


def languages():
    if not available():
        return None
    try:
        out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=20).stdout.split()
    except Exception:
        return None
    langs = [l for l in ("eng", "ara") if l in out]
    return "+".join(langs) or None


def _render(data, idx):
    doc = pymupdf.open(stream=data, filetype="pdf")
    pix = doc[idx].get_pixmap(dpi=OCR_DPI, alpha=False, colorspace=pymupdf.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    doc.close()
    return img


def _ocr_crop(img, box, lang):
    """Returns list of words {text, conf, bbox(x0,y0,x1,y1 in page px at OCR_DPI)}."""
    x0, y0, x1, y1 = box
    crop = img.crop(box)
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "c.png")
        crop.save(path)
        try:
            r = subprocess.run(["tesseract", path, "stdout", "-l", lang, "--psm", "6", "tsv"], capture_output=True, text=True,
                               timeout=90, env={**os.environ, "OMP_THREAD_LIMIT": "1"})
        except Exception:
            return None
    words = []
    for line in r.stdout.splitlines()[1:]:
        p = line.split("\t")
        if len(p) < 12 or not p[11].strip():
            continue
        try:
            conf = float(p[10]); l, t, w, h = (int(p[i]) for i in (6, 7, 8, 9))
        except ValueError:
            continue
        if conf < 0:
            continue
        words.append({"text": p[11].strip(), "conf": conf, "bbox": (x0 + l, y0 + t, x0 + l + w, y0 + t + h)})
    return words


def _boxes(regions, scale, size):
    """Merge changed regions (px at render dpi) into padded OCR boxes at OCR_DPI, split into bands."""
    W, H = size
    boxes = []
    for r in regions:
        boxes.append([max(0, int(r["x"] * scale) - PAD), max(0, int(r["y"] * scale) - PAD),
                      min(W, int((r["x"] + r["w"]) * scale) + PAD), min(H, int((r["y"] + r["h"]) * scale) + PAD)])
    merged = True
    while merged:
        merged = False
        out = []
        for b in boxes:
            for o in out:
                if b[0] <= o[2] + PAD and b[2] >= o[0] - PAD and b[1] <= o[3] + PAD and b[3] >= o[1] - PAD:
                    o[0], o[1], o[2], o[3] = min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3])
                    merged = True
                    break
            else:
                out.append(list(b))
        boxes = out
    final = []
    for b in boxes:
        y = b[1]
        while y < b[3]:
            final.append((b[0], y, b[2], min(b[3], y + MAX_BAND)))
            y += MAX_BAND
    final.sort(key=lambda b: (b[1], b[0]))
    return final


def compare(ref_bytes, cand_bytes, pages, regions_by_page, dpi):
    """pages: list of 1-based page numbers with thin text layers. regions_by_page: {page: [region dicts at dpi]}.
    Returns (rows, highlights {page: (ref_regions, cand_regions)} at dpi px)."""
    rows, hl = [], {}
    if not pages:
        return rows, hl
    lang = languages()
    if not lang:
        for pg in pages:
            rows.append(make("OCR wording of outlined text", S.NOT_VERIFIABLE, "OCR engine (tesseract) is not available on this server. Compare the highlighted pixel differences visually.", pg, "OCR"))
        return rows, hl
    t0 = time.time()
    s = dpi / OCR_DPI
    for pg in pages:
        regions = regions_by_page.get(pg) or []
        if not regions:
            rows.append(make("OCR wording of outlined text", S.REVIEW,
                             "No pixel differences were found, so no region was read by OCR. Wording was not read as text on this page; identical rendering is the only evidence.", pg, "OCR"))
            continue
        ia, ib = _render(ref_bytes, pg - 1), _render(cand_bytes, pg - 1)
        if ia.size != ib.size:
            rows.append(make("OCR wording of outlined text", S.NOT_VERIFIABLE, "Page sizes differ; OCR regions cannot be matched.", pg, "OCR"))
            continue
        boxes = _boxes(regions, OCR_DPI / dpi, ia.size)
        skipped = max(0, len(boxes) - MAX_CROPS)
        boxes = boxes[:MAX_CROPS]
        if time.time() - t0 > BUDGET_S:
            rows.append(make("OCR wording of outlined text", S.NOT_VERIFIABLE, "OCR time budget used up; remaining pages were not read.", pg, "OCR"))
            continue
        workers = max(1, min(4, os.cpu_count() or 1))
        with ThreadPoolExecutor(workers) as ex:
            ra = list(ex.map(lambda b: _ocr_crop(ia, b, lang), boxes))
            rb = list(ex.map(lambda b: _ocr_crop(ib, b, lang), boxes))
        ha, hb, diffs, confs, hints = [], [], 0, [], 0
        for k, (b, wa, wb) in enumerate(zip(boxes, ra, rb)):
            if wa is None or wb is None:
                rows.append(make("OCR wording of outlined text", S.NOT_VERIFIABLE, f"OCR failed on region {k + 1}", pg, "OCR"))
                continue
            confs += [w["conf"] for w in wa + wb]
            sm = difflib.SequenceMatcher(None, [w["text"] for w in wa], [w["text"] for w in wb], autojunk=False)
            for op, i1, i2, j1, j2 in sm.get_opcodes():
                if op == "equal":
                    for p, q in zip(wa[i1:i2], wb[j1:j2]):
                        hp, hq = p["bbox"][3] - p["bbox"][1], q["bbox"][3] - q["bbox"][1]
                        if hp > 14 and abs(hp - hq) / hp > 0.12 and min(p["conf"], q["conf"]) >= CONF_OK:
                            hints += 1
                            hb.append(_box(q["bbox"], s, (240, 140, 0))); ha.append(_box(p["bbox"], s, (240, 140, 0)))
                            if hints <= 20:
                                rows.append(make("OCR size hint", S.REVIEW, f"'{p['text']}': OCR box height {hp} -> {hq} px (hint only, OCR cannot measure font size)", pg, "OCR"))
                    continue
                ta = " ".join(w["text"] for w in wa[i1:i2]) or "-"
                tb = " ".join(w["text"] for w in wb[j1:j2]) or "-"
                ca = [w["conf"] for w in wa[i1:i2]]; cb = [w["conf"] for w in wb[j1:j2]]
                conf = min(ca + cb) if (ca + cb) else 0
                diffs += 1
                for w in wa[i1:i2]: ha.append(_box(w["bbox"], s, (230, 20, 20)))
                for w in wb[j1:j2]: hb.append(_box(w["bbox"], s, (230, 20, 20)))
                if not wa[i1:i2]: ha.append(_box((b[0] + 0, b[1], b[0] + 1, b[1] + 1), s, (230, 20, 20)))
                if diffs <= 100:
                    rows.append(make("OCR wording difference", S.FAIL if conf >= CONF_OK else S.REVIEW,
                                     f"OCR-derived. Reference '{ta}' | Candidate '{tb}' (lowest word confidence {conf:.0f}%)"
                                     + ("" if conf >= CONF_OK else ". Low confidence: may be an OCR misread, check visually"), pg, "OCR"))
        mean = sum(confs) / len(confs) if confs else 0
        note = f"OCR ({lang}) read {len(boxes)} changed region(s), mean confidence {mean:.0f}%." + (f" {skipped} more region(s) not read (limit)." if skipped else "")
        if diffs:
            rows.append(make("OCR wording of outlined text", S.REVIEW, f"{diffs} word difference(s) found by OCR. {note} OCR is a reading of pixels: confirm each highlight visually.", pg, "OCR"))
        else:
            rows.append(make("OCR wording of outlined text", S.REVIEW, f"OCR found no word differences in the changed regions. {note} OCR cannot prove wording 100%.", pg, "OCR"))
        rows.append(make("Font, bold, underline of outlined text", S.NOT_VERIFIABLE, "Outlined or image-only text carries no font data and OCR cannot prove font, size, bold or underline. Compare the highlighted regions visually.", pg, "OCR"))
        hl[pg] = (ha, hb)
    return rows, hl


def _box(bb, s, color):
    return {"x": int(bb[0] * s) - 2, "y": int(bb[1] * s) - 2, "w": int((bb[2] - bb[0]) * s) + 4, "h": int((bb[3] - bb[1]) * s) + 4, "color": color}
