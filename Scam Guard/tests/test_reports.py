import pytest
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
from scamguard.services import submit_report

CATEGORY_ERROR = b"Choose a valid report category."
EMPTY_DESCRIPTION_ERROR = b"Please describe the problem."
LONG_DESCRIPTION_ERROR = b"2000 characters"
DUPLICATE_ERROR = b"You already reported this entity."


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
    from datetime import datetime, timezone

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


def _report_count():
    return db.session.execute(db.select(db.func.count()).select_from(Report)).scalar_one()


# --- submit_report service ---


def test_verified_user_report_is_published(ctx):
    user = _add_user(verified=True)
    entity = _entity()

    report, error = submit_report(user, entity, "PHISHING", "fake login page")

    assert error is None
    assert report.status == ReportStatus.PUBLISHED
    assert report.category == ReportCategory.PHISHING
    assert report.description == "fake login page"


def test_unverified_user_report_is_pending(ctx):
    user = _add_user(verified=False)
    entity = _entity()

    report, error = submit_report(user, entity, ReportCategory.NON_DELIVERY, "never arrived")

    assert error is None
    assert report.status == ReportStatus.PENDING


def test_duplicate_report_rejected(ctx):
    user = _add_user()
    entity = _entity()

    first, error = submit_report(user, entity, "PHISHING", "first report")
    assert error is None

    second, error = submit_report(user, entity, "PHISHING", "second report")

    assert second is None
    assert error == "You already reported this entity."
    assert _report_count() == 1


@pytest.mark.parametrize("category", ["NOT_A_CATEGORY", "phishing", "", None])
def test_invalid_category_rejected(ctx, category):
    user = _add_user()
    entity = _entity()

    report, error = submit_report(user, entity, category, "some description")

    assert report is None
    assert error == "Choose a valid report category."
    assert _report_count() == 0


@pytest.mark.parametrize("description", ["", "   ", "\n\t"])
def test_empty_description_rejected(ctx, description):
    user = _add_user()
    entity = _entity()

    report, error = submit_report(user, entity, "PHISHING", description)

    assert report is None
    assert error == "Please describe the problem."
    assert _report_count() == 0


def test_description_over_2000_chars_rejected(ctx):
    user = _add_user()
    entity = _entity()

    report, error = submit_report(user, entity, "OTHER", "x" * 2001)

    assert report is None
    assert "2000 characters" in error
    assert _report_count() == 0


# --- /report routes ---


def test_report_form_requires_login(client, ctx):
    entity = _entity()

    get_resp = client.get(f"/report/{entity.id}")
    post_resp = client.post(
        f"/report/{entity.id}", data={"category": "PHISHING", "description": "hi"}
    )

    for resp in (get_resp, post_resp):
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
    assert _report_count() == 0


def test_report_form_unknown_entity_404(client, ctx):
    _add_user()
    _login(client)

    assert client.get("/report/999").status_code == 404


def test_report_form_get_renders_category_select_and_textarea(client, ctx):
    _add_user()
    entity = _entity()
    _login(client)

    resp = client.get(f"/report/{entity.id}")

    assert resp.status_code == 200
    assert b'name="category"' in resp.data
    assert b'name="description"' in resp.data
    assert b"<textarea" in resp.data
    assert b"Fake Payment Request" in resp.data
    assert b"Non Delivery" in resp.data


def test_verified_user_report_shows_on_entity_page_and_risk_flips(client, ctx):
    _add_user(verified=True)
    entity = _entity()
    _login(client)

    resp = client.post(
        f"/report/{entity.id}",
        data={"category": "FAKE_PAYMENT_REQUEST", "description": "REPORT-BODY-XYZ"},
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/entity/{entity.id}?tab=reports")
    assert _report_count() == 1

    page = client.get(f"/entity/{entity.id}?tab=reports")
    assert b"Fake Payment Request" in page.data
    assert b"REPORT-BODY-XYZ" in page.data
    assert b"High risk" in page.data


def test_unverified_user_report_pending_not_on_page(client, ctx):
    _add_user(verified=False)
    entity = _entity()
    _login(client)

    resp = client.post(
        f"/report/{entity.id}",
        data={"category": "PHISHING", "description": "PENDING-REPORT-BODY"},
    )
    assert resp.status_code == 302

    reports = db.session.execute(db.select(Report)).scalars().all()
    assert len(reports) == 1
    assert reports[0].status == ReportStatus.PENDING

    page = client.get(f"/entity/{entity.id}?tab=reports")
    assert b"PENDING-REPORT-BODY" not in page.data
    assert b"High risk" not in page.data


def test_duplicate_post_rejected(client, ctx):
    _add_user()
    entity = _entity()
    _login(client)

    first = client.post(
        f"/report/{entity.id}",
        data={"category": "PHISHING", "description": "first take"},
    )
    assert first.status_code == 302

    second = client.post(
        f"/report/{entity.id}",
        data={"category": "PHISHING", "description": "second take"},
    )
    assert second.status_code == 200
    assert DUPLICATE_ERROR in second.data
    assert _report_count() == 1


def test_invalid_category_post_rejected(client, ctx):
    _add_user()
    entity = _entity()
    _login(client)

    resp = client.post(
        f"/report/{entity.id}",
        data={"category": "NOT_A_CATEGORY", "description": "sneaky"},
    )
    assert resp.status_code == 200
    assert CATEGORY_ERROR in resp.data
    assert _report_count() == 0


def test_empty_description_post_rejected(client, ctx):
    _add_user()
    entity = _entity()
    _login(client)

    resp = client.post(f"/report/{entity.id}", data={"category": "PHISHING"})
    assert resp.status_code == 200
    assert EMPTY_DESCRIPTION_ERROR in resp.data
    assert _report_count() == 0


def test_public_pages_never_render_raw_identifier(client, ctx):
    _add_user(verified=True)
    entity = _entity(suffix="9", masked="09**-***-9999")
    _login(client)
    client.post(
        f"/report/{entity.id}",
        data={"category": "OTHER", "description": "body for report page"},
    )

    entity_page = client.get(f"/entity/{entity.id}")
    report_form = client.get(f"/report/{entity.id}")

    for page in (entity_page, report_form):
        assert entity.identifier_hash.encode() not in page.data
        assert b"09**-***-9999" in page.data
