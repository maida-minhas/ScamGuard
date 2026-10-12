import io
from datetime import datetime, timezone

import pytest
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from scamguard.db import db
from scamguard.models import (
    Entity,
    EntityType,
    Report,
    ReportCategory,
    ReportStatus,
    User,
)
from scamguard.services import submit_review


@pytest.fixture
def ctx(app, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
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


def _add_user(email="ada@example.com", verified=True):
    user = User(email=email, password_hash=generate_password_hash("secret123"))
    if verified:
        user.email_verified_at = _utcnow()
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, email="ada@example.com"):
    return client.post("/login", data={"email": email, "password": "secret123"})


def _entity(kind=EntityType.PHONE, suffix="1", masked="03**-***-1111"):
    entity = Entity(type=kind, identifier_hash=suffix * 64, display_masked=masked)
    db.session.add(entity)
    db.session.commit()
    return entity


def _proof():
    return FileStorage(
        stream=io.BytesIO(b"seed-png-bytes"),
        filename="receipt.png",
        content_type="image/png",
    )


def test_my_activity_requires_login(client, ctx):
    resp = client.get("/my-activity")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_my_activity_empty_state(client, ctx):
    _add_user()
    _login(client)

    resp = client.get("/my-activity")

    assert resp.status_code == 200
    assert b"You haven't written any reviews yet." in resp.data
    assert b"You haven't filed any reports yet." in resp.data


def test_pending_phone_review_shows_awaiting_email_verification_chip(client, ctx):
    user = _add_user(verified=False)
    phone = _entity(EntityType.PHONE, "1", "03**-***-1111")
    submit_review(user, phone, 5, "pending phone review", None)
    _login(client)

    resp = client.get("/my-activity")

    assert resp.status_code == 200
    assert b"pending phone review" in resp.data
    assert b"Awaiting email verification" in resp.data
    assert b"Missing proof" not in resp.data


def test_business_pending_without_proof_shows_missing_proof_chip(client, ctx):
    user = _add_user(verified=True)
    ig = _entity(EntityType.INSTAGRAM, "2", "@sh****op")
    submit_review(user, ig, 3, "business needs proof", None)
    _login(client)

    resp = client.get("/my-activity")

    assert resp.status_code == 200
    assert b"business needs proof" in resp.data
    assert b"Missing proof" in resp.data
    assert b"Awaiting email verification" not in resp.data


def test_published_review_with_proof_shows_verified_badge(client, ctx):
    user = _add_user(verified=True)
    ig = _entity(EntityType.INSTAGRAM, "2", "@sh****op")
    review, error = submit_review(user, ig, 5, "badged business review", _proof())
    assert error is None
    _login(client)

    resp = client.get("/my-activity")

    assert resp.status_code == 200
    assert b"badged business review" in resp.data
    assert b"Published" in resp.data
    assert b"Verified with proof" in resp.data


def test_own_reports_listed_with_status_chips(client, ctx):
    user = _add_user(verified=True)
    phone = _entity(EntityType.PHONE, "1", "03**-***-1111")
    ig = _entity(EntityType.INSTAGRAM, "2", "@sh****op")
    db.session.add_all(
        [
            Report(
                entity=phone,
                user=user,
                category=ReportCategory.NON_DELIVERY,
                description="never shipped the order",
                status=ReportStatus.PUBLISHED,
            ),
            Report(
                entity=ig,
                user=user,
                category=ReportCategory.PHISHING,
                description="fake login page",
                status=ReportStatus.PENDING,
            ),
        ]
    )
    db.session.commit()
    _login(client)

    resp = client.get("/my-activity")

    assert resp.status_code == 200
    assert b"Non Delivery" in resp.data
    assert b"never shipped the order" in resp.data
    assert b"Published" in resp.data
    assert b"Phishing" in resp.data
    assert b"fake login page" in resp.data
    assert b"Awaiting email verification" in resp.data


def test_activity_reviews_do_not_leak_other_users_content(client, ctx):
    owner = _add_user(email="owner@example.com", verified=True)
    stranger = _add_user(email="stranger@example.com", verified=True)
    phone = _entity(EntityType.PHONE, "1", "03**-***-1111")
    submit_review(owner, phone, 5, "OWNERS-REVIEW-BODY", None)
    db.session.add(
        Report(
            entity=phone,
            user=owner,
            category=ReportCategory.FAKE_SELLER,
            description="OWNERS-REPORT-BODY",
            status=ReportStatus.PUBLISHED,
        )
    )
    db.session.commit()
    _login(client, "stranger@example.com")

    resp = client.get("/my-activity")

    assert resp.status_code == 200
    assert b"OWNERS-REVIEW-BODY" not in resp.data
    assert b"OWNERS-REPORT-BODY" not in resp.data
