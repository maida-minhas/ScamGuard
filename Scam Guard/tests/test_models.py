from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

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
def session(app):
    with app.app_context():
        db.create_all()
        yield db.session
        db.session.rollback()
        db.drop_all()


def test_create_and_persist_all_rows(session):
    user = User(email="ada@example.com", password_hash="hashed-secret")
    entity = Entity(
        type=EntityType.PHONE,
        identifier_hash="a" * 64,
        display_masked="03**-***-4567",
    )
    proof = File(
        uploader=user,
        stored_name="proof-1.png",
        original_name="receipt.png",
        mime_type="image/png",
        size=1234,
    )
    review = Review(entity=entity, user=user, rating=5, body="Legit seller.")
    review.proof_file = proof
    report = Report(
        entity=entity,
        user=user,
        category=ReportCategory.FAKE_SELLER,
        description="Took the money, never delivered.",
    )
    token = EmailToken(user=user, token="url-safe-token", expires_at=datetime(2030, 1, 1))

    session.add_all([user, entity, proof, review, report, token])
    session.commit()

    saved_user = session.get(User, user.id)
    assert saved_user.email == "ada@example.com"
    assert saved_user.email_verified_at is None
    assert saved_user.created_at is not None

    saved_entity = session.get(Entity, entity.id)
    assert saved_entity.type == EntityType.PHONE
    assert saved_entity.identifier_hash == "a" * 64
    assert saved_entity.display_masked == "03**-***-4567"
    assert saved_entity.created_at is not None

    saved_review = session.get(Review, review.id)
    assert saved_review.rating == 5
    assert saved_review.body == "Legit seller."
    assert saved_review.proof_file.original_name == "receipt.png"
    assert saved_review.user.email == "ada@example.com"
    assert saved_review.entity.type == EntityType.PHONE

    saved_report = session.get(Report, report.id)
    assert saved_report.category == ReportCategory.FAKE_SELLER
    assert saved_report.description == "Took the money, never delivered."

    saved_file = session.get(File, proof.id)
    assert saved_file.stored_name == "proof-1.png"
    assert saved_file.mime_type == "image/png"
    assert saved_file.size == 1234
    assert saved_file.uploader.email == "ada@example.com"

    saved_token = session.get(EmailToken, token.id)
    assert saved_token.purpose == "verify_email"
    assert saved_token.used_at is None
    assert saved_token.user.email == "ada@example.com"


def test_unique_user_entity_review(session):
    user = User(email="dup@example.com", password_hash="hashed")
    entity = Entity(
        type=EntityType.INSTAGRAM,
        identifier_hash="b" * 64,
        display_masked="@sh**.pk",
    )
    session.add_all([user, entity])
    session.commit()

    session.add(Review(entity=entity, user=user, rating=4, body="first"))
    session.commit()

    session.add(Review(entity=entity, user=user, rating=1, body="duplicate"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_unique_user_entity_report(session):
    user = User(email="dup-report@example.com", password_hash="hashed")
    entity = Entity(
        type=EntityType.FACEBOOK,
        identifier_hash="c" * 64,
        display_masked="www.facebook.com/mar…",
    )
    session.add_all([user, entity])
    session.commit()

    session.add(
        Report(entity=entity, user=user, category=ReportCategory.PHISHING, description="first")
    )
    session.commit()

    session.add(
        Report(entity=entity, user=user, category=ReportCategory.OTHER, description="duplicate")
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_review_default_status_pending(session):
    user = User(email="pending@example.com", password_hash="hashed")
    entity = Entity(
        type=EntityType.PHONE,
        identifier_hash="d" * 64,
        display_masked="03**-***-4567",
    )
    session.add_all([user, entity])
    session.commit()

    review = Review(entity=entity, user=user, rating=3, body="okay")
    session.add(review)
    session.flush()

    assert review.status == ReviewStatus.PENDING


def test_init_db_cli_creates_tables_and_persists_row(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["init-db"])

    assert result.exit_code == 0, result.output
    assert "Initialized the database" in result.output

    with app.app_context():
        user = User(email="cli@example.com", password_hash="hashed")
        db.session.add(user)
        db.session.commit()

        saved = db.session.get(User, user.id)
        assert saved is not None
        assert saved.email == "cli@example.com"
