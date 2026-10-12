from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from scamguard.ai_insights import suggest_category
from scamguard.db import db
from scamguard.models import Entity, ReportCategory, ReportStatus
from scamguard.security import current_user, login_required
from scamguard.services import submit_report

bp = Blueprint("reports", __name__)


@bp.route("/report/<int:entity_id>", methods=["GET", "POST"])
@login_required
def report_form(entity_id: int):
    entity = db.session.get(Entity, entity_id)
    if entity is None:
        abort(404)

    error = None
    if request.method == "POST":
        report, error = submit_report(
            current_user,
            entity,
            request.form.get("category", ""),
            request.form.get("description", ""),
        )
        if error is None:
            if report.status == ReportStatus.PUBLISHED:
                flash("Your report is published.")
            else:
                flash("Report saved — it will go public once your email is verified.")
            return redirect(url_for("entities.entity_page", entity_id=entity.id, tab="reports"))

    return render_template(
        "report_form.html",
        entity=entity,
        error=error,
        categories=list(ReportCategory),
    )


@bp.post("/ai/suggest")
def suggest():
    """Suggest a report category for free text (local keyword analysis)."""
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify(error="text is required"), 400
    return jsonify(category=suggest_category(text))
