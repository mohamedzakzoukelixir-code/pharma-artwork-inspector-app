"""Reference vs Candidate comparison. Each function returns result rows (see status.make)."""
import difflib
import numpy as np
from PIL import Image
from . import status as S
from .status import make

TOL_PT = 0.5          # geometry tolerance in PDF points (stated in the report)
TOL_SIZE = 0.05


def _words(page):
    # reading order from the PDF stream; Arabic order may differ from visual order
    return [w for sp in page["spans"] for w in sp["text"].split()]


def compare_pages_count(ref, cand):
    ok = ref["page_count"] == cand["page_count"]
    return [make("Page count", S.PASS if ok else S.FAIL, f"Reference {ref['page_count']}, Candidate {cand['page_count']}")]


def compare_dimensions(ref, cand, n):
    rows = []
    for i in range(n):
        a, b = ref["pages"][i], cand["pages"][i]
        ok = abs(a["width_pt"] - b["width_pt"]) <= TOL_PT and abs(a["height_pt"] - b["height_pt"]) <= TOL_PT
        rows.append(make("Page size", S.PASS if ok else S.FAIL,
                         f"Reference {a['width_pt']}x{a['height_pt']} pt, Candidate {b['width_pt']}x{b['height_pt']} pt (tolerance {TOL_PT} pt)", i + 1))
        rows.append(make("Orientation / rotation", S.PASS if (a["orientation"], a["rotation"]) == (b["orientation"], b["rotation"]) else S.FAIL,
                         f"Reference {a['orientation']}/{a['rotation']}, Candidate {b['orientation']}/{b['rotation']}", i + 1))
        for key in a["boxes"]:
            x, y = a["boxes"][key], b["boxes"][key]
            if x is None and y is None:
                rows.append(make(f"{key}", S.NOT_VERIFIABLE, "Not defined in either PDF", i + 1))
            elif x is None or y is None:
                rows.append(make(f"{key}", S.FAIL, f"Defined only in {'Candidate' if x is None else 'Reference'}: {x or y}", i + 1))
            else:
                ok = all(abs(p - q) <= TOL_PT for p, q in zip(x, y))
                rows.append(make(f"{key}", S.PASS if ok else S.FAIL, f"Reference {x}, Candidate {y}", i + 1))
    return rows


def compare_text(ref, cand, n):
    rows = []
    for i in range(n):
        a, b = ref["pages"][i], cand["pages"][i]
        if not a["text_extractable"] and not b["text_extractable"]:
            rows.append(make("Text", S.NOT_VERIFIABLE, "No extractable text (possibly outlined). OCR is not implemented.", i + 1))
            continue
        wa, wb = _words(a), _words(b)
        sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
        diffs = [(op, " ".join(wa[i1:i2]), " ".join(wb[j1:j2])) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]
        if not diffs:
            rows.append(make("Text (embedded text layer)", S.PASS, f"{len(wa)} words identical", i + 1))
        else:
            rows.append(make("Text (embedded text layer)", S.FAIL, f"{len(diffs)} difference(s)", i + 1))
            for op, ra, cb in diffs:
                rows.append(make("Text difference", S.FAIL, f"Reference: '{ra or '-'}' | Candidate: '{cb or '-'}'", i + 1))
        digs = lambda pg: {"arabic-indic" if "\u0660" <= ch <= "\u0669" else "western" for sp in pg["spans"] for ch in sp["text"] if ch.isdigit()}
        if digs(a) != digs(b):
            rows.append(make("Digit style", S.REVIEW, f"Reference uses {sorted(digs(a))}, Candidate uses {sorted(digs(b))} digits", i + 1))
        if any("\u0600" <= ch <= "\u06ff" or "\ufb50" <= ch <= "\ufeff" for sp in a["spans"] + b["spans"] for ch in sp["text"]):
            rows.append(make("Arabic text order", S.REVIEW, "Arabic found. Letter shapes are normalized (NFKC) before comparing; extracted word order may still differ from visual order. Check visually.", i + 1))
    return rows


def compare_fonts(ref, cand, n):
    rows = []
    for i in range(n):
        fa = {f["font"]: f for f in ref["pages"][i]["fonts"]}
        fb = {f["font"]: f for f in cand["pages"][i]["fonts"]}
        only_a, only_b = sorted(set(fa) - set(fb)), sorted(set(fb) - set(fa))
        if only_a or only_b:
            rows.append(make("Font resources", S.FAIL, f"Only in Reference: {only_a or '-'}; only in Candidate: {only_b or '-'}", i + 1))
        else:
            rows.append(make("Font resources", S.PASS if fa else S.NOT_VERIFIABLE, f"{len(fa)} font(s) identical" if fa else "No fonts found", i + 1))
        for name, f in {**fa, **fb}.items():
            if not f["embedded"]:
                std = f["type"] in ("Type1",) and "+" not in name
                rows.append(make("Font embedding", S.REVIEW,
                                 f"{name} is not embedded" + (" (possible standard PDF font)" if std else "") +
                                 ". Runtime font substitution cannot be verified from the file.", i + 1))
        if (fa or fb) and all(f["embedded"] for f in {**fa, **fb}.values()):
            rows.append(make("Font embedding", S.PASS, "All fonts embedded", i + 1))
    return rows


def compare_styles(ref, cand, n):
    rows = []
    for i in range(n):
        a, b = ref["pages"][i]["spans"], cand["pages"][i]["spans"]
        sm = difflib.SequenceMatcher(None, [s["text"] for s in a], [s["text"] for s in b], autojunk=False)
        pairs = [(a[i1 + k], b[j1 + k]) for op, i1, i2, j1, j2 in sm.get_opcodes() if op == "equal" for k in range(i2 - i1)]
        bad = 0
        for p, q in pairs:
            d = []
            if p["font"].split("+")[-1] != q["font"].split("+")[-1]:
                d.append(f"font {p['font']} -> {q['font']}")
            if abs(p["size"] - q["size"]) > TOL_SIZE:
                d.append(f"size {p['size']} -> {q['size']} pt")
            if p["color"] != q["color"]:
                d.append(f"color {p['color']} -> {q['color']} (RGB from PDF; ICC/spot not evaluated)")
            if any(abs(u - v) > TOL_PT for u, v in zip(p["bbox"], q["bbox"])):
                d.append(f"position {p['bbox']} -> {q['bbox']}")
            if d:
                bad += 1
                rows.append(make("Text style/position", S.FAIL, f"'{p['text'][:50]}': " + "; ".join(d), i + 1))
        if not pairs:
            rows.append(make("Text style/position", S.NOT_VERIFIABLE, "No matching text runs to compare", i + 1))
        elif not bad:
            rows.append(make("Text style/position", S.PASS, f"{len(pairs)} matching text runs, same font/size/color/position within {TOL_PT} pt", i + 1))
    return rows


def compare_images(ref, cand, n):
    rows = []
    for i in range(n):
        a, b = ref["pages"][i]["images"], cand["pages"][i]["images"]
        if any(x["hash"] is None for x in a + b):
            rows.append(make("Embedded images", S.NOT_VERIFIABLE, "Some images could not be decoded", i + 1))
            continue
        sa = sorted((x["width"], x["height"], x["hash"]) for x in a)
        sb = sorted((x["width"], x["height"], x["hash"]) for x in b)
        if sa == sb:
            rows.append(make("Embedded images", S.PASS, f"{len(a)} image(s), identical pixel data" if a else "No embedded raster images (artwork may be vector)", i + 1))
        else:
            rows.append(make("Embedded images", S.FAIL, f"Reference {len(a)} image(s), Candidate {len(b)}; pixel data differs", i + 1))
        va, vb = ref["pages"][i]["vector_drawings"], cand["pages"][i]["vector_drawings"]
        rows.append(make("Vector drawing count", S.PASS if va == vb else S.FAIL, f"Reference {va}, Candidate {vb}", i + 1))
    return rows


def pixel_diff(img_a: Image.Image, img_b: Image.Image, threshold: int = 40, min_area: int = 4):
    """Return (overlay RGB image, list of region dicts, changed_pixels). Sizes must match."""
    a, b = np.asarray(img_a, dtype=np.int16), np.asarray(img_b, dtype=np.int16)
    mask = np.abs(a - b).max(axis=2) > threshold
    changed = int(mask.sum())
    h, w = mask.shape
    cs = max(8, w // 90)
    gh, gw = -(-h // cs), -(-w // cs)
    grid = np.zeros((gh, gw), bool)
    ys, xs = np.nonzero(mask)
    grid[ys // cs, xs // cs] = True
    seen = np.zeros_like(grid)
    regions = []
    for gy in range(gh):
        for gx in range(gw):
            if not grid[gy, gx] or seen[gy, gx]:
                continue
            stack, cells = [(gy, gx)], []
            seen[gy, gx] = True
            while stack:
                y, x = stack.pop()
                cells.append((y, x))
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < gh and 0 <= nx < gw and grid[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
            y0 = min(c[0] for c in cells) * cs; y1 = min(h, (max(c[0] for c in cells) + 1) * cs)
            x0 = min(c[1] for c in cells) * cs; x1 = min(w, (max(c[1] for c in cells) + 1) * cs)
            px = int(mask[y0:y1, x0:x1].sum())
            if px >= min_area:
                regions.append({"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "pixels": px})
    regions.sort(key=lambda r: (r["y"], r["x"]))
    base = np.asarray(img_a.convert("L"), dtype=np.float32)
    ov = np.stack([255 - (255 - base) * 0.35] * 3, axis=2).astype(np.uint8)
    ov[mask] = (230, 20, 20)
    return Image.fromarray(ov), regions, changed


def compare_visual(img_pairs, dpi, threshold):
    """img_pairs: list of (page_no, ref_img, cand_img). Returns (rows, overlays)."""
    rows, overlays = [], {}
    for page, ia, ib in img_pairs:
        if ia.size != ib.size:
            rows.append(make("Visual (pixel) comparison", S.NOT_VERIFIABLE, f"Page sizes differ ({ia.size} vs {ib.size}); alignment not attempted, no verdict", page, "render"))
            continue
        ov, regions, changed = pixel_diff(ia, ib, threshold)
        overlays[page] = (ov, regions)
        if not regions:
            rows.append(make("Visual (pixel) comparison", S.PASS, f"0 changed pixels at {dpi} dpi, threshold {threshold}/255 (RGB render; differences below threshold or outside RGB not evaluated)", page, "render"))
        else:
            rows.append(make("Visual (pixel) comparison", S.FAIL, f"{len(regions)} region(s), {changed} pixel(s) differ at {dpi} dpi", page, "render"))
            for k, r in enumerate(regions, 1):
                rows.append(make(f"Visual region {k}", S.FAIL, f"x={r['x']} y={r['y']} w={r['w']} h={r['h']} px, {r['pixels']} changed px", page, "render"))
    return rows, overlays


def compare_annotations(ref, cand, n):
    rows = []
    for i in range(n):
        a = sorted((x["type"], x["content"]) for x in ref["pages"][i]["annotations"])
        b = sorted((x["type"], x["content"]) for x in cand["pages"][i]["annotations"])
        rows.append(make("Annotations / comments", S.PASS if a == b else S.FAIL,
                         f"Reference {len(a)}, Candidate {len(b)}" + ("" if a == b else f": Reference {a} vs Candidate {b}"), i + 1))
    return rows


def compare_colors(ref, cand, n):
    """Vector fill/stroke colors (exact RGB as converted by the PDF engine) and spot ink names.
    Tint values, ICC conversion and overprint are not evaluated."""
    rows = []
    for i in range(n):
        for kind, key in (("fill", "fill_colors"), ("stroke", "stroke_colors")):
            a, b = ref["pages"][i][key], cand["pages"][i][key]
            if not a and not b:
                rows.append(make(f"Vector {kind} colors", S.NOT_VERIFIABLE, "No vector colors found", i + 1))
                continue
            only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
            cnt = sorted(c for c in set(a) & set(b) if a[c] != b[c])
            if only_a or only_b or cnt:
                d = []
                if only_a: d.append(f"only in Reference: {only_a[:8]}")
                if only_b: d.append(f"only in Candidate: {only_b[:8]}")
                if cnt: d.append("usage count differs: " + ", ".join(f"{c} {a[c]}->{b[c]}" for c in cnt[:8]))
                rows.append(make(f"Vector {kind} colors", S.FAIL, "; ".join(d) + " (RGB values; not CMYK/ICC)", i + 1))
            else:
                rows.append(make(f"Vector {kind} colors", S.PASS, f"{len(a)} distinct colors, same usage counts (RGB values; not CMYK/ICC)", i + 1))
    sa, sb = set(ref.get("spot_colors", [])), set(cand.get("spot_colors", []))
    if not sa and not sb:
        rows.append(make("Spot colors (Separation/DeviceN names)", S.NOT_VERIFIABLE, "None found; Pantone names may be baked into RGB/CMYK or outlined", None))
    elif sa == sb:
        rows.append(make("Spot colors (Separation/DeviceN names)", S.PASS, "Same names: " + ", ".join(sorted(sa)) + ". Tint values not evaluated.", None))
    else:
        rows.append(make("Spot colors (Separation/DeviceN names)", S.FAIL, f"Only in Reference: {sorted(sa - sb) or '-'}; only in Candidate: {sorted(sb - sa) or '-'}", None))
    return rows


def compare_image_resolution(ref, cand, n):
    rows = []
    for i in range(n):
        a, b = ref["pages"][i]["image_ppi"], cand["pages"][i]["image_ppi"]
        if not a and not b:
            continue
        ka = sorted((x["w"], x["h"], round(x["ppi_x"]), round(x["ppi_y"])) for x in a)
        kb = sorted((x["w"], x["h"], round(x["ppi_x"]), round(x["ppi_y"])) for x in b)
        rows.append(make("Effective image resolution (ppi)", S.PASS if ka == kb else S.FAIL,
                         f"Reference {ka}, Candidate {kb} (w, h, ppi_x, ppi_y)" if ka != kb else f"{len(a)} image(s), same effective ppi", i + 1))
    return rows


def dimension_summary(analysis):
    """Human-readable box sizes in mm for the report (informational, no verdict)."""
    rows = []
    for p in analysis["pages"]:
        for key, box in p["boxes"].items():
            if box:
                rows.append(make(f"{key} size (info)", S.PASS, f"{(box[2]-box[0])*25.4/72:.2f} x {(box[3]-box[1])*25.4/72:.2f} mm ({box[2]-box[0]:.2f} x {box[3]-box[1]:.2f} pt)", p["index"]))
    return rows
