import pytest

from scamguard.db import db
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


def test_landing_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"ScamGuard" in response.data


def test_landing_page_shows_site_stats(client):
    user = User(email="ada@example.com", password_hash="unused")
    phone = Entity(
        type=EntityType.PHONE, identifier_hash="1" * 64, display_masked="03**-***-1111"
    )
    ig = Entity(type=EntityType.INSTAGRAM, identifier_hash="2" * 64, display_masked="@sh****op")
    db.session.add_all([user, phone, ig])
    db.session.commit()
    db.session.add_all(
        [
            Review(
                entity=phone,
                user=user,
                rating=5,
                body="published review",
                status=ReviewStatus.PUBLISHED,
            ),
            Review(
                entity=ig,
                user=user,
                rating=1,
                body="pending review",
                status=ReviewStatus.PENDING,
            ),
            Report(
                entity=phone,
                user=user,
                category=ReportCategory.PHISHING,
                description="published report",
                status=ReportStatus.PUBLISHED,
            ),
            Report(
                entity=ig,
                user=user,
                category=ReportCategory.OTHER,
                description="pending report",
                status=ReportStatus.PENDING,
            ),
        ]
    )
    db.session.commit()

    resp = client.get("/")

    assert resp.status_code == 200
    assert "2 entities checked · 1 reviews · 1 reports" in resp.get_data(as_text=True)
