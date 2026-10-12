from flask import Blueprint, abort, current_app, send_from_directory

from scamguard.db import db
from scamguard.models import File
from scamguard.security import current_user, login_required

bp = Blueprint("file_routes", __name__)


@bp.route("/files/<int:file_id>")
@login_required
def get_file(file_id: int):
    stored = db.session.get(File, file_id)
    if stored is None:
        abort(404)
    if stored.uploader_id != current_user.id:
        abort(403)
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        stored.stored_name,
        download_name=stored.original_name,
    )
