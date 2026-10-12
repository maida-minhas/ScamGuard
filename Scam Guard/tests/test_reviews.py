import io
import os
import re
from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from scamguard.db import db
from scamguard.models import (
    EmailToken,
    Entity,
    EntityType,
    File,
    Report,
    ReportCategory,
    ReportStatus,
    Review,
    ReviewStatus,
    User,
)
from scamguard.services import submit_review
from scamguard.uploads import save_upload

RATING_ERROR = b"Rating must be between 1 and 5."
EMPTY_BODY_ERROR = b"Please write a review."
LONG_BODY_ERROR = b"2000 characters"
DUPLICATE_ERROR = b"You already reviewed this entity."
PROOF_SAVE_ERROR = b"could not save that proof file"
PROOF_LABEL = b"Proof of payment / order (required to publish)"


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


def _proof(filename="receipt.png", content=b"fake-png-bytes", content_type="image/png"):
    return FileStorage(stream=io.BytesIO(content), filename=filename, content_type=content_type)


def _add_token(user, raw="verify-token"):
    token = EmailToken(
        user=user,
        token=raw,
        expires_at=_utcnow() + timedelta(hours=24),
    )
    db.session.add(token)
    db.session.commit()
    return token


def _review_count():
    return db.session.execute(db.select(db.func.count()).select_from(Review)).scalar_one()


# --- Gate matrix: submit_review ---


def test_business_review_without_proof_stays_pending(ctx):
    user = _add_user()
    entity = _entity(EntityType.INSTAGRAM, "2", "@sh****op")

    review, error = submit_review(user, entity, 4, "looks legit", None)

    assert error is None
    assert review.status == ReviewStatus.PENDING
    assert review.proof_file_id is None


def test_business_review_without_proof_not_shown_on_entity_page(client, ctx):
    user = _add_user()
    entity = _entity(EntityType.INSTAGRAM, "2", "@sh****op")
    _login(client)

    resp = client.post(
        f"/review/{entity.id}",
        data={"rating": "4", "body": "PENDING-BIZ-BODY"},
    )
    assert resp.status_code == 302

    page = client.get(f"/entity/{entity.id}")
    assert b"PENDING-BIZ-BODY" not in page.data
    assert _review_count() == 1


def test_business_review_with_proof_by_verified_user_is_published(ctx):
    user = _add_user(verified=True)
    entity = _entity(EntityType.FACEBOOK, "3", "facebook.com/mar…")

    review, error = submit_review(user, entity, 5, "paid, got the goods", _proof())

    assert error is None
    assert review.status == ReviewStatus.PUBLISHED
    assert review.proof_file_id is not None


def test_business_review_with_proof_shows_stars_and_badge_on_entity_page(client, ctx):
    user = _add_user(verified=True)
    entity = _entity(EntityType.INSTAGRAM, "2", "@sh****op")
    _login(client)

    resp = client.post(
        f"/review/{entity.id}",
        data={
            "rating": "4",
            "body": "PROOF-BIZ-BODY",
            "proof": (io.BytesIO(b"png-bytes"), "receipt.png"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302

    page = client.get(f"/entity/{entity.id}")
    assert b"PROOF-BIZ-BODY" in page.data
    assert b"Verified with proof" in page.data
    assert ("★" * 4 + "☆").encode() in page.data


def test_business_review_with_proof_by_unverified_user_promotes_on_verify(client, ctx):
    user = _add_user(verified=False)
    entity = _entity(EntityType.FACEBOOK, "3", "facebook.com/mar…")

    review, error = submit_review(user, entity, 2, "waiting for verify", _proof())
    assert error is None
    assert review.status == ReviewStatus.PENDING

    _add_token(user, raw="flip-token")
    resp = client.get("/verify?token=flip-token")
    assert resp.status_code == 200

    db.session.expire_all()
    refreshed = db.session.get(Review, review.id)
    assert refreshed.status == ReviewStatus.PUBLISHED

    page = client.get(f"/entity/{entity.id}")
    assert b"waiting for verify" in page.data


def test_phone_review_by_verified_user_is_published(ctx):
    user = _add_user(verified=True)
    entity = _entity(EntityType.PHONE)

    review, error = submit_review(user, entity, 5, "genuine seller", None)

    assert error is None
    assert review.status == ReviewStatus.PUBLISHED


def test_phone_review_by_unverified_user_is_pending(client, ctx):
    user = _add_user(verified=False)
    entity = _entity(EntityType.PHONE)

    review, error = submit_review(user, entity, 5, "not yet public", None)

    assert error is None
    assert review.status == ReviewStatus.PENDING

    _add_token(user, raw="phone-token")
    client.get("/verify?token=phone-token")
    db.session.expire_all()
    assert db.session.get(Review, review.id).status == ReviewStatus.PUBLISHED


def test_duplicate_review_rejected(ctx):
    user = _add_user()
    entity = _entity(EntityType.PHONE)

    first, error = submit_review(user, entity, 3, "first take", None)
    assert error is None

    second, error = submit_review(user, entity, 1, "second take", None)

    assert second is None
    assert error == "You already reviewed this entity."
    assert _review_count() == 1


@pytest.mark.parametrize("rating", [0, 6, -1, None])
def test_rating_out_of_range_rejected(ctx, rating):
    user = _add_user()
    entity = _entity(EntityType.PHONE)

    review, error = submit_review(user, entity, rating, "text", None)

    assert review is None
    assert error == "Rating must be between 1 and 5."
    assert _review_count() == 0


@pytest.mark.parametrize("body", ["", "   ", "\n\t"])
def test_empty_body_rejected(ctx, body):
    user = _add_user()
    entity = _entity(EntityType.PHONE)

    review, error = submit_review(user, entity, 4, body, None)

    assert review is None
    assert error == "Please write a review."
    assert _review_count() == 0


def test_body_over_2000_chars_rejected(ctx):
    user = _add_user()
    entity = _entity(EntityType.PHONE)

    review, error = submit_review(user, entity, 4, "x" * 2001, None)

    assert review is None
    assert "2000 characters" in error
    assert _review_count() == 0


# --- save_upload ---


def test_save_upload_writes_file_to_disk_and_persists_row(ctx, tmp_path):
    user = _add_user()

    stored = save_upload(_proof(filename="ORDER.PDF", content_type="application/pdf"), user)

    assert stored is not None
    assert re.fullmatch(r"[0-9a-f]{16}\.pdf", stored.stored_name)
    assert stored.original_name == "ORDER.PDF"
    assert stored.size == len(b"fake-png-bytes")
    assert stored.uploader_id == user.id
    assert os.path.isfile(os.path.join(str(tmp_path), stored.stored_name))


def test_save_upload_rejects_disallowed_extension(ctx, tmp_path):
    user = _add_user()

    stored = save_upload(_proof(filename="payload.exe", content_type="application/octet-stream"), user)

    assert stored is None
    assert os.listdir(tmp_path) == []
    assert db.session.execute(db.select(db.func.count()).select_from(File)).scalar_one() == 0


def test_save_upload_rejects_empty_filename(ctx):
    user = _add_user()

    assert save_upload(_proof(filename=""), user) is None
    assert save_upload(None, user) is None


def test_save_upload_rejects_zero_byte_file(ctx, tmp_path):
    user = _add_user()

    assert save_upload(_proof(content=b""), user) is None
    assert os.listdir(tmp_path) == []


def test_save_upload_rejects_oversized_stream(ctx, tmp_path):
    user = _add_user()
    oversized = _proof(content=b"x" * (5 * 1024 * 1024 + 1))

    assert save_upload(oversized, user) is None
    assert os.listdir(tmp_path) == []


# --- Review form routes ---


def test_review_form_requires_login(client, ctx):
    entity = _entity(EntityType.PHONE)

    get_resp = client.get(f"/review/{entity.id}")
    post_resp = client.post(f"/review/{entity.id}", data={"rating": "5", "body": "hi"})

    for resp in (get_resp, post_resp):
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
    assert _review_count() == 0


def test_review_form_unknown_entity_404(client, ctx):
    _add_user()
    _login(client)

    assert client.get("/review/999").status_code == 404


def test_review_form_get_renders_star_picker(client, ctx):
    user = _add_user()
    entity = _entity(EntityType.PHONE)
    _login(client)

    resp = client.get(f"/review/{entity.id}")

    assert resp.status_code == 200
    assert b'name="rating"' in resp.data
    assert b'type="radio"' in resp.data
    assert b"<textarea" in resp.data


def test_review_form_shows_proof_field_for_business_only(client, ctx):
    _add_user()
    entity_phone = _entity(EntityType.PHONE, "1", "03**-***-1111")
    entity_ig = _entity(EntityType.INSTAGRAM, "2", "@sh****op")
    _login(client)

    phone_page = client.get(f"/review/{entity_phone.id}")
    ig_page = client.get(f"/review/{entity_ig.id}")

    assert b'name="proof"' not in phone_page.data
    assert PROOF_LABEL not in phone_page.data
    assert b'name="proof"' in ig_page.data
    assert PROOF_LABEL in ig_page.data
    assert b"multipart/form-data" in ig_page.data


def test_review_post_success_redirects_to_entity_page(client, ctx):
    _add_user(verified=True)
    entity = _entity(EntityType.PHONE)
    _login(client)

    resp = client.post(
        f"/review/{entity.id}",
        data={"rating": "5", "body": "all good here"},
    )

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/entity/{entity.id}")
    page = client.get(f"/entity/{entity.id}")
    assert b"all good here" in page.data


def test_phone_review_from_unverified_user_flashes_verify_email(client, ctx):
    _add_user(verified=False)
    entity = _entity(EntityType.PHONE)
    _login(client)

    resp = client.post(
        f"/review/{entity.id}",
        data={"rating": "5", "body": "waiting for verify"},
    )
    assert resp.status_code == 302

    page = client.get(resp.headers["Location"])
    assert b"verify your email to publish it" in page.data
    assert b"upload proof of payment" not in page.data


def test_business_review_without_proof_flash_explains_stays_private(client, ctx):
    _add_user(verified=True)
    entity = _entity(EntityType.INSTAGRAM, "2", "@sh****op")
    _login(client)

    resp = client.post(
        f"/review/{entity.id}",
        data={"rating": "3", "body": "no receipt"},
    )
    assert resp.status_code == 302

    page = client.get(resp.headers["Location"])
    assert b"need proof of payment at submission to be published" in page.data
    assert b"upload proof of payment to publish it" not in page.data


def test_business_review_with_proof_pending_flashes_verify_email(client, ctx):
    _add_user(verified=False)
    entity = _entity(EntityType.FACEBOOK, "3", "facebook.com/mar…")
    _login(client)

    resp = client.post(
        f"/review/{entity.id}",
        data={
            "rating": "4",
            "body": "proof given, not verified",
            "proof": (io.BytesIO(b"png-bytes"), "receipt.png"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302

    page = client.get(resp.headers["Location"])
    assert b"will go public once your email is verified" in page.data
    assert b"upload proof of payment" not in page.data


def test_review_post_rejects_out_of_range_rating(client, ctx):
    _add_user()
    entity = _entity(EntityType.PHONE)
    _login(client)

    resp = client.post(
        f"/review/{entity.id}",
        data={"rating": "0", "body": "sneaky"},
    )

    assert resp.status_code == 200
    assert RATING_ERROR in resp.data
    assert _review_count() == 0


def test_review_post_missing_rating_rejected(client, ctx):
    _add_user()
    entity = _entity(EntityType.PHONE)
    _login(client)

    resp = client.post(f"/review/{entity.id}", data={"body": "no rating given"})

    assert resp.status_code == 200
    assert RATING_ERROR in resp.data
    assert _review_count() == 0


def test_review_post_with_exe_proof_shows_error(client, ctx):
    _add_user(verified=True)
    entity = _entity(EntityType.INSTAGRAM, "2", "@sh****op")
    _login(client)

    resp = client.post(
        f"/review/{entity.id}",
        data={
            "rating": "5",
            "body": "trust me",
            "proof": (io.BytesIO(b"MZ..."), "totally-a-receipt.exe"),
        },
        content_type="multipart/form-data",
    )

    assert resp.status_code == 200
    assert PROOF_SAVE_ERROR in resp.data
    assert _review_count() == 0


# --- Proof file access ---


def _make_file(user, filename="receipt.png", content=b"png-bytes"):
    stored = save_upload(_proof(filename=filename, content=content), user)
    assert stored is not None
    return stored


def test_uploader_can_view_own_proof(client, ctx):
    user = _add_user()
    stored = _make_file(user)
    _login(client)

    resp = client.get(f"/files/{stored.id}")

    assert resp.status_code == 200
    assert resp.data == b"png-bytes"
    assert "receipt.png" in resp.headers.get("Content-Disposition", "")


def test_other_user_cannot_view_proof(client, ctx):
    uploader = _add_user("ada@example.com")
    stored = _make_file(uploader)
    _add_user("mallory@example.com")
    _login(client, "mallory@example.com")

    assert client.get(f"/files/{stored.id}").status_code == 403


def test_anonymous_cannot_view_proof(client, ctx):
    user = _add_user()
    stored = _make_file(user)

    resp = client.get(f"/files/{stored.id}")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_unknown_file_404(client, ctx):
    _add_user()
    _login(client)

    assert client.get("/files/999").status_code == 404


# --- My activity ---


def test_my_activity_shows_pending_review_status_chips(client, ctx):
    user = _add_user(verified=False)
    phone = _entity(EntityType.PHONE, "1", "03**-***-1111")
    ig = _entity(EntityType.INSTAGRAM, "2", "@sh****op")
    fb = _entity(EntityType.FACEBOOK, "3", "facebook.com/mar…")
    submit_review(user, phone, 5, "phone pending", None)
    submit_review(user, ig, 3, "biz needs proof", None)
    submit_review(user, fb, 4, "biz has proof", _proof())
    _login(client)

    resp = client.get("/my-activity")

    assert resp.status_code == 200
    assert resp.data.count(b"Awaiting email verification") >= 2
    assert b"Missing proof" in resp.data
    assert b"phone pending" in resp.data
    assert b"03**-***-1111" in resp.data


def test_my_activity_shows_published_chips_and_proof_badge(client, ctx):
    user = _add_user(verified=True)
    phone = _entity(EntityType.PHONE, "1", "03**-***-1111")
    fb = _entity(EntityType.FACEBOOK, "3", "facebook.com/mar…")
    submit_review(user, phone, 5, "live phone review", None)
    submit_review(user, fb, 5, "live biz review", _proof())
    _login(client)

    resp = client.get("/my-activity")

    assert resp.status_code == 200
    assert resp.data.count(b"Published") >= 2
    assert b"Verified with proof" in resp.data
    assert b"live biz review" in resp.data


def test_my_activity_shows_reports_with_category_and_status(client, ctx):
    user = _add_user(verified=True)
    entity = _entity(EntityType.PHONE)
    db.session.add(
        Report(
            entity=entity,
            user=user,
            category=ReportCategory.FAKE_PAYMENT_REQUEST,
            description="asked for advance payment",
            status=ReportStatus.PUBLISHED,
        )
    )
    db.session.commit()
    _login(client)

    resp = client.get("/my-activity")

    assert resp.status_code == 200
    assert b"Fake Payment Request" in resp.data
    assert b"asked for advance payment" in resp.data
    assert b"Published" in resp.data


def test_my_activity_pending_report_chip(client, ctx):
    user = _add_user(verified=False)
    entity = _entity(EntityType.PHONE)
    db.session.add(
        Report(
            entity=entity,
            user=user,
            category=ReportCategory.PHISHING,
            description="fake login page",
            status=ReportStatus.PENDING,
        )
    )
    db.session.commit()
    _login(client)

    resp = client.get("/my-activity")

    assert b"Phishing" in resp.data
    assert b"Awaiting email verification" in resp.data
