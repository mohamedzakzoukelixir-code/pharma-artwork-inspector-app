# Pharma Artwork AI Inspector (clean Streamlit build, v0.2.0)

Compares a Reference artwork PDF with a Candidate artwork PDF and reports differences. Inspection aid only: not GMP-validated, not a release approval. Human review and sign-off are mandatory.

## Run
    pip install -r requirements.txt
    streamlit run app.py
Tests: `pip install -r requirements-dev.txt && pytest`

## What it checks (all read natively from the PDF unless noted)
Page count, page size, orientation/rotation, MediaBox/CropBox/TrimBox/BleedBox/ArtBox, embedded text (word diff), per-run font/size/color/position, font resources and embedded status, embedded image pixel hashes and effective ppi, vector fill/stroke colors, spot (Separation/DeviceN) ink names, page boxes in mm, vector drawing count, annotations/comments, pixel diff of rendered pages (RGB render), EAN/Code128/DataMatrix/QR decoding from render (zxing-cpp), dimensional check against a user JSON spec.

## Status model
Pass / Fail / Not Configured / Not Verifiable / Requires Human Review / Not Implemented. Anything that cannot be proven is never Pass. See `specs/example_spec.json`.

## Known limitations
No OCR, no ICC/Pantone/spot/overprint evaluation, no dieline extraction, no image registration (pages compared at identical coordinates), no regulatory rules, no packaging profiles, no authentication, audit trail or e-signatures. Arabic text order extracted from PDFs may differ from visual order (flagged). Barcode decode is not a print-quality grade. Positions use a 0.5 pt tolerance, sizes 0.05 pt, pixel threshold selectable.
