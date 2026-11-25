"""Native PDF extraction with PyMuPDF. Everything here is read from the PDF itself, not OCR."""
import hashlib
import re
import unicodedata
import pymupdf

BOX_KEYS = ("MediaBox", "CropBox", "TrimBox", "BleedBox", "ArtBox")


class UnsupportedPDF(Exception):
    pass


def normalize_text(t: str) -> str:
    """NFKC folds Arabic presentation forms (isolated/initial/medial/final shapes) back to base letters,
    so text extracted from outlined-shaped glyph runs becomes comparable and readable. Digits are NOT
    converted between Arabic-Indic and Western forms: a different digit set is reported as a difference."""
    return unicodedata.normalize("NFKC", t)


def _spot_colors(doc):
    """Names of Separation/DeviceN colorants found anywhere in the file (Pantone and other spot inks)."""
    names = set()
    for xref in range(1, doc.xref_length()):
        try:
            obj = doc.xref_object(xref, compressed=True)
        except Exception:
            continue
        if "/Separation" in obj or "/DeviceN" in obj:
            for m in re.finditer(r"/(?:Separation|DeviceN)\s*(?:\[\s*)?/?([^\s/\[\]<>()]+|\([^)]*\))", obj):
                names.add(m.group(1).strip("()").replace("#20", " "))
            for m in re.finditer(r"\[\s*/DeviceN\s*\[([^\]]*)\]", obj):
                names.update(n.replace("#20", " ") for n in re.findall(r"/([^\s/]+)", m.group(1)))
    return sorted(n for n in names if n and n not in ("DeviceCMYK", "DeviceRGB", "DeviceGray"))


def _rect(r):
    return [round(float(v), 3) for v in (r.x0, r.y0, r.x1, r.y1)]


def _page_boxes(doc, page):
    """Return each page box as [x0,y0,x1,y1] in PDF points, or None when the PDF does not define it."""
    boxes = {}
    for key in BOX_KEYS:
        val = None
        try:
            t, raw = doc.xref_get_key(page.xref, key)
            if t == "array":
                nums = [float(x) for x in raw.strip("[]").split()]
                if len(nums) == 4:
                    val = [round(v, 3) for v in nums]
            elif key == "CropBox" or key == "MediaBox":
                val = _rect(page.mediabox if key == "MediaBox" else page.cropbox)
        except Exception:
            val = None
        boxes[key] = val
    return boxes


def open_pdf(data: bytes):
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise UnsupportedPDF(f"Cannot open file as PDF: {exc}") from exc
    if doc.needs_pass:
        raise UnsupportedPDF("PDF is encrypted; password required")
    if doc.page_count == 0:
        raise UnsupportedPDF("PDF has no pages")
    return doc


def analyze(data: bytes):
    """Extract per-page facts. Returns a plain dict (JSON-serialisable)."""
    doc = open_pdf(data)
    out = {"sha256": hashlib.sha256(data).hexdigest(), "page_count": doc.page_count,
           "metadata": {k: v for k, v in (doc.metadata or {}).items() if v}, "pages": []}
    for i, page in enumerate(doc):
        info = {"index": i + 1, "rotation": page.rotation,
                "width_pt": round(page.rect.width, 3), "height_pt": round(page.rect.height, 3),
                "orientation": "landscape" if page.rect.width > page.rect.height else "portrait",
                "boxes": _page_boxes(doc, page)}
        spans = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for sp in line["spans"]:
                    if not sp["text"].strip():
                        continue
                    c = sp["color"]
                    spans.append({"text": normalize_text(sp["text"]), "raw_text": sp["text"], "font": sp["font"], "size": round(sp["size"], 3),
                                  "color": "#%06x" % c, "bbox": [round(v, 2) for v in sp["bbox"]]})
        info["spans"] = spans
        fonts = {}
        for f in page.get_fonts(full=True):
            xref, ext, ftype, basefont, name = f[0], f[1], f[2], f[3], f[4]
            clean = basefont.split("+", 1)[1] if "+" in basefont[:8] else basefont
            embedded = bool(xref) and ext not in ("n/a", "")
            fonts[clean] = {"font": clean, "type": ftype, "embedded": embedded,
                            "subset": "+" in basefont[:8]}
        info["fonts"] = sorted(fonts.values(), key=lambda x: x["font"])
        images = []
        for im in page.get_images(full=True):
            xref = im[0]
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if pix.alpha or pix.colorspace is None or pix.n > 3:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                digest = hashlib.sha256(pix.samples).hexdigest()[:16]
                images.append({"width": pix.width, "height": pix.height, "hash": digest})
            except Exception:
                images.append({"width": im[2], "height": im[3], "hash": None})
        info["images"] = images
        drawings = page.get_drawings()
        info["vector_drawings"] = len(drawings)
        fills, strokes = {}, {}
        for d in drawings:
            for key, store in (("fill", fills), ("color", strokes)):
                c = d.get(key)
                if c is not None:
                    hexv = "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in (c if len(c) == 3 else (c[0],) * 3))
                    store[hexv] = store.get(hexv, 0) + 1
        info["fill_colors"], info["stroke_colors"] = fills, strokes
        ppi = []
        for ii in page.get_image_info():
            bb = ii["bbox"]
            w_in, h_in = (bb[2] - bb[0]) / 72, (bb[3] - bb[1]) / 72
            if w_in > 0 and h_in > 0:
                ppi.append({"w": ii["width"], "h": ii["height"], "ppi_x": round(ii["width"] / w_in, 1), "ppi_y": round(ii["height"] / h_in, 1)})
        info["image_ppi"] = ppi
        info["annotations"] = [{"type": a.type[1], "content": a.info.get("content", "")}
                               for a in page.annots() or []]
        info["text_extractable"] = len(spans) > 0
        out["pages"].append(info)
    out["spot_colors"] = _spot_colors(doc)
    doc.close()
    return out


def render_page(data: bytes, index: int, dpi: int = 100):
    """Render a page to a PIL image (RGB)."""
    from PIL import Image
    doc = open_pdf(data)
    page = doc[index]
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return img
