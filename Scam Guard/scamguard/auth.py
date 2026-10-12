import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from scamguard.db import db
from scamguard.models import EmailToken, Report, Review, User
from scamguard.security import login_required
from scamguard.services import promote_pending_content

bp = Blueprint("auth", __name__)

PASSWORD_MIN_LENGTH = 6
TOKEN_TTL = timedelta(hours=24)
DEMO_TOKEN_SESSION_KEY = "demo_verify_token"
DEMO_EMAIL_SESSION_KEY = "demo_verify_email"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_valid_email(email: str) -> bool:
    local, sep, domain = email.partition("@")
    return bool(sep and local and "." in domain)


def _safe_next_url(target):
    if not target:
        return None
    if "\\" in target:
        return None
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in target):
        return None
    if target.startswith("//"):
        return None
    try:
        parts = urlsplit(target)
    except ValueError:
        return None
    if parts.scheme or parts.netloc:
        return None
    if not parts.path.startswith("/") or parts.path.startswith("//"):
        return None
    return target


def _clear_demo_token_stash():
    session.pop(DEMO_TOKEN_SESSION_KEY, None)
    session.pop(DEMO_EMAIL_SESSION_KEY, None)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("auth/register.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not _is_valid_email(email):
        flash("Enter a valid email address.")
        return render_template("auth/register.html", email=email)
    if len(password) < PASSWORD_MIN_LENGTH:
        flash(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
        return render_template("auth/register.html", email=email)
    existing = db.session.execute(
        db.select(User).where(User.email == email)
    ).scalar_one_or_none()
    if existing is not None:
        flash("That email is already registered.")
        return render_template("auth/register.html", email=email)

    user = User(email=email, password_hash=generate_password_hash(password))
    token = EmailToken(
        user=user,
        token=secrets.token_urlsafe(16),
        purpose="verify_email",
        expires_at=utcnow() + TOKEN_TTL,
    )
    db.session.add_all([user, token])
    db.session.commit()

    if current_app.config.get("DEMO_MODE", True):
        session[DEMO_TOKEN_SESSION_KEY] = token.token
        session[DEMO_EMAIL_SESSION_KEY] = user.email
        return redirect(url_for("auth.register_success"))

    flash("Check your inbox for a verification link.")
    return redirect(url_for("auth.login"))


@bp.route("/register/success")
def register_success():
    token = session.get(DEMO_TOKEN_SESSION_KEY)
    if not token:
        return redirect(url_for("auth.register"))
    return render_template(
        "auth/register.html",
        email=session.get(DEMO_EMAIL_SESSION_KEY, ""),
        token=token,
    )


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    user = db.session.execute(
        db.select(User).where(User.email == email)
    ).scalar_one_or_none()
    if user is None or not check_password_hash(user.password_hash, password):
        flash("Invalid email or password.")
        return render_template("auth/login.html", email=email)

    login_user(user)
    _clear_demo_token_stash()
    next_url = _safe_next_url(request.args.get("next")) or url_for("index")
    return redirect(next_url)


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("You have been logged out.")
    return redirect(url_for("index"))


@bp.route("/verify", methods=["GET", "POST"])
def verify():
    raw = request.args.get("token") or request.form.get("token")
    if not raw:
        flash("Verification link is missing a token.")
        return render_template("auth/verify_result.html", success=False)

    token = db.session.execute(
        db.select(EmailToken).where(
            EmailToken.token == raw,
            EmailToken.purpose == "verify_email",
        )
    ).scalar_one_or_none()
    if token is None:
        flash("Invalid verification token.")
        return render_template("auth/verify_result.html", success=False)
    if token.used_at is not None:
        flash("This verification token has already been used.")
        return render_template("auth/verify_result.html", success=False)
    if token.expires_at < utcnow():
        flash("This verification token has expired.")
        return render_template("auth/verify_result.html", success=False)

    token.used_at = utcnow()
    user = token.user
    user.email_verified_at = utcnow()
    promote_pending_content(user)
    db.session.commit()
    _clear_demo_token_stash()

    flash("Email verified. Your pending content is now public.")
    return render_template("auth/verify_result.html", success=True)


@bp.route("/my-activity")
@login_required
def my_activity():
    reviews = list(
        db.session.execute(
            db.select(Review)
            .where(Review.user_id == current_user.id)
            .order_by(Review.created_at.desc())
        )
        .scalars()
    )
    reports = list(
        db.session.execute(
            db.select(Report)
            .where(Report.user_id == current_user.id)
            .order_by(Report.created_at.desc())
        )
        .scalars()
    )
    return render_template("my_activity.html", reviews=reviews, reports=reports)
