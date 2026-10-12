from flask import Flask, render_template
from flask_login import LoginManager

from scamguard import cli, models  # noqa: F401
from scamguard.auth import bp as auth_bp
from scamguard.config import Config
from scamguard.db import db
from scamguard.entities import bp as entities_bp
from scamguard.file_routes import bp as files_bp
from scamguard.models import (
    Entity,
    Report,
    ReportStatus,
    Review,
    ReviewStatus,
    User,
)
from scamguard.reports import bp as reports_bp
from scamguard.reviews import bp as reviews_bp

login_manager = LoginManager()


def _load_user(user_id: str):
    return db.session.get(User, int(user_id))


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    cli.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)
    login_manager.user_loader(_load_user)
    app.register_blueprint(auth_bp)
    app.register_blueprint(entities_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(files_bp)

    @app.route("/")
    def index():
        entity_count = db.session.scalar(db.select(db.func.count()).select_from(Entity))
        review_count = db.session.scalar(
            db.select(db.func.count())
            .select_from(Review)
            .where(Review.status == ReviewStatus.PUBLISHED)
        )
        report_count = db.session.scalar(
            db.select(db.func.count())
            .select_from(Report)
            .where(Report.status == ReportStatus.PUBLISHED)
        )
        return render_template(
            "index.html",
            entity_count=entity_count,
            review_count=review_count,
            report_count=report_count,
        )

    return app
