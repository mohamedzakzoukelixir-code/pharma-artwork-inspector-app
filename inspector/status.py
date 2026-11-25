"""Result statuses. A check that cannot be proven never reports PASS."""
PASS = "Pass"
FAIL = "Fail"
NOT_CONFIGURED = "Not Configured"
NOT_VERIFIABLE = "Not Verifiable"
REVIEW = "Requires Human Review"
NOT_IMPLEMENTED = "Not Implemented"

ALL = (PASS, FAIL, NOT_CONFIGURED, NOT_VERIFIABLE, REVIEW, NOT_IMPLEMENTED)


def make(check, status, detail="", page=None, source="native PDF"):
    """One traceable result row."""
    assert status in ALL, status
    return {"check": check, "status": status, "detail": detail, "page": page, "source": source}
