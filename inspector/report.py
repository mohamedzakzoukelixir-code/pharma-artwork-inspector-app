"""Structured report export. The report is not a certificate or release approval."""
import html
import json

DISCLAIMER = ("Inspection aid only. Not a GMP-validated system, not a certificate of approval and not a Release Approval. "
              "Human review and final sign-off remain mandatory.")


def to_json(result, ref_name="Reference", cand_name="Candidate"):
    out = {k: v for k, v in result.items() if k != "analysis"}
    out.update({"reference_file": ref_name, "candidate_file": cand_name, "disclaimer": DISCLAIMER})
    return json.dumps(out, indent=2, ensure_ascii=False)


def to_html(result, ref_name, cand_name):
    colors = {"Pass": "#17803d", "Fail": "#c62828", "Requires Human Review": "#b26a00", "Not Verifiable": "#b26a00",
              "Not Configured": "#555", "Not Implemented": "#555"}
    rows = "".join(
        f"<tr><td>{html.escape(str(r['page'] or '-'))}</td><td>{html.escape(r['check'])}</td>"
        f"<td style='color:{colors[r['status']]};font-weight:700'>{r['status']}</td><td>{html.escape(r['detail'])}</td>"
        f"<td>{html.escape(str(r['source']))}</td></tr>" for r in result["rows"])
    return f"""<!doctype html><meta charset=utf-8><title>Artwork inspection report</title>
<style>body{{font-family:sans-serif;margin:24px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:5px;font-size:13px;text-align:left;vertical-align:top}}</style>
<h1>Artwork inspection report</h1>
<p><b>Reference:</b> {html.escape(ref_name)} (sha256 {result['reference']['sha256'][:16]})<br>
<b>Candidate:</b> {html.escape(cand_name)} (sha256 {result['candidate']['sha256'][:16]})<br>
<b>Generated:</b> {result['generated']}<br><b>Settings:</b> {result['settings']}</p>
<h2>{html.escape(result['overall'])}</h2><p>{result['counts']}</p>
<table><tr><th>Page</th><th>Check</th><th>Status</th><th>Detail</th><th>Source</th></tr>{rows}</table>
<p><i>{DISCLAIMER}</i></p>"""
