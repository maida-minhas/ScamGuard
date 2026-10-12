from sqlalchemy import select

from scamguard.db import db
from scamguard.models import (
    EntityType,
    Report,
    ReportCategory,
    ReportStatus,
    Review,
    ReviewStatus,
    User,
)
from scamguard.uploads import save_upload

MAX_REVIEW_BODY = 2000
MAX_REPORT_DESCRIPTION = 2000


def promote_pending_content(user: User) -> None:
    for report in user.reports:
        if report.status == ReportStatus.PENDING:
            report.status = ReportStatus.PUBLISHED
    for review in user.reviews:
        if review.status != ReviewStatus.PENDING:
            continue
        if review.entity.type == EntityType.PHONE or review.proof_file_id is not None:
            review.status = ReviewStatus.PUBLISHED


def submit_review(user, entity, rating, body, proof_upload) -> tuple[Review | None, str | None]:
    """Validate and store a review, applying the spec §5 gates.

    Returns (review, None) on success or (None, error_message) on failure.
    """
    if isinstance(rating, str):
        try:
            rating = int(rating)
        except ValueError:
            rating = None
    if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
        return None, "Rating must be between 1 and 5."

    body = (body or "").strip()
    if not body:
        return None, "Please write a review."
    if len(body) > MAX_REVIEW_BODY:
        return None, f"Review must be {MAX_REVIEW_BODY} characters or fewer."

    duplicate = db.session.execute(
        select(Review).where(Review.user_id == user.id, Review.entity_id == entity.id)
    ).scalar_one_or_none()
    if duplicate is not None:
        return None, "You already reviewed this entity."

    proof_file = None
    if entity.type != EntityType.PHONE and proof_upload is not None and proof_upload.filename:
        proof_file = save_upload(proof_upload, user)
        if proof_file is None:
            return None, "We could not save that proof file."

    verified = user.email_verified_at is not None
    if entity.type == EntityType.PHONE:
        status = ReviewStatus.PUBLISHED if verified else ReviewStatus.PENDING
    elif proof_file is None or not verified:
        status = ReviewStatus.PENDING
    else:
        status = ReviewStatus.PUBLISHED

    review = Review(
        entity_id=entity.id,
        user_id=user.id,
        rating=rating,
        body=body,
        status=status,
        proof_file_id=proof_file.id if proof_file is not None else None,
    )
    db.session.add(review)
    db.session.commit()
    return review, None


def submit_report(user, entity, category, description) -> tuple[Report | None, str | None]:
    """Validate and store a scam report, applying the spec §5 gates.

    Returns (report, None) on success or (None, error_message) on failure.
    """
    try:
        category = ReportCategory(category)
    except (ValueError, KeyError, TypeError):
        return None, "Choose a valid report category."

    description = (description or "").strip()
    if not description:
        return None, "Please describe the problem."
    if len(description) > MAX_REPORT_DESCRIPTION:
        return None, f"Report must be {MAX_REPORT_DESCRIPTION} characters or fewer."

    duplicate = db.session.execute(
        select(Report).where(Report.user_id == user.id, Report.entity_id == entity.id)
    ).scalar_one_or_none()
    if duplicate is not None:
        return None, "You already reported this entity."

    verified = user.email_verified_at is not None
    report = Report(
        entity_id=entity.id,
        user_id=user.id,
        category=category,
        description=description,
        status=ReportStatus.PUBLISHED if verified else ReportStatus.PENDING,
    )
    db.session.add(report)
    db.session.commit()
    return report, None
