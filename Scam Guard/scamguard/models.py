from __future__ import annotations

import enum
from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from scamguard.db import db


def _enum(enum_cls, name: str) -> SAEnum:
    return SAEnum(enum_cls, name=name, values_callable=lambda cls: [m.value for m in cls])


class EntityType(str, enum.Enum):
    PHONE = "PHONE"
    INSTAGRAM = "INSTAGRAM"
    FACEBOOK = "FACEBOOK"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    HIDDEN = "hidden"


class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    HIDDEN = "hidden"


class ReportCategory(str, enum.Enum):
    FAKE_PAYMENT_REQUEST = "FAKE_PAYMENT_REQUEST"
    NON_DELIVERY = "NON_DELIVERY"
    FAKE_SELLER = "FAKE_SELLER"
    PHISHING = "PHISHING"
    OTHER = "OTHER"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    reviews: Mapped[list[Review]] = relationship(back_populates="user")
    reports: Mapped[list[Report]] = relationship(back_populates="user")
    files: Mapped[list[File]] = relationship(back_populates="uploader")
    email_tokens: Mapped[list[EmailToken]] = relationship(back_populates="user")


class EmailToken(db.Model):
    __tablename__ = "email_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="verify_email")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="email_tokens")


class Entity(db.Model):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[EntityType] = mapped_column(_enum(EntityType, "entity_type"), nullable=False)
    identifier_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_masked: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    reviews: Mapped[list[Review]] = relationship(back_populates="entity")
    reports: Mapped[list[Report]] = relationship(back_populates="entity")


class Review(db.Model):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_id", name="uq_reviews_user_entity"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(
        _enum(ReviewStatus, "review_status"),
        nullable=False,
        default=ReviewStatus.PENDING,
    )
    proof_file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    entity: Mapped[Entity] = relationship(back_populates="reviews")
    user: Mapped[User] = relationship(back_populates="reviews")
    proof_file: Mapped[File | None] = relationship()


class Report(db.Model):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("user_id", "entity_id", name="uq_reports_user_entity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    category: Mapped[ReportCategory] = mapped_column(
        _enum(ReportCategory, "report_category"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        _enum(ReportStatus, "report_status"),
        nullable=False,
        default=ReportStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    entity: Mapped[Entity] = relationship(back_populates="reports")
    user: Mapped[User] = relationship(back_populates="reports")


class File(db.Model):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    uploader: Mapped[User] = relationship(back_populates="files")
