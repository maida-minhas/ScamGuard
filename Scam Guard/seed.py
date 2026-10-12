"""Idempotent demo seed for ScamGuard.

Run from the repo root with the app's interpreter:

    .venv\\Scripts\\python seed.py

Safe to re-run: every row is looked up before it is inserted, so no
duplicate-key errors and no duplicated content.
"""

from __future__ import annotations

import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from werkzeug.security import generate_password_hash

from scamguard import create_app
from scamguard.db import db
from scamguard.entities import find_or_create_entity
from scamguard.models import (
    Entity,
    File,
    Report,
    ReportCategory,
    ReportStatus,
    Review,
    ReviewStatus,
    User,
)

DEMO_EMAIL = "demo@scamguard.local"
DEMO_PASSWORD = "DemoPass123!"
NEW_EMAIL = "new@scamguard.local"
NEW_PASSWORD = "DemoPass123!"
SEED_PROOF_NAME = "seed-proof.png"

PHONE_INPUT = "03001234567"
INSTAGRAM_INPUT = "@fashionshop.pk"
FACEBOOK_INPUT = "facebook.com/marketplace/item/12345/"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _tiny_png() -> bytes:
    """Return a valid 1x1 RGBA PNG (70 bytes)."""
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00\x00\xff")
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _ensure_user(email: str, password: str, *, verified: bool) -> User:
    user = db.session.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()
    if user is not None:
        return user
    user = User(email=email, password_hash=generate_password_hash(password))
    if verified:
        user.email_verified_at = _utcnow()
    db.session.add(user)
    db.session.commit()
    return user


def _ensure_review(
    user: User,
    entity: Entity,
    rating: int,
    body: str,
    status: ReviewStatus,
    proof_file: File | None = None,
) -> Review:
    review = db.session.execute(
        select(Review).where(
            Review.user_id == user.id, Review.entity_id == entity.id
        )
    ).scalar_one_or_none()
    if review is not None:
        return review
    review = Review(
        entity_id=entity.id,
        user_id=user.id,
        rating=rating,
        body=body,
        status=status,
        proof_file_id=proof_file.id if proof_file is not None else None,
    )
    db.session.add(review)
    db.session.commit()
    return review


def _ensure_report(
    user: User,
    entity: Entity,
    category: ReportCategory,
    description: str,
    status: ReportStatus,
) -> Report:
    report = db.session.execute(
        select(Report).where(
            Report.user_id == user.id, Report.entity_id == entity.id
        )
    ).scalar_one_or_none()
    if report is not None:
        return report
    report = Report(
        entity_id=entity.id,
        user_id=user.id,
        category=category,
        description=description,
        status=status,
    )
    db.session.add(report)
    db.session.commit()
    return report


def _ensure_proof_file(uploader: User, upload_folder: str) -> File:
    png = _tiny_png()
    folder = Path(upload_folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / SEED_PROOF_NAME
    if not path.exists():
        path.write_bytes(png)

    proof = db.session.execute(
        select(File).where(File.stored_name == SEED_PROOF_NAME)
    ).scalar_one_or_none()
    if proof is not None:
        return proof
    proof = File(
        uploader_id=uploader.id,
        stored_name=SEED_PROOF_NAME,
        original_name="receipt.png",
        mime_type="image/png",
        size=len(png),
    )
    db.session.add(proof)
    db.session.commit()
    return proof


def _count(model) -> int:
    return db.session.execute(select(func.count()).select_from(model)).scalar_one()


def main() -> None:
    app = create_app()
    with app.app_context():
        db.create_all()

        demo = _ensure_user(DEMO_EMAIL, DEMO_PASSWORD, verified=True)
        new_user = _ensure_user(NEW_EMAIL, NEW_PASSWORD, verified=False)

        phone = find_or_create_entity(PHONE_INPUT)
        instagram = find_or_create_entity(INSTAGRAM_INPUT)
        facebook = find_or_create_entity(FACEBOOK_INPUT)

        proof = _ensure_proof_file(demo, app.config["UPLOAD_FOLDER"])

        _ensure_review(
            demo,
            phone,
            5,
            "Paid in advance and the item arrived on time. Genuine seller.",
            ReviewStatus.PUBLISHED,
        )
        _ensure_review(
            new_user,
            phone,
            4,
            "Quick replies, waiting to hear back from others before I trust it.",
            ReviewStatus.PENDING,
        )
        _ensure_review(
            demo,
            instagram,
            2,
            "Order never shipped and support stopped replying. Attached my receipt.",
            ReviewStatus.PUBLISHED,
            proof_file=proof,
        )
        _ensure_report(
            demo,
            instagram,
            ReportCategory.FAKE_PAYMENT_REQUEST,
            "Asked for advance payment, then blocked me once it was sent.",
            ReportStatus.PUBLISHED,
        )

        totals = {
            "users": _count(User),
            "entities": _count(Entity),
            "reviews": _count(Review),
            "reports": _count(Report),
            "files": _count(File),
        }
        phone_label = phone.display_masked
        instagram_label = instagram.display_masked
        facebook_label = facebook.display_masked

    print("ScamGuard seed complete (idempotent, safe to re-run).")
    print(f"  users:   {totals['users']} "
          f"({DEMO_EMAIL} / {DEMO_PASSWORD} verified, "
          f"{NEW_EMAIL} / {NEW_PASSWORD} unverified)")
    print(f"  entities: {totals['entities']} "
          f"(phone {phone_label}, instagram {instagram_label}, "
          f"facebook {facebook_label})")
    print(f"  reviews:  {totals['reviews']}")
    print(f"  reports:  {totals['reports']}")
    print(f"  files:    {totals['files']} (uploads/{SEED_PROOF_NAME})")


if __name__ == "__main__":
    main()
