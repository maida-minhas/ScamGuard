from __future__ import annotations

from scamguard.models import Report, Review

HIGH_RISK = "High risk"
CAUTION = "Caution"
LOOKS_OK = "Looks OK"
NO_DATA = "No data"

RISK_TONES = {HIGH_RISK: "red", CAUTION: "amber", LOOKS_OK: "green"}


def compute_risk(reviews: list[Review], reports: list[Report]) -> str:
    """Return the spec §6 risk label for published content only.

    Order of checks: No data -> High risk -> Caution -> Looks OK.
    """
    if not reviews and not reports:
        return NO_DATA
    if reports:
        return HIGH_RISK
    avg = sum(r.rating for r in reviews) / len(reviews)
    if avg <= 2 and len(reviews) >= 2:
        return HIGH_RISK
    if avg < 3.5 or (len(reviews) < 2 and any(r.rating <= 2 for r in reviews)):
        return CAUTION
    return LOOKS_OK
