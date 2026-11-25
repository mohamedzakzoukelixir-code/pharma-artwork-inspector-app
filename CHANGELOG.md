# Changelog
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
