"""Structured report export. The report is not a certificate or release approval."""
import base64
import csv
import html
import io
import json

from PIL import ImageDraw

from . import status as S

TITLE = "Elixir Pharma - Quality Assurance Products Artwork AI Verification"
FOOTER_LINES = ("Inspection Aid Only",
                "Not GMP-validated and does not constitute release approval. Human review and sign-off are mandatory.",
                "Authorized, Verified, and Created By:",
                "Quality Assurance Supervisor",
                "Mohamed Mostafa Zakzouk")
DISCLAIMER = "\n".join(FOOTER_LINES)
BANNER = " ".join(FOOTER_LINES[:2])

COLORS = {S.PASS: "#17803d", S.FAIL: "#c62828", S.REVIEW: "#b26a00", S.NOT_VERIFIABLE: "#b26a00",
          S.NOT_CONFIGURED: "#555555", S.NOT_IMPLEMENTED: "#555555"}
ORDER = {S.FAIL: 0, S.REVIEW: 1, S.NOT_VERIFIABLE: 2, S.NOT_CONFIGURED: 3, S.NOT_IMPLEMENTED: 4, S.PASS: 5}


def sorted_rows(rows):
    """Failures first, then items needing a human, then limitations, then passes."""
    return sorted(rows, key=lambda r: (ORDER[r["status"]], r["page"] or 0))


def overlay_image(ov, regions):
    im = ov.copy()
    d = ImageDraw.Draw(im)
    for r in regions:
        d.rectangle([r["x"] - 3, r["y"] - 3, r["x"] + r["w"] + 3, r["y"] + r["h"] + 3], outline=(255, 0, 0), width=2)
    return im


def to_json(result, ref_name="Reference", cand_name="Candidate"):
    out = {k: v for k, v in result.items() if k != "analysis"}
    out.update({"title": TITLE, "reference_file": ref_name, "candidate_file": cand_name, "disclaimer": DISCLAIMER, "footer": list(FOOTER_LINES)})
    return json.dumps(out, indent=2, ensure_ascii=False)


def to_csv(result):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["page", "check", "status", "detail", "source"])
    for r in sorted_rows(result["rows"]):
        w.writerow([r["page"] or "", r["check"], r["status"], r["detail"], r["source"]])
    return "\ufeff" + buf.getvalue()  # BOM so Excel opens Arabic text correctly


def _png_b64(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def to_html(result, ref_name, cand_name, overlays=None):
    rows = "".join(
        f"<tr class='{r['status'].replace(' ', '-')}'><td>{html.escape(str(r['page'] or '-'))}</td><td>{html.escape(r['check'])}</td>"
        f"<td style='color:{COLORS[r['status']]};font-weight:700'>{html.escape(r['status'])}</td>"
        f"<td dir='auto'>{html.escape(r['detail'])}</td><td>{html.escape(str(r['source']))}</td></tr>" for r in sorted_rows(result["rows"]))
    cards = "".join(f"<div class='card' style='border-top:4px solid {COLORS[s]}'><b>{result['counts'][s]}</b><span>{html.escape(s)}</span></div>" for s in S.ALL)
    visuals = ""
    for page, (ov, regions) in (overlays or {}).items():
        visuals += (f"<h3>Page {page}: visual differences ({len(regions)} region(s))</h3>"
                    f"<img alt='diff page {page}' style='max-width:100%;border:1px solid #ccc' src='data:image/png;base64,{_png_b64(overlay_image(ov, regions))}'>"
                    "<p class='small'>Red boxes = changed pixels in an RGB render. Not a colour measurement.</p>")
    return f"""<!doctype html><meta charset=utf-8><title>{html.escape(TITLE)}: inspection report</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1b1b1b}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:5px 7px;font-size:13px;text-align:left;vertical-align:top}}th{{background:#f1f3f5}}
.cards{{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}}.card{{background:#f7f7f8;padding:8px 14px;min-width:110px}}
.card b{{display:block;font-size:22px}}.small{{font-size:12px;color:#555}}.footer{{font-size:13px;margin-top:12px}}.banner{{background:#fff4e5;border:1px solid #f0b34a;padding:8px 12px;margin:10px 0}}
@media print{{.card{{break-inside:avoid}}tr{{break-inside:avoid}}}}</style>
<h1>{html.escape(TITLE)}</h1><h2>Artwork inspection report</h2>
<div class='banner'>{html.escape(BANNER)}</div>
<p><b>Reference:</b> {html.escape(ref_name)} ({result['reference']['pages']} page(s), sha256 {result['reference']['sha256']})<br>
<b>Candidate:</b> {html.escape(cand_name)} ({result['candidate']['pages']} page(s), sha256 {result['candidate']['sha256']})<br>
<b>Generated:</b> {html.escape(result['generated'])}<br><b>Settings:</b> {html.escape(str(result['settings']))}</p>
<h2>{html.escape(result['overall'])}</h2><div class='cards'>{cards}</div>
{visuals}
<h3>All findings (failures first)</h3>
<table><tr><th>Page</th><th>Check</th><th>Status</th><th>Detail</th><th>Source</th></tr>{rows}</table>
<hr><div class='footer'><b>{html.escape(FOOTER_LINES[0])}</b><br>{html.escape(FOOTER_LINES[1])}<br><br>{html.escape(FOOTER_LINES[2])}<br><b>{html.escape(FOOTER_LINES[3])}</b><br><b>{html.escape(FOOTER_LINES[4])}</b></div>"""
