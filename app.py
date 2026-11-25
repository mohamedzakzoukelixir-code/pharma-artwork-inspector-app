import io
import json
import streamlit as st
from PIL import ImageDraw
from inspector import engine, report, specs, status as S
from inspector.pdf_analysis import UnsupportedPDF

st.set_page_config(page_title="Elixir Pharma - Quality Assurance Products Artwork AI Verification", layout="wide")
st.title("Elixir Pharma - Quality Assurance Products Artwork AI Verification")
st.warning("Inspection aid only. Not GMP-validated, not a release approval. Human review and sign-off are mandatory.")

with st.sidebar:
    st.header("Settings")
    dpi = st.select_slider("Render dpi", [72, 100, 150, 200], value=100)
    thr = st.select_slider("Pixel difference threshold (0-255)", [16, 24, 40, 70], value=40)
    do_bc = st.checkbox("Decode barcodes (slower)", True)
    st.caption("Packaging material profile: Not Configured")
    spec_text = st.text_area("Dimensional spec (JSON, optional)", height=160, placeholder=json.dumps(specs.EXAMPLE, indent=2))

c1, c2 = st.columns(2)
ref = c1.file_uploader("Reference Artwork (PDF)", type="pdf", key="ref")
cand = c2.file_uploader("Candidate Artwork (PDF)", type="pdf", key="cand")

if st.button("Run inspection", disabled=not (ref and cand), type="primary"):
    try:
        with st.spinner("Inspecting..."):
            res, overlays = engine.run(ref.getvalue(), cand.getvalue(), spec_text, dpi, thr, do_bc)
        st.session_state["res"] = (res, overlays, ref.name, cand.name)
    except UnsupportedPDF as exc:
        st.error(f"Cannot inspect: {exc}")
        st.session_state.pop("res", None)

if "res" in st.session_state:
    res, overlays, rn, cn = st.session_state["res"]
    box = st.error if res["counts"][S.FAIL] else st.warning
    box(res["overall"])
    cols = st.columns(len(S.ALL))
    for col, s in zip(cols, S.ALL):
        col.metric(s, res["counts"][s])
    f_status = st.multiselect("Filter by status", S.ALL, default=[s for s in S.ALL if s != S.PASS])
    rows = [r for r in res["rows"] if r["status"] in f_status]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    for page, (ov, regions) in overlays.items():
        st.subheader(f"Page {page} visual differences")
        im = ov.copy()
        d = ImageDraw.Draw(im)
        for r in regions:
            d.rectangle([r["x"] - 3, r["y"] - 3, r["x"] + r["w"] + 3, r["y"] + r["h"] + 3], outline=(255, 0, 0), width=2)
        st.image(im, caption="Red = changed pixels (RGB render). Not a colour measurement.", use_container_width=True)
    st.download_button("Download report (HTML)", report.to_html(res, rn, cn), "inspection_report.html", "text/html")
    st.download_button("Download report (JSON)", report.to_json(res, rn, cn), "inspection_report.json", "application/json")
    st.caption(report.DISCLAIMER)
