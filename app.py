import json
import streamlit as st
from inspector import engine, report, specs, status as S
from inspector.pdf_analysis import UnsupportedPDF

TITLE = report.TITLE
st.set_page_config(page_title=TITLE, page_icon="🔍", layout="wide")
st.markdown("""<style>
.block-container{padding-top:2rem}
div[data-testid=stMetric]{background:#f7f7f8;border-radius:8px;padding:8px 12px;border-top:3px solid #bbb}
</style>""", unsafe_allow_html=True)
st.title(TITLE)
st.warning("Inspection aid only. Not GMP-validated, not a release approval. Human review and sign-off are mandatory.")

with st.sidebar:
    st.header("Settings")
    dpi = st.select_slider("Render dpi", [72, 100, 150, 200], value=100, help="Higher dpi finds smaller visual differences but is slower.")
    thr = st.select_slider("Pixel difference threshold (0-255)", [16, 24, 40, 70], value=40, help="Lower = more sensitive.")
    do_bc = st.checkbox("Decode barcodes (slower)", True)
    st.caption("Packaging material profile: Not Configured")
    spec_text = st.text_area("Dimensional spec (JSON, optional)", height=160, placeholder=json.dumps(specs.EXAMPLE, indent=2))
    st.caption("Uploaded files are processed in memory and are not stored by this app.")

c1, c2 = st.columns(2)
ref = c1.file_uploader("Reference Artwork (PDF)", type="pdf", key="ref")
cand = c2.file_uploader("Candidate Artwork (PDF)", type="pdf", key="cand")
if not (ref and cand):
    st.info("Upload both PDFs, then press Run inspection.")

if st.button("Run inspection", disabled=not (ref and cand), type="primary"):
    try:
        with st.spinner("Inspecting text, fonts, colours, dimensions, images and barcodes..."):
            res, overlays = engine.run(ref.getvalue(), cand.getvalue(), spec_text, dpi, thr, do_bc)
        st.session_state["res"] = (res, overlays, ref.name, cand.name)
    except UnsupportedPDF as exc:
        st.error(f"Cannot inspect: {exc}")
        st.session_state.pop("res", None)
    except Exception as exc:  # never show a traceback to the reviewer; the file is the likely cause
        st.error(f"The inspection could not be completed ({type(exc).__name__}). Check that both files are valid, unprotected PDFs.")
        st.session_state.pop("res", None)

if "res" in st.session_state:
    res, overlays, rn, cn = st.session_state["res"]
    box = st.error if res["counts"][S.FAIL] else st.warning
    box(res["overall"])
    cols = st.columns(len(S.ALL))
    for col, s in zip(cols, S.ALL):
        col.metric(s, res["counts"][s])

    tab_find, tab_vis, tab_info, tab_dl = st.tabs(["Findings", "Visual differences", "Files and settings", "Download"])
    with tab_find:
        only_fail = st.toggle("Show failures only", False)
        f_status = st.multiselect("Filter by status", S.ALL, default=[s for s in S.ALL if s != S.PASS])
        rows = report.sorted_rows([r for r in res["rows"] if r["status"] in ([S.FAIL] if only_fail else f_status)])
        st.caption(f"{len(rows)} finding(s) shown. Failures first.")
        st.dataframe(rows, use_container_width=True, hide_index=True)
    with tab_vis:
        if not overlays:
            st.info("No pages were rendered.")
        for page, (ov, regions) in overlays.items():
            st.subheader(f"Page {page}: {len(regions)} changed region(s)")
            st.image(report.overlay_image(ov, regions), caption="Red = changed pixels (RGB render). Not a colour measurement.", use_container_width=True)
    with tab_info:
        a, b = st.columns(2)
        for col, label, name, d in ((a, "Reference", rn, res["reference"]), (b, "Candidate", cn, res["candidate"])):
            col.markdown(f"**{label}**: {name}")
            col.write({"pages": d["pages"], "sha256": d["sha256"], **d["metadata"]})
        st.write({"settings": res["settings"], "generated": res["generated"]})
    with tab_dl:
        st.download_button("Download report (HTML, printable)", report.to_html(res, rn, cn, overlays), "inspection_report.html", "text/html")
        st.download_button("Download findings (CSV)", report.to_csv(res), "inspection_findings.csv", "text/csv")
        st.download_button("Download report (JSON)", report.to_json(res, rn, cn), "inspection_report.json", "application/json")
    st.caption(report.DISCLAIMER)
