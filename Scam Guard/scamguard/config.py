import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{(REPO_ROOT / 'scamguard.db').as_posix()}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = str(REPO_ROOT / "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    DEMO_MODE = True
