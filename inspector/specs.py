"""Dimensional checks against a user-supplied JSON specification. No built-in limits are assumed."""
import json
from . import status as S
from .status import make

EXAMPLE = {
    "name": "Example carton (replace with approved values)",
    "source": "Approved spec document ID / version",
    "unit": "mm",
    "page": 1,
    "box": "TrimBox",
    "expected": {"width": 150.0, "height": 70.0},
    "tolerance": 0.5,
}

PT_PER = {"pt": 1.0, "mm": 72 / 25.4, "cm": 72 / 2.54, "in": 72.0}


def parse(text: str):
    try:
        spec = json.loads(text)
    except Exception as exc:
        return None, f"Invalid JSON: {exc}"
    missing = [k for k in ("unit", "expected", "source") if k not in spec]
    if missing:
        return None, f"Spec incomplete, missing: {', '.join(missing)}"
    if spec["unit"] not in PT_PER:
        return None, f"Unsupported unit {spec['unit']}"
    return spec, None


def check(analysis, spec_text):
    if not spec_text or not spec_text.strip():
        return [make("Dimensional spec check", S.NOT_CONFIGURED, "No specification supplied; no Pass/Fail issued", None, "spec")]
    spec, err = parse(spec_text)
    if err:
        return [make("Dimensional spec check", S.NOT_VERIFIABLE, err, None, "spec")]
    if "tolerance" not in spec:
        return [make("Dimensional spec check", S.NOT_CONFIGURED, "Spec has no explicit tolerance; no Pass/Fail issued", None, spec["source"])]
    idx = int(spec.get("page", 1)) - 1
    if not 0 <= idx < analysis["page_count"]:
        return [make("Dimensional spec check", S.NOT_VERIFIABLE, "Spec page out of range", None, spec["source"])]
    page = analysis["pages"][idx]
    k = PT_PER[spec["unit"]]
    rows = []
    box_name = spec.get("box", "MediaBox")
    if box_name not in page["boxes"]:
        return [make("Dimensional spec check", S.NOT_VERIFIABLE, f"Unknown box {box_name}", idx + 1, spec["source"])]
    box = page["boxes"][box_name]
    if box is None:
        return [make("Dimensional spec check", S.NOT_VERIFIABLE, f"{box_name} is not defined in this PDF; cannot measure it", idx + 1, spec["source"])]
    for dim, actual_pt in (("width", box[2] - box[0]), ("height", box[3] - box[1])):
        if dim not in spec["expected"]:
            rows.append(make(f"Spec {dim}", S.NOT_CONFIGURED, f"No expected {dim} in spec", idx + 1, spec["source"]))
            continue
        meas = actual_pt / k
        diff = meas - float(spec["expected"][dim])
        ok = abs(diff) <= float(spec["tolerance"])
        rows.append(make(f"Spec {dim}", S.PASS if ok else S.FAIL,
                         f"measured {meas:.3f} {spec['unit']}, required {spec['expected'][dim]} {spec['unit']}, diff {diff:+.3f}, tolerance +/-{spec['tolerance']} (measured from {box_name}). Source: {spec['source']}", idx + 1, spec["source"]))
    return rows
