from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from scamguard.db import db
from scamguard.models import Entity, EntityType, ReviewStatus
from scamguard.security import current_user, login_required
from scamguard.services import submit_review

bp = Blueprint("reviews", __name__)


@bp.route("/review/<int:entity_id>", methods=["GET", "POST"])
@login_required
def review_form(entity_id: int):
    entity = db.session.get(Entity, entity_id)
    if entity is None:
        abort(404)

    error = None
    if request.method == "POST":
        review, error = submit_review(
            current_user,
            entity,
            request.form.get("rating", type=int),
            request.form.get("body", ""),
            request.files.get("proof"),
        )
        if error is None:
            if review.status == ReviewStatus.PUBLISHED:
                flash("Your review is published.")
            elif entity.type == EntityType.PHONE:
                flash("Review saved — verify your email to publish it.")
            elif review.proof_file_id is None:
                flash(
                    "Review saved — business reviews need proof of payment "
                    "at submission to be published."
                )
            else:
                flash("Review saved — it will go public once your email is verified.")
            return redirect(url_for("entities.entity_page", entity_id=entity.id))

    return render_template("review_form.html", entity=entity, error=error)
