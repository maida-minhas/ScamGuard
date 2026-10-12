# ScamGuard — Design Spec

Date: 2026-10-11
Status: Approved
Scope: Student-level web prototype (no mobile app, no AI/OCR, no moderation queue)

## 1. Product idea

ScamGuard is a community site where people look up a **phone number**, **Instagram
shop/page**, or **Facebook Marketplace listing/seller** before they pay or answer a
call. Anyone can search and see what other users said. Two kinds of user
contributions exist, kept separate:

- **Star reviews** — a 1–5 rating plus written experience.
- **Scam reports** — a category + description flagging a number/page as a scam.

The core trust problem: reviews must be genuine. For **business** entities
(Instagram shops, Facebook Marketplace sellers) a review only becomes public after
the author uploads **proof of payment/order** (screenshot or receipt). Phone
numbers are not businesses, so their reviews publish after email verification only.

## 2. Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.14 |
| Web framework | Flask 3 (app factory) |
| Templates | Jinja2, Tailwind CSS via CDN |
| ORM / DB | SQLAlchemy 2 (Flask-SQLAlchemy) + SQLite (`scamguard.db`) |
| Auth | Flask-Login sessions; password hashing via Werkzeug |
| Uploads | Local `uploads/` directory, served through an authenticated route |
| Validation | Plain-Python validation helpers + form checks |
| Tests | pytest |

Run: `python app.py` → http://localhost:5000 (plus `flask init-db` / seed script).

## 3. Data model

- **User** — id, email (unique), password_hash, email_verified_at (nullable), created_at.
- **EmailToken** — id, user_id, token (unique), purpose (`verify_email`), expires_at, used_at.
  Demo mode: the token is shown on-screen after registration (no SMTP).
- **Entity** — id, type (`PHONE | INSTAGRAM | FACEBOOK`), identifier_hash (unique;
  hash of the normalized value), display_masked (e.g. `03**-***-7890`, `@sh****op`),
  created_at.
- **Review** — id, entity_id, user_id, rating (1–5), body, status
  (`pending | published | hidden`), proof_file_id (nullable), created_at.
  Unique (user_id, entity_id).
- **Report** — id, entity_id, user_id, category
  (`FAKE_PAYMENT_REQUEST | NON_DELIVERY | FAKE_SELLER | PHISHING | OTHER`),
  description, status (`pending | published | hidden`), created_at. Unique (user_id, entity_id).
- **File** — id, uploader_id, stored_name, original_name, mime_type, size, created_at.

## 4. Normalization (search input → entity)

- **Phone**: keep digits only; treat `+92`/`0092` prefix as equivalent to local `0`;
  canonical form is digits starting with `0`. Masked display: `03**-***-7890`.
- **Instagram**: accept `@handle` or any `instagram.com/<handle>` URL; canonical
  value is lowercase handle. Masked display: `@sh****op` (keep first 2 / last 2).
- **Facebook**: accept marketplace listing or profile URLs containing
  `facebook.com`; canonical value is scheme-less host+path lowercase, with
  `www.` prefix stripped, and the `id` query parameter retained when the path
  is `profile.php` (so distinct profiles don't collide). Masked
  display: first 20 chars + `…`.
- Type detection from input: digits → PHONE; contains `instagram.com` or starts
  with `@` → INSTAGRAM; contains `facebook.com` → FACEBOOK; anything else →
  error message asking to pick/fix the input.

## 5. Gates (the trust rules)

1. **Email verification** (demo mode, on-screen token):
   - Registering creates an account with `email_verified_at = None`.
   - A **phone** review is stored with status `pending` until the author's email
     is verified; verification flips their pending reviews to `published`.
   - Verification promotes a pending **business** review only if it already has
     a proof file (a business review without proof is never promoted).
   - Verification also promotes the user's pending **reports** to published.
2. **Proof-of-payment gate (business entities only — INSTAGRAM, FACEBOOK):**
   - A review without an uploaded proof file → status `pending` (never public).
   - A review with a proof file → status `published` + "Verified with proof" badge.
3. **Scam reports** publish immediately for verified emails (same email-verify
   gate as phone reviews: unverified → pending until verify).
4. **One review and one report per user per entity** (enforced by unique
   constraints; friendly error message on attempt).

## 6. Risk label (entity page header)

Computed from published content only:

- **High risk** — average rating ≤ 2 with ≥ 2 published reviews, OR ≥ 1 scam report.
- **Caution** — average rating < 3.5, or fewer than 2 published reviews with any rating ≤ 2.
- **Looks OK** — average rating ≥ 3.5 with no reports.
- **No data** — no published reviews and no reports.

## 7. Pages

| Route | Purpose |
|---|---|
| `/` | Landing: big search box, short explainer, site stats |
| `/search?q=` | Result: masked identity, type, avg stars, risk chip, or "not found" CTA |
| `/entity/<id>` | Header (masked identity, risk chip, avg stars, counts), tabs: Reviews / Reports |
| `/register`, `/login`, `/verify?token=` | Auth; verify consumes token and shows success |
| `/review/<entity_id>` | Star picker + text + (business only) proof upload field |
| `/report/<entity_id>` | Category select + description |
| `/my-activity` | My reviews (status chips: awaiting proof / awaiting email verify) and my reports |

## 8. Explicitly out of scope

AI/OCR on proof files, moderator dashboard, disputes, trust scores, SMTP email,
rate limiting beyond the uniqueness rules, Docker, deployment, mobile app.

## 9. Success criteria

- A visitor can search a phone/Instagram/Facebook input and see an entity page.
- A business review without proof is not visible publicly; with proof it is,
  badged "Verified with proof".
- Phone review from an unverified email stays private until verification.
- Duplicate review/report attempts are rejected with a clear message.
- `pytest` suite covers normalization, gates, and risk label; app runs with
  `python app.py` and a seed script provides demo accounts and sample data.
