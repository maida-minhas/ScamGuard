import pytest

from scamguard.models import Report, ReportCategory, Review
from scamguard.risk import compute_risk


def r(rating):
    return Review(rating=rating)


def rep(category=ReportCategory.PHISHING):
    return Report(category=category, description="scam")


@pytest.mark.parametrize(
    "reviews, reports, expected",
    [
        ([], [], "No data"),
        ([], [rep()], "High risk"),
        ([r(1), r(2)], [], "High risk"),
        ([r(2), r(2)], [], "High risk"),
        ([r(2), r(3)], [rep()], "High risk"),
        ([r(4), r(5)], [rep()], "High risk"),
        ([r(1)], [], "Caution"),
        ([r(1.5)], [], "Caution"),
        ([r(3)], [], "Caution"),
        ([r(3), r(3)], [], "Caution"),
        ([r(4)], [], "Looks OK"),
        ([r(3), r(4)], [], "Looks OK"),
        ([r(4), r(5)], [], "Looks OK"),
    ],
    ids=[
        "empty-no-data",
        "one-report-alone-high",
        "two-reviews-avg-1.5-high",
        "two-reviews-avg-2.0-high",
        "avg-2.5-plus-report-high",
        "good-reviews-plus-report-high",
        "single-low-review-caution",
        "single-review-avg-1.5-caution",
        "single-review-avg-3.0-caution",
        "two-reviews-avg-3.0-caution",
        "single-review-avg-4.0-looks-ok",
        "avg-3.5-boundary-looks-ok",
        "avg-4.5-no-reports-looks-ok",
    ],
)
def test_compute_risk_labels(reviews, reports, expected):
    assert compute_risk(reviews, reports) == expected
