from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.security import generate_password_hash

from scamguard.db import db
from scamguard.models import (
    EmailToken,
    Entity,
    EntityType,
    File,
    Report,
    ReportCategory,
    Review,
    ReviewStatus,
    User,
)


@pytest.fixture
def ctx(app):
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app, ctx):
    return app.test_client()


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _add_user(email="ada@example.com", password="secret123"):
    user = User(email=email, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    return user


def _get_user(email):
    db.session.expire_all()
    return db.session.execute(db.select(User).where(User.email == email)).scalar_one()


def _add_token(user, raw="fixed-test-token", expires_in=timedelta(hours=24), purpose="verify_email"):
    token = EmailToken(user=user, token=raw, purpose=purpose, expires_at=_utcnow() + expires_in)
    db.session.add(token)
    db.session.commit()
    return token


def _entity(kind, suffix, masked):
    entity = Entity(type=kind, identifier_hash=suffix * 64, display_masked=masked)
    db.session.add(entity)
    db.session.commit()
    return entity


def _pending_content(user):
    phone = _entity(EntityType.PHONE, "1", "03**-***-1111")
    ig = _entity(EntityType.INSTAGRAM, "2", "@sh****op")
    fb = _entity(EntityType.FACEBOOK, "3", "www.facebook.com/mar…")

    phone_review = Review(entity=phone, user=user, rating=5, body="phone ok")
    biz_no_proof = Review(entity=ig, user=user, rating=1, body="biz no proof")
    proof = File(
        uploader=user,
        stored_name="proof-1.png",
        original_name="receipt.png",
        mime_type="image/png",
        size=99,
    )
    biz_with_proof = Review(entity=fb, user=user, rating=2, body="biz with proof")
    biz_with_proof.proof_file = proof
    report = Report(
        entity=phone,
        user=user,
        category=ReportCategory.FAKE_SELLER,
        description="took the money",
    )
    db.session.add_all([phone_review, biz_no_proof, biz_with_proof, report])
    db.session.commit()
    return phone_review, biz_no_proof, biz_with_proof, report


def _register(client, email="ada@example.com", password="secret123"):
    return client.post("/register", data={"email": email, "password": password})


def test_register_page_renders(client):
    resp = client.get("/register")

    assert resp.status_code == 200
    assert b"Create your account" in resp.data


def test_register_creates_user_and_token(client):
    resp = _register(client)

    assert resp.status_code == 302
    user = _get_user("ada@example.com")
    assert user.password_hash != "secret123"
    assert user.email_verified_at is None

    token = db.session.execute(
        db.select(EmailToken).where(EmailToken.user_id == user.id)
    ).scalar_one()
    assert token.purpose == "verify_email"
    assert token.used_at is None
    assert token.expires_at > _utcnow() + timedelta(hours=23)


def test_register_success_page_displays_token_and_verify_link(client):
    resp = _register(client)

    assert resp.status_code == 302
    page = client.get(resp.headers["Location"])

    user = _get_user("ada@example.com")
    token = db.session.execute(
        db.select(EmailToken).where(EmailToken.user_id == user.id)
    ).scalar_one()
    assert page.status_code == 200
    assert token.token.encode() in page.data
    assert b"/verify?token=" in page.data


def test_register_success_page_refresh_safe(client):
    resp = _register(client)
    location = resp.headers["Location"]

    user = _get_user("ada@example.com")
    token = db.session.execute(
        db.select(EmailToken).where(EmailToken.user_id == user.id)
    ).scalar_one()
    first = client.get(location)
    second = client.get(location)

    assert token.token.encode() in first.data
    assert token.token.encode() in second.data


def test_register_success_page_without_stash_redirects_to_register(client):
    resp = client.get("/register/success")

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/register")


def test_verify_clears_stashed_token(client):
    _register(client)
    user = _get_user("ada@example.com")
    _add_token(user, raw="consume-me")

    client.get("/verify?token=consume-me")

    resp = client.get("/register/success")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/register")


def test_login_clears_stashed_token(client):
    _register(client)

    resp = client.post("/login", data={"email": "ada@example.com", "password": "secret123"})
    assert resp.status_code == 302

    page = client.get("/register/success")
    assert page.status_code == 302
    assert page.headers["Location"].endswith("/register")


def test_register_rejects_duplicate_email(client):
    _register(client)
    resp = _register(client)

    assert b"already registered" in resp.data
    db.session.expire_all()
    count = db.session.execute(db.select(db.func.count()).select_from(User)).scalar_one()
    assert count == 1


def test_register_rejects_invalid_email_and_short_password(client):
    resp = _register(client, email="not-an-email")
    assert b"valid email" in resp.data

    resp = _register(client, email="bob@example.com", password="abc")
    assert b"at least 6 characters" in resp.data
    count = db.session.execute(
        db.select(db.func.count()).select_from(User).where(User.email == "bob@example.com")
    ).scalar_one()
    assert count == 0


def test_login_success_sets_session_and_opens_my_activity(client):
    _add_user()

    resp = client.post("/login", data={"email": "ada@example.com", "password": "secret123"})
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is not None

    page = client.get("/my-activity")
    assert page.status_code == 200
    assert b"My activity" in page.data
    assert b"My reviews" in page.data


def test_login_wrong_password_rejected(client):
    _add_user()

    resp = client.post("/login", data={"email": "ada@example.com", "password": "wrongpass"})

    assert b"Invalid email or password" in resp.data
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None


def test_login_honors_safe_next(client):
    _add_user()

    resp = client.post(
        "/login",
        query_string="next=/my-activity",
        data={"email": "ada@example.com", "password": "secret123"},
    )

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/my-activity")


@pytest.mark.parametrize(
    "attack",
    [
        "//evil.com",
        "/\\evil.com",
        "https://evil.com",
        "/%09/evil",
        "////evil.com",
        "///evil.com",
        "//[::1",
        "//]",
    ],
)
def test_login_rejects_unsafe_next(client, attack):
    _add_user()

    resp = client.post(
        "/login",
        query_string="next=" + attack,
        data={"email": "ada@example.com", "password": "secret123"},
    )

    assert resp.status_code == 302
    location = resp.headers["Location"]
    assert "evil" not in location
    assert location in ("/", "http://localhost/")


def test_logout_clears_session(client):
    _add_user()
    client.post("/login", data={"email": "ada@example.com", "password": "secret123"})

    resp = client.post("/logout")
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None

    page = client.get("/my-activity")
    assert page.status_code == 302
    assert "/login" in page.headers["Location"]


def test_my_activity_redirects_anonymous_to_login(client):
    resp = client.get("/my-activity")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_verify_get_marks_verified_and_promotes_pending_content(client, app):
    user = _add_user()
    phone_review, biz_no_proof, biz_with_proof, report = _pending_content(user)
    _add_token(user, raw="good-token")

    resp = client.get("/verify?token=good-token")

    assert resp.status_code == 200
    assert b"Email verified" in resp.data

    refreshed = _get_user("ada@example.com")
    assert refreshed.email_verified_at is not None
    assert phone_review.status == ReviewStatus.PUBLISHED
    assert biz_no_proof.status == ReviewStatus.PENDING
    assert biz_with_proof.status == ReviewStatus.PUBLISHED
    assert report.status == "published"

    token = db.session.execute(
        db.select(EmailToken).where(EmailToken.user_id == refreshed.id)
    ).scalar_one()
    assert token.used_at is not None


def test_verify_post_also_works(client):
    user = _add_user()
    _add_token(user, raw="post-token")

    resp = client.post("/verify", data={"token": "post-token"})

    assert resp.status_code == 200
    assert b"Email verified" in resp.data
    assert _get_user("ada@example.com").email_verified_at is not None


def test_verify_invalid_token_flashes_error(client):
    user = _add_user()

    resp = client.get("/verify?token=nope")

    assert b"Invalid verification token" in resp.data
    assert _get_user("ada@example.com").email_verified_at is None
    assert user.email_verified_at is None


def test_verify_ignores_token_with_other_purpose(client):
    user = _add_user()
    _add_token(user, raw="reset-token", purpose="password_reset")

    resp = client.get("/verify?token=reset-token")

    assert b"Invalid verification token" in resp.data
    assert _get_user("ada@example.com").email_verified_at is None


def test_verify_expired_token_flashes_error(client):
    user = _add_user()
    _add_token(user, raw="stale-token", expires_in=timedelta(hours=-1))

    resp = client.get("/verify?token=stale-token")

    assert b"expired" in resp.data
    assert _get_user("ada@example.com").email_verified_at is None


def test_verify_used_token_flashes_error(client):
    user = _add_user()
    _add_token(user, raw="one-time-token")

    first = client.get("/verify?token=one-time-token")
    assert b"Email verified" in first.data

    second = client.get("/verify?token=one-time-token")
    assert b"already been used" in second.data


def test_verify_missing_token_flashes_error(client):
    resp = client.get("/verify")

    assert b"missing a token" in resp.data


def test_nav_shows_login_register_for_anonymous_and_activity_logout_when_logged_in(client):
    anonymous = client.get("/")
    assert b"Login" in anonymous.data
    assert b"Register" in anonymous.data
    assert b"My Activity" not in anonymous.data

    _add_user()
    client.post("/login", data={"email": "ada@example.com", "password": "secret123"})
    logged_in = client.get("/")
    assert b"My Activity" in logged_in.data
    assert b"Logout" in logged_in.data
