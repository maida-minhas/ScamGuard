# ScamGuard (Python) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Student-level Flask prototype: search a phone / Instagram handle / Facebook URL, read star reviews and scam reports; business reviews require uploaded proof of payment/order before going public.

**Architecture:** Single Flask app (app factory), Jinja2 + Tailwind CDN templates, SQLAlchemy 2 + SQLite, Flask-Login sessions, local `uploads/` dir served via authenticated route, pytest.

**Tech Stack:** Python 3.14, Flask 3, Flask-Login, Flask-SQLAlchemy, Werkzeug, pytest.

**Spec:** `docs/superpowers/specs/2026-10-11-scamguard-design.md`

## Global Constraints

- Student-level: no AI/OCR, no moderation queue, no SMTP (demo-mode on-screen verify token), no Docker.
- Python 3.14; venv at `.venv/` in repo root; run `python app.py` → http://localhost:5000.
- DB file: `scamguard.db` at repo root (gitignored). Uploads in `uploads/` (gitignored, keep `.gitkeep`).
- Public payloads NEVER include raw identifiers — only `display_masked`.
- Only `published` reviews/reports appear on public entity pages.
- Every task: write failing tests first, implement, green, commit.

---

### Task 1: Scaffold Flask app

**Files:**
- Create: `app.py` (entry: `python app.py`), `scamguard/__init__.py` (app factory `create_app()`), `scamguard/config.py`, `scamguard/db.py`, `scamguard/templates/base.html`, `scamguard/templates/index.html`, `requirements.txt`, `pytest.ini`, `uploads/.gitkeep`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `create_app(test_config=None)` — configures Flask, Flask-Login, SQLAlchemy; `scamguard.db` exposes `db` (SQLAlchemy instance).

Steps:
- [ ] Write `requirements.txt`: `flask`, `flask-login`, `flask-sqlalchemy`, `pytest`.
- [ ] App factory with config (`SECRET_KEY`, `SQLALCHEMY_DATABASE_URI=sqlite:///../scamguard.db` — resolve path relative to repo root so `scamguard.db` lands at root; `UPLOAD_FOLDER` = repo-root `uploads/`, `MAX_CONTENT_LENGTH = 5MB`, `DEMO_MODE=True`).
- [ ] `base.html`: Tailwind CDN, nav (logo → `/`, links: Search, Login/Register or My Activity/Logout), `{% block content %}`, flash-message area.
- [ ] `index.html`: hero search box posting to `/search`, short explainer cards (Reviews / Reports / Proof gate).
- [ ] Placeholder `/` route returning the template; health via `/` only (keep basic).
- [ ] `pytest.ini`: `testpaths = tests`; tests use app factory with in-memory SQLite override.
- [ ] Smoke test: client GET `/` → 200, contains "ScamGuard".
- [ ] Update `.gitignore`: add `.venv/`, `scamguard.db*`, `uploads/*` (!.gitkeep), `__pycache__/`.
- [ ] Run `pytest` green; commit `feat: flask scaffold with base template and landing page`.

### Task 2: Schema + normalization

**Files:**
- Create: `scamguard/models.py`, `scamguard/normalize.py`, `scamguard/cli.py`, `tests/test_normalize.py`, `tests/test_models.py`
- Modify: `scamguard/__init__.py` (register models, CLI `init-db`)

**Interfaces:**
- Produces (models): `User`, `EmailToken`, `Entity`, `Review`, `Report`, `File` exactly as spec §3; enums `EntityType`, `ReviewStatus`, `ReportCategory` as Python `str` enums.
- Produces (normalize): `detect_type(raw: str) -> EntityType | None`; `normalize(raw: str, entity_type: EntityType) -> str` (canonical); `mask(canonical: str, entity_type: EntityType) -> str`; `identifier_hash(canonical: str) -> str` (SHA-256 hex).
- Produces: CLI `flask init-db` creating all tables.

Steps:
- [ ] Write failing `tests/test_normalize.py` covering: `03001234567`→`03001234567`; `+92 300 1234567` and `00923001234567` → `03001234567`; `@Shop.Pk` and `https://instagram.com/Shop.pk` → `shop.pk`; facebook URL → lowercase host+path without scheme; masks: `03**-***-4567`, `@sh**.pk`; detect_type for digits / `@x` / instagram URL / facebook URL / garbage → None.
- [ ] Implement `normalize.py`; tests green.
- [ ] Write failing `tests/test_models.py`: create user/entity/review/report/file rows; unique (user, entity) raises on second review; review default status pending.
- [ ] Implement `models.py` per spec §3 (SQLite-friendly: integer PKs, `sa.Enum` for enums, `unique_constraint` on `identifier_hash` and `(user_id, entity_id)`).
- [ ] Register CLI `init-db`; test DB creates and persists a row; commit `feat: schema and identifier normalization`.

### Task 3: Auth (register / login / logout / verify / my-activity placeholder)

**Files:**
- Create: `scamguard/auth.py` (blueprint), `scamguard/security.py` (`current_user` helpers), `scamguard/templates/auth/register.html`, `login.html`, `verify_result.html`, `tests/test_auth.py`
- Modify: `__init__.py` (register blueprint, Flask-Login), `base.html` (auth-aware nav)

**Interfaces:**
- Produces: routes `POST/GET /register` (creates user + EmailToken; demo mode shows token + link `/verify?token=...` on the register-success page), `POST/GET /login`, `POST /logout`, `GET /verify?token=` (consumes token, sets `email_verified_at`, flips user's pending reviews+reports to published, flashes success).
- Produces: `login_required` decorator from Flask-Login; `promote_pending_content(user)` helper in `scamguard/services.py`.

Steps:
- [ ] Failing tests (`tests/test_auth.py`): register creates user + token; register page in demo mode displays token; `/verify?token=` marks verified and promotes a pending phone review to published; login sets session; wrong password rejected; logout clears session; `/my-activity` redirects anonymous to `/login`.
- [ ] Implement auth blueprint (Werkzeug `generate_password_hash`/`check_password_hash`, token = `secrets.token_urlsafe(16)`, expiry 24h).
- [ ] Templates with flash errors; nav shows Login/Register or My Activity/Logout.
- [ ] Tests green; commit `feat: auth with demo email verification`.

### Task 4: Search + entity pages

**Files:**
- Create: `scamguard/entities.py` (blueprint + service functions), `scamguard/templates/search_results.html`, `entity.html`, `tests/test_search.py`
- Modify: `index.html` (form action), `base.html` (search box in nav)

**Interfaces:**
- Produces: `find_or_create_entity(raw: str) -> Entity | None` (None if undetectable); `GET /search?q=` renders results or "no record yet" CTA linking to review/report (login-gated); `GET /entity/<int:id>` renders header + published-only reviews/reports sections (tabs via query param `?tab=reviews|reports`, default reviews). Empty entity page shows "Be the first" CTAs.
- Note: entity page pulls `published_reviews` / `published_reports` (Task 5/6 fill lists; for now sections render empty and avg stars = "—" and risk chip = "No data").

Steps:
- [ ] Failing tests: search phone that doesn't exist → "no record" page with CTA; `find_or_create_entity` creates one entity for repeated searches (unique hash); `/entity/<id>` 200 and shows masked identifier, never raw digits/handle; unknown input → friendly error; invalid entity id → 404.
- [ ] Implement blueprint + templates (risk chip placeholder macro `risk_chip(label)`).
- [ ] Green; commit `feat: entity search and public entity page`.

### Task 5: Reviews + proof gate

**Files:**
- Create: `scamguard/reviews.py` (blueprint), `scamguard/uploads.py` (`save_upload(file, uploader) -> File | None` — validate extension png/jpg/pdf ≤5MB), `scamguard/templates/review_form.html`, `scamguard/templates/partials/_reviews.html`, `tests/test_reviews.py`, `scamguard/file_routes.py` (`GET /files/<int:file_id>` — login_required, only uploader may view proof)
- Modify: `entity.html`, `my-activity` route (create `scamguard/activity.py` if not present — `/my-activity` listing user's reviews w/ status chips and reports)

**Interfaces:**
- Produces: `POST/GET /review/<int:entity_id>` form; `submit_review(user, entity, rating, body, proof_upload) -> tuple[Review, str | None]` returning review + error message (None error = success). Gate logic exactly per spec §5:
  - business entity + no proof → `pending`
  - business entity + proof → `published` (status), `proof_file_id` set
  - phone + unverified email → `pending`
  - phone + verified email → `published`
  - duplicate → error `"You already reviewed this entity."`
- Produces: public entity page lists only `published` reviews with stars, body, date, "Verified with proof" badge; avg stars in header = mean of published ratings.

Steps:
- [ ] Failing tests (`tests/test_reviews.py`) — one per gate rule above + proof file saved to disk + duplicate rejected + unverified user can't view others' proofs (403) but uploader can (200) + rating out of range rejected.
- [ ] Implement uploads, review blueprint, file route, `submit_review` in `scamguard/services.py`.
- [ ] Templates: star picker (5 radio buttons styled), conditional proof upload field when entity type != PHONE, status chips on `/my-activity`.
- [ ] Green; commit `feat: reviews with proof-of-payment gate`.

### Task 6: Reports + risk label

**Files:**
- Create: `scamguard/reports.py`, `scamguard/risk.py` (`compute_risk(reviews: list[Review], reports: list[Report]) -> str`), `scamguard/templates/report_form.html`, `scamguard/templates/partials/_reports.html`, `tests/test_reports.py`, `tests/test_risk.py`
- Modify: `entity.html` (header: risk chip via `compute_risk`, counts), `services.py` (`submit_report` with same email-verify gate + duplicate rule)

**Interfaces:**
- Produces: `POST/GET /report/<int:entity_id>`; `submit_report(user, entity, category, description) -> tuple[Report, str | None]`; category validated against `ReportCategory`.
- Produces: `compute_risk` per spec §6 (accepts published reviews/reports; returns one of `High risk|Caution|Looks OK|No data`).

Steps:
- [ ] Failing `tests/test_risk.py`: table-driven cases for all four labels (incl. High risk via 1 report; Caution via avg 3.0; Looks OK avg 4.5 no reports; No data empty).
- [ ] Failing `tests/test_reports.py`: verified user report → published + entity page shows category/description + risk flips to High risk; unverified → pending; duplicate rejected; invalid category rejected.
- [ ] Implement; wire header; green; commit `feat: scam reports and risk labels`.

### Task 7: Polish + seed + README + final gates

**Files:**
- Create: `seed.py` (repo root: creates 2 verified demo users, 1 unverified, 1 phone entity w/ published+pending review, 1 instagram entity w/ proof-badged review + report, 1 facebook entity w/ no content), `README.md`, `tests/test_activity.py`
- Modify: `entity.html`/`search_results.html` empty states, nav, `base.html` footer

Steps:
- [ ] `/my-activity` tests: shows own pending review with "Awaiting proof" chip; own published with badge; own reports listed.
- [ ] Empty states everywhere ("No reviews yet — be the first"); footer with disclaimer ("Student prototype — demo data, no real guarantees").
- [ ] `README.md`: what it is, run steps (venv, pip install, `flask init-db`, `python seed.py`, `python app.py`), test command, demo accounts.
- [ ] Seed script idempotent; run it; manual smoke: register → verify → review phone → appears; business review without proof → hidden; with proof → appears badged.
- [ ] Final gates: `pytest` all green; `python -m compileall scamguard seed.py app.py` clean; commit `feat: seed data, readme, activity page polish`.

## Self-Review

- Spec coverage: search/entities (T4), reviews+gate (T5), reports (T6), risk (T6), auth+verify promote (T3), activity page (T5/T7), seed+README (T7). ✔
- No placeholders: all routes, functions, and gate rules specified. ✔
- Type consistency: `submit_review`/`submit_report` signatures reused across tasks; `compute_risk(list, list) -> str` used by entity template in T6/T7. ✔
