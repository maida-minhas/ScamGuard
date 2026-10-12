from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from scamguard.ai_insights import review_tone, summarize_reviews
from scamguard.db import db
from scamguard.models import Entity, Report, ReportStatus, Review, ReviewStatus
from scamguard.normalize import detect_type, identifier_hash, mask, normalize
from scamguard.risk import RISK_TONES, compute_risk

bp = Blueprint("entities", __name__)

UNRECOGNIZED_MESSAGE = (
    "That doesn't look like a phone number, Instagram handle, or Facebook link"
)


def find_or_create_entity(raw: str) -> Entity | None:
    """Return the entity for raw input, creating it if needed.

    Returns None when the input cannot be classified or normalized.
    """
    entity_type = detect_type(raw)
    if entity_type is None:
        return None
    try:
        canonical = normalize(raw, entity_type)
    except ValueError:
        return None
    id_hash = identifier_hash(canonical)
    entity = db.session.execute(
        db.select(Entity).where(Entity.identifier_hash == id_hash)
    ).scalar_one_or_none()
    if entity is not None:
        return entity
    entity = Entity(
        type=entity_type,
        identifier_hash=id_hash,
        display_masked=mask(canonical, entity_type),
    )
    db.session.add(entity)
    db.session.commit()
    return entity


def _published_reviews(entity_id: int) -> list[Review]:
    return list(
        db.session.execute(
            db.select(Review)
            .where(
                Review.entity_id == entity_id,
                Review.status == ReviewStatus.PUBLISHED,
            )
            .order_by(Review.created_at.desc())
        )
        .scalars()
    )


def _published_reports(entity_id: int) -> list[Report]:
    return list(
        db.session.execute(
            db.select(Report)
            .where(
                Report.entity_id == entity_id,
                Report.status == ReportStatus.PUBLISHED,
            )
            .order_by(Report.created_at.desc())
        )
        .scalars()
    )


@bp.route("/search")
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return redirect(url_for("index"))
    entity = find_or_create_entity(q)
    if entity is None:
        flash(UNRECOGNIZED_MESSAGE)
        return render_template("search_results.html")
    return redirect(url_for("entities.entity_page", entity_id=entity.id))


@bp.route("/entity/<int:entity_id>")
def entity_page(entity_id: int):
    entity = db.session.get(Entity, entity_id)
    if entity is None:
        abort(404)

    reviews = _published_reviews(entity_id)
    reports = _published_reports(entity_id)
    avg_stars = f"{sum(r.rating for r in reviews) / len(reviews):.1f}" if reviews else "—"
    show_reports = request.args.get("tab") == "reports"
    risk_label = compute_risk(reviews, reports)
    insights = summarize_reviews(reviews) if reviews else None
    review_tones = {r.id: review_tone(r.body, r.rating) for r in reviews}

    return render_template(
        "entity.html",
        entity=entity,
        reviews=reviews,
        reports=reports,
        avg_stars=avg_stars,
        review_count=len(reviews),
        report_count=len(reports),
        show_reports=show_reports,
        risk_label=risk_label,
        risk_tone=RISK_TONES.get(risk_label, "slate"),
        insights=insights,
        review_tones=review_tones,
    )
