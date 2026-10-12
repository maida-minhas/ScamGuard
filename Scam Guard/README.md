# ScamGuard

ScamGuard is a community-driven scam-checking app: search a phone number, Instagram handle, or Facebook marketplace link to see what other people experienced **before** money changes hands. Users leave 1–5 star reviews and file scam reports, and each entity gets a computed risk label. Business reviews only go public once the author uploads proof of payment, and everything a new account posts stays private until the email is verified.

This is a **student prototype** — demo data only, no real guarantees.

## Features

- **Search** any phone number, Instagram handle, or Facebook link from the nav on every page; unknown identifiers are normalized and the entity page is created on first search.
- **Star reviews (1–5)** on an entity page, with a **proof-of-payment gate**: business reviews need a proof file at submission and only publish once the author's email is verified. Phone reviews publish immediately for verified users.
- **Scam reports** with categories (fake payment request, non-delivery, fake seller, phishing, other) and a **risk label** per entity: `High risk` / `Caution` / `Looks OK` / `No data`.
- **Accounts & verification**: register, log in, and verify email — in demo mode the verification token is shown on screen (no real email is sent). Pending reviews and reports are promoted automatically on verification.
- **My Activity** page listing your own reviews and reports with status chips (`Published`, `Verified with proof`, `Missing proof`, `Awaiting email verification`).
- **Proof files** are private: only the uploader can open `/files/<id>`.

## Run it

Requires Python 3.10+.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
flask --app scamguard init-db     # create tables
python seed.py                    # optional demo data (idempotent, safe to re-run)
python app.py                     # http://localhost:5000
```

If you prefer not to activate the venv, prefix commands with `.venv\Scripts\python` (e.g. `.venv\Scripts\python seed.py`, `.venv\Scripts\python app.py`).

`python seed.py` is optional — without it the database starts empty. Re-running it never duplicates rows.

Debug mode is off by default; set `FLASK_DEBUG=1` to enable it (`$env:FLASK_DEBUG="1"` then `python app.py`).

## Tests

```powershell
.venv\Scripts\python -m pytest -v
```

## Demo accounts

Created by `python seed.py` (password for both: `DemoPass123!`):

| Email                  | Password    | Email verified |
|------------------------|-------------|----------------|
| `demo@scamguard.local` | `DemoPass123!` | Yes |
| `new@scamguard.local`  | `DemoPass123!` | No  |

Seeded content:

- Phone `03001234567` — published 5★ review from `demo@`, plus a pending review from `new@` (shows the *Awaiting email verification* chip on My Activity).
- Instagram `@fashionshop.pk` — published 2★ review from `demo@` **with proof** (*Verified with proof* badge) and a published report, so the entity is labeled **High risk**.
- Facebook `facebook.com/marketplace/item/12345/` — entity exists with no reviews or reports (*No data*).

## Demo verification flow

The app runs in demo mode: no real emails are sent.

1. Register a new account — you are redirected to a success page that **shows your verification token on screen** as a ready-to-click link (`/verify?token=...`).
2. Follow the link (or open `/verify?token=<token>`) — the account is verified and any pending reviews/reports are published immediately.
3. Try it end to end: register → log in → post a review on a phone entity while unverified (stays pending) → verify → the review appears on the entity page.

The seeded `new@scamguard.local` account stays unverified so you can see the pending chips on My Activity; register your own account to watch the verify → publish transition.

## Scope

Student prototype built with Flask, Flask-SQLAlchemy, and Flask-Login. All data is demo data stored in a local SQLite file (`scamguard.db`); uploads live in `uploads/`. There is no real email delivery, no moderation backend, and **no real guarantees** about any entity — treat every risk label as community-sourced demo output.
