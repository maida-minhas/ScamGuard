import pytest
from werkzeug.security import generate_password_hash

from scamguard.db import db
from scamguard.entities import find_or_create_entity
from scamguard.models import (
    Entity,
    EntityType,
    Report,
    ReportCategory,
    ReportStatus,
    Review,
    ReviewStatus,
    User,
)

FRIENDLY_ERROR = b"look like a phone number, Instagram handle, or Facebook link"


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


def _add_user(email="ada@example.com"):
    user = User(email=email, password_hash=generate_password_hash("secret123"))
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, email="ada@example.com", password="secret123"):
    return client.post("/login", data={"email": email, "password": password})


def _entity_count():
    return db.session.execute(db.select(db.func.count()).select_from(Entity)).scalar_one()


# --- find_or_create_entity (service) ---


def test_find_or_create_creates_entity_with_masked_display(ctx):
    entity = find_or_create_entity("03001234567")

    assert entity is not None
    assert entity.id is not None
    assert entity.type == EntityType.PHONE
    assert entity.display_masked == "03**-***-4567"
    assert len(entity.identifier_hash) == 64


def test_find_or_create_reuses_entity_for_equivalent_inputs(ctx):
    first = find_or_create_entity("03001234567")
    second = find_or_create_entity("+92 300-1234567")

    assert first.id == second.id
    assert _entity_count() == 1


def test_find_or_create_returns_none_for_undetectable_input(ctx):
    assert find_or_create_entity("hello world") is None
    assert _entity_count() == 0


def test_find_or_create_returns_none_for_unnormalizable_input(ctx):
    assert find_or_create_entity("@") is None
    assert _entity_count() == 0


def test_find_or_create_handles_instagram_and_facebook(ctx):
    ig = find_or_create_entity("@CoolShop.pk")
    fb = find_or_create_entity("https://www.facebook.com/marketplace.seller")

    assert ig.type == EntityType.INSTAGRAM
    assert ig.display_masked == "@co******.pk"
    assert fb.type == EntityType.FACEBOOK
    assert fb.display_masked == "facebook.com/marketp…"
    assert _entity_count() == 2


# --- GET /search ---


def test_search_without_q_redirects_to_index(client):
    resp = client.get("/search")

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_search_with_empty_q_redirects_to_index(client):
    resp = client.get("/search", query_string={"q": "   "})

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_search_undetectable_input_shows_friendly_error(client):
    resp = client.get("/search", query_string={"q": "hello world"})

    assert resp.status_code == 200
    assert FRIENDLY_ERROR in resp.data
    assert _entity_count() == 0


def test_search_phone_redirects_to_entity_page(client):
    resp = client.get("/search", query_string={"q": "03001234567"})

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/entity/1")


def test_search_repeated_searches_redirect_to_same_entity(client):
    first = client.get("/search", query_string={"q": "03001234567"})
    second = client.get("/search", query_string={"q": "+92 300-1234567"})

    assert first.headers["Location"] == second.headers["Location"]
    assert _entity_count() == 1


# --- GET /entity/<id> ---


def test_entity_unknown_id_returns_404(client):
    resp = client.get("/entity/999")

    assert resp.status_code == 404


def test_entity_page_shows_masked_and_never_raw_phone(client):
    client.get("/search", query_string={"q": "03001234567"})

    resp = client.get("/entity/1")

    assert resp.status_code == 200
    assert b"03**-***-4567" in resp.data
    assert b"03001234567" not in resp.data


def test_entity_page_never_shows_raw_instagram_handle(client):
    client.get("/search", query_string={"q": "@coolshop.pk"})

    resp = client.get("/entity/1")

    assert resp.status_code == 200
    assert b"coolshop" not in resp.data
    assert b"@co******.pk" in resp.data


def test_entity_page_header_placeholders(client):
    client.get("/search", query_string={"q": "03001234567"})

    resp = client.get("/entity/1")

    assert b"Phone" in resp.data
    assert b"No data" in resp.data
    assert "—".encode() in resp.data


def test_entity_page_default_tab_is_reviews_and_anonymous_sees_login_prompt(client):
    client.get("/search", query_string={"q": "03001234567"})

    resp = client.get("/entity/1")

    assert b"Log in to contribute" in resp.data
    assert b"/review/1" not in resp.data


def test_entity_page_empty_state_logged_in_links_to_review_and_report(client):
    _add_user()
    _login(client)
    client.get("/search", query_string={"q": "03001234567"})

    reviews = client.get("/entity/1")
    reports = client.get("/entity/1?tab=reports")

    assert b'href="/review/1"' in reviews.data
    assert b'href="/report/1"' in reports.data


def test_entity_page_reviews_tab_shows_published_reviews_only(client):
    a = _add_user("a@example.com")
    b = _add_user("b@example.com")
    entity = find_or_create_entity("03001234567")
    db.session.add_all(
        [
            Review(
                entity=entity,
                user=a,
                rating=5,
                body="Legit seller, fast delivery",
                status=ReviewStatus.PUBLISHED,
            ),
            Review(
                entity=entity,
                user=b,
                rating=1,
                body="PENDING-REVIEW-BODY",
                status=ReviewStatus.PENDING,
            ),
        ]
    )
    db.session.commit()

    resp = client.get(f"/entity/{entity.id}")

    assert b"Legit seller, fast delivery" in resp.data
    assert b"PENDING-REVIEW-BODY" not in resp.data


def test_entity_page_reports_tab_shows_published_reports_only(client):
    a = _add_user("a@example.com")
    b = _add_user("b@example.com")
    entity = find_or_create_entity("03001234567")
    db.session.add_all(
        [
            Report(
                entity=entity,
                user=a,
                category=ReportCategory.FAKE_SELLER,
                description="Took the money and vanished",
                status=ReportStatus.PUBLISHED,
            ),
            Report(
                entity=entity,
                user=b,
                category=ReportCategory.PHISHING,
                description="PENDING-REPORT-BODY",
                status=ReportStatus.PENDING,
            ),
        ]
    )
    db.session.commit()

    resp = client.get(f"/entity/{entity.id}?tab=reports")

    assert b"Took the money and vanished" in resp.data
    assert b"Fake Seller" in resp.data
    assert b"PENDING-REPORT-BODY" not in resp.data


def test_entity_page_avg_stars_and_counts_use_published_reviews(client):
    a = _add_user("a@example.com")
    b = _add_user("b@example.com")
    entity = find_or_create_entity("03001234567")
    db.session.add_all(
        [
            Review(
                entity=entity, user=a, rating=5, body="great", status=ReviewStatus.PUBLISHED
            ),
            Review(
                entity=entity, user=b, rating=4, body="fine", status=ReviewStatus.PUBLISHED
            ),
        ]
    )
    db.session.commit()

    resp = client.get(f"/entity/{entity.id}")

    assert b"4.5" in resp.data
    assert b"2 reviews" in resp.data
