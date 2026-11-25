# Changelog
## 0.5.1
- Password-protected (encrypted) PDFs are detected before analysis and reported as Unsupported / Not Verifiable: nothing is compared, no password is tried, and the message says this is not the same as outlined text. PDFs with owner-password restrictions only are read and flagged for review.
- OCR that reads no words in changed regions is Not Verifiable instead of "no differences".
- Arabic OCR verified with a synthetic changed-word fixture (test skipped where the Arabic language pack is not installed).
- Tests: 50 passing.
## 0.5.0
- OCR (tesseract, English + Arabic) for pages with no usable text layer, applied only to regions where the visual comparison found differences. Results are labelled OCR with confidence, never a plain Pass; font, size, bold and underline of outlined text stay Not Verifiable.
- packages.txt installs tesseract on Streamlit Cloud. Sidebar switch to turn OCR off.
- Tests: 46 passing.
## 0.4.0
- Text-document review: word-by-word wording, font family, size, bold, italic, underline, colour, numbering/bullets, ruled tables, item/batch codes, footer area.
- Outlined text detected and never reported as Pass; vector outline geometry compared instead.
- Highlights drawn directly on Reference and Candidate pages by category; highlighted-pages PDF download; in-app instructions and legend.
- Faster drawing extraction (about 3x on vector-heavy pages).
- Tests: 45 passing.
## 0.3.0
- Renamed to "Elixir Pharma - Quality Assurance Products Artwork AI Verification" (page title, header, reports, README).
- New checks: text layer present/absent, font embedding, page rotation, document metadata (dates/producer treated as informational).
- Report: failures first, summary cards, embedded visual-diff images, full SHA-256, print-ready HTML; new CSV export (Excel-safe for Arabic).
- UI: tabs (Findings, Visual differences, Files and settings, Download), failures-only toggle, help text, clean error messages instead of tracebacks.
- Tests: 38 passing.
## 0.2.0
- Arabic: extracted text normalized with NFKC (shaped/presentation forms folded to base letters), readable in reports; Arabic-Indic vs Western digit mismatch flagged for review.
- Colour: vector fill/stroke RGB palettes compared with usage counts; Separation/DeviceN (spot/Pantone) ink names compared. Tints, ICC, overprint, Delta E remain Not Implemented.
- Dimensions: page boxes reported in mm; JSON spec can name the box to measure (`"box": "TrimBox"`), box missing in the PDF gives Not Verifiable.
- Images: effective resolution (ppi) compared.
- Tests: 28 passing.
## 0.1.0
- New clean Streamlit app (not derived from the earlier private project code, which was not available).
- Native PDF analysis, Reference vs Candidate comparison, barcode decode, dimensional spec check, HTML/JSON report.
- 20 unit/regression tests.
