"""Barcode / DataMatrix decoding from a rendered page (zxing-cpp). Decoded from pixels, not a scanner grade."""
from . import status as S
from .status import make


def _decode(img):
    import zxingcpp
    return {(r.format.name, r.text) for r in zxingcpp.read_barcodes(img)}


def decode_page(img_loader):
    """img_loader(dpi) -> PIL image. Tries 200, 400, 600 dpi until something decodes."""
    try:
        import zxingcpp  # noqa: F401
    except Exception:
        return None
    for dpi in (200, 400, 600):
        found = _decode(img_loader(dpi))
        if found:
            return sorted(found)
    return []


def compare_barcodes(ref_loader, cand_loader, page_no):
    ra, ca = decode_page(ref_loader), decode_page(cand_loader)
    if ra is None:
        return [make("Barcode", S.NOT_VERIFIABLE, "Barcode library (zxing-cpp) not installed", page_no, "render")]
    if not ra and not ca:
        return [make("Barcode", S.NOT_VERIFIABLE, "No barcode decoded in either file (none present, too small, or unreadable). Visual comparison still applies.", page_no, "render")]
    if not ra or not ca:
        return [make("Barcode", S.FAIL, f"Reference {ra or 'none decoded'}, Candidate {ca or 'none decoded'}", page_no, "render")]
    if ra == ca:
        return [make("Barcode", S.PASS, "Same decoded value(s): " + ", ".join(f"{f} {t}" for f, t in ra) + ". Decoded from render; print grade (ISO 15416) not assessed.", page_no, "render")]
    return [make("Barcode", S.FAIL, f"Reference {ra}, Candidate {ca}", page_no, "render")]
