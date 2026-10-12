import pytest

from scamguard.ai_insights import (
    review_tone,
    sentiment_score,
    suggest_category,
    summarize_reviews,
)
from scamguard.models import Review


@pytest.fixture
def ctx(app):
    from scamguard.db import db

    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app, ctx):
    return app.test_client()


def test_positive_text_scores_positive():
    assert sentiment_score("genuine seller, fast delivery, highly trusted") > 0


def test_negative_text_scores_negative():
    assert sentiment_score("total scam, ghosted me, never again") < 0


def test_negation_flips_positive_word():
    assert sentiment_score("the item was not good") < 0


def test_neutral_text_scores_zero():
    assert sentiment_score("delivered on tuesday afternoon") == 0


def test_review_tone_labels():
    assert review_tone("wonderful and reliable") == "positive"
    assert review_tone("fake products, want my money back") == "negative"
    assert review_tone("bought two items") == "neutral"


def test_one_star_review_is_negative_even_with_plain_words():
    assert review_tone("i dont like it", rating=1) == "negative"


def test_five_star_review_is_positive_even_with_plain_words():
    assert review_tone("bought two items", rating=5) == "positive"


def test_summarize_counts_one_star_plain_review_as_negative():
    summary = summarize_reviews([Review(rating=1, body="i dont like it")])

    assert summary["negative"] == 1
    assert summary["positive"] == 0


def test_summarize_counts_and_sentence():
    reviews = [
        Review(rating=5, body="genuine seller, trusted and fast"),
        Review(rating=5, body="great experience, highly recommended"),
        Review(rating=1, body="scam, never received my order"),
    ]
    summary = summarize_reviews(reviews)

    assert summary["total"] == 3
    assert summary["positive"] == 2
    assert summary["negative"] == 1
    assert summary["neutral"] == 0
    assert "2 of 3 reviews are positive" in summary["sentence"]


def test_summarize_extracts_topics():
    reviews = [
        Review(rating=5, body="fast delivery and smooth payment"),
        Review(rating=4, body="good quality item, delivery was quick"),
    ]
    summary = summarize_reviews(reviews)

    assert "delivery" in summary["topics"]
    assert len(summary["topics"]) <= 3


def test_summarize_empty_reviews():
    summary = summarize_reviews([])

    assert summary["total"] == 0
    assert summary["topics"] == []
    assert "No reviews yet" in summary["sentence"]


def test_suggest_payment_fraud():
    assert suggest_category("he asked for an advance payment fee") == "FAKE_PAYMENT_REQUEST"


def test_suggest_non_delivery():
    assert suggest_category("never received the parcel after paying") == "NON_DELIVERY"


def test_suggest_fake_seller():
    assert suggest_category("sent me a fake replica product") == "FAKE_SELLER"


def test_suggest_phishing():
    assert suggest_category("clicked the link and shared my otp password") == "PHISHING"


def test_suggest_no_match_returns_none():
    assert suggest_category("hello there") is None


# --- entity page: AI insights box ---


def _seeded_entity_with_review(ctx, status=None):
    from datetime import datetime, timezone

    from scamguard.db import db
    from scamguard.models import Entity, EntityType, ReviewStatus, User
    from werkzeug.security import generate_password_hash

    user = User(
        email="ai@example.com",
        password_hash=generate_password_hash("secret123"),
        email_verified_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    entity = Entity(
        type=EntityType.PHONE,
        identifier_hash="a" * 64,
        display_masked="03**-***-1111",
    )
    db.session.add_all([user, entity])
    db.session.commit()
    review = Review(
        entity_id=entity.id,
        user_id=user.id,
        rating=5,
        body="genuine seller, fast and highly trusted",
        status=status or ReviewStatus.PUBLISHED,
    )
    db.session.add(review)
    db.session.commit()
    return entity


def test_entity_page_shows_ai_insights_box(client, ctx):
    entity = _seeded_entity_with_review(ctx)

    page = client.get(f"/entity/{entity.id}")

    assert b"What people say" in page.data
    assert b"1 of 1 reviews are positive" in page.data


def test_entity_page_hides_insights_without_published_reviews(client, ctx):
    from scamguard.models import ReviewStatus

    entity = _seeded_entity_with_review(ctx, status=ReviewStatus.PENDING)

    page = client.get(f"/entity/{entity.id}")

    assert b"What people say" not in page.data


def test_review_shows_tone_label(client, ctx):
    entity = _seeded_entity_with_review(ctx)

    page = client.get(f"/entity/{entity.id}")

    assert b"Positive" in page.data


# --- /ai/suggest route ---


def test_suggest_route_returns_category(client, ctx):
    resp = client.post("/ai/suggest", json={"text": "shared my otp on a fake link"})

    assert resp.status_code == 200
    assert resp.get_json()["category"] == "PHISHING"


def test_suggest_route_no_match_returns_null(client, ctx):
    resp = client.post("/ai/suggest", json={"text": "hello there"})

    assert resp.status_code == 200
    assert resp.get_json()["category"] is None


def test_suggest_route_empty_text_is_bad_request(client, ctx):
    resp = client.post("/ai/suggest", json={"text": ""})

    assert resp.status_code == 400


def test_suggest_route_requires_post(client, ctx):
    resp = client.get("/ai/suggest")

    assert resp.status_code == 405
