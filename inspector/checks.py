"""Extra native-PDF checks: text layer, font embedding, document metadata, page rotation."""
from . import status as S
from .status import make

META_KEYS = ("title", "author", "subject", "producer", "creator", "creationDate", "modDate")
# Dates and tool names change on every export and usually mean nothing for artwork content.
META_NOISE = ("creationDate", "modDate", "producer", "creator")


def check_text_layer(ref, cand, n):
    rows = []
    for i in range(n):
        a, b = ref["pages"][i]["text_extractable"], cand["pages"][i]["text_extractable"]
        if a != b:
            rows.append(make("Text layer", S.FAIL, f"Text layer exists in {'Reference' if a else 'Candidate'} only (the other page has no extractable text: outlined or image-only?).", i + 1))
        elif not a:
            rows.append(make("Text layer", S.REVIEW, "No extractable text in either page. Text may be outlined or image-only; OCR is not implemented, so text was not compared.", i + 1))
        else:
            rows.append(make("Text layer", S.PASS, "Both pages have an extractable text layer.", i + 1))
    return rows


def check_font_embedding(ref, cand, n):
    rows = []
    for label, doc in (("Reference", ref), ("Candidate", cand)):
        bad = sorted({f["font"] for p in doc["pages"][:n] for f in p["fonts"] if not f["embedded"]})
        if bad:
            rows.append(make("Font embedding", S.REVIEW, f"{label}: fonts not embedded (print output may substitute them): {', '.join(bad)}", None))
        else:
            rows.append(make("Font embedding", S.PASS, f"{label}: every font used is embedded.", None))
    return rows


def check_rotation(ref, cand, n):
    diffs = [i + 1 for i in range(n) if ref["pages"][i]["rotation"] != cand["pages"][i]["rotation"]]
    if diffs:
        return [make("Page rotation", S.FAIL, f"Rotation differs on page(s) {diffs}.", None)]
    return [make("Page rotation", S.PASS, "Page rotation flags are identical.", None)]


def compare_metadata(ref, cand):
    rows = []
    diff = {k: (ref["metadata"].get(k), cand["metadata"].get(k)) for k in META_KEYS
            if ref["metadata"].get(k) != cand["metadata"].get(k)}
    content = {k: v for k, v in diff.items() if k not in META_NOISE}
    noise = {k: v for k, v in diff.items() if k in META_NOISE}
    if content:
        rows.append(make("Document metadata", S.REVIEW, "Title/author/subject differ: " + "; ".join(f"{k}: {a!r} vs {b!r}" for k, (a, b) in content.items()), None))
    else:
        rows.append(make("Document metadata", S.PASS, "Title, author and subject are identical.", None))
    if noise:
        rows.append(make("Export info (informational)", S.PASS, "Dates/producer differ, which is normal between exports: " + ", ".join(sorted(noise)), None))
    return rows
