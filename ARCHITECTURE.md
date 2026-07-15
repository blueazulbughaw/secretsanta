# Secret Santa — Architecture & API Specification

A family gift-exchange platform built for elderly-friendly use, deployable on Namecheap shared hosting, and designed to scale to thousands of families.

---

## 1. Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Flask 3 + Gunicorn (Passenger on cPanel) | Matches your learning path and Namecheap's "Setup Python App" |
| Database | MySQL 8 (utf8mb4) | Included with Namecheap hosting |
| ORM | SQLAlchemy + Flask-Migrate (Alembic) | Schema versioning so production migrations are safe |
| Auth | Username → SMS OTP (Twilio) or password → JWT (httpOnly cookie) | SMS is optional per-user so login doesn't hard-depend on Twilio |
| Frontend | Vanilla JS + CSS (mobile-first) served by Flask templates | No build step on shared hosting; plays to your JS strengths |
| PWA | manifest.json + service worker | Installable, basic offline, push-ready |
| SMS | Twilio | OTP delivery |
| Email (optional, future) | Flask-Mail via Namecheap SMTP (or Resend free tier) | Reserved for non-auth notifications; not used for login |

## 2. Project structure

```
giftcircle/
├── app/
│   ├── __init__.py          # app factory, extensions
│   ├── config.py            # env-driven config
│   ├── models/              # SQLAlchemy models (one file per domain)
│   │   ├── user.py  family.py  event.py  wishlist.py
│   │   ├── message.py  notification.py
│   ├── api/                 # Blueprints (JSON API)
│   │   ├── auth.py  families.py  households.py  events.py
│   │   ├── assignments.py  wishlists.py  messages.py
│   │   ├── announcements.py  notifications.py
│   ├── services/            # business logic, no HTTP concerns
│   │   ├── otp_service.py
│   │   ├── matching_service.py
│   │   ├── notification_service.py
│   │   ├── sms_service.py
│   │   └── mail_service.py
│   ├── utils.py              # phone normalization, etc.
│   ├── middleware/
│   │   ├── auth.py          # @require_auth, @require_family_admin
│   │   └── rate_limit.py
│   ├── templates/           # index.html shell + page partials
│   └── static/
│       ├── css/app.css      # design tokens + components
│       ├── js/              # api.js, router.js, pages/*.js
│       ├── manifest.json
│       └── sw.js            # service worker
├── migrations/              # Alembic
├── tests/                   # pytest
├── .env.example
├── requirements.txt
├── passenger_wsgi.py        # cPanel entry point
└── run.py                   # local dev entry point
```

## 3. Roles & access control

Roles live on `family_members`, not `users` — a person can be admin of one family and member of another.

| Capability | Member | Family Admin |
|---|---|---|
| View own assignment, wishlists, announcements | ✅ | ✅ |
| Add/edit own wishlist items | ✅ | ✅ |
| Send anonymous messages to giver/giftee | ✅ | ✅ |
| Mark giftee's item purchased | ✅ | ✅ |
| Manage members, households, participants | ❌ | ✅ |
| Set event rules, generate assignments | ❌ | ✅ |
| View ALL wishlists, post announcements | ❌ | ✅ |

Enforced with two decorators: `@require_auth` (valid JWT) and `@require_family_admin(family_id)` (checks `family_members.role`). Admins can see all wishlists but **never** the assignment map (who drew whom stays secret even from admins — only "matching complete: 12/12" is shown).

## 4. Authentication flow (username-first, SMS OTP or password)

```
1. POST /api/auth/login-start   { username }
   → unknown username: creates the account right here, issues a JWT
     cookie immediately, user is routed to Security setup (password
     required, phone optional) - no separate signup step
   → existing account with a phone on file: generate a 6-digit code,
     store SHA-256(code + PEPPER), expire 10 min, text it via Twilio
     (rate limit: 3 requests / 15 min per phone) → { method: "otp" }
   → existing account with a password set: → { method: "password" }

2a. POST /api/auth/verify-otp   { username, code }
    → check hash, attempts < 5, not expired, not used → issue JWT cookie
2b. POST /api/auth/login-password { username, password }
    → check password hash → issue JWT cookie

3. PATCH /api/auth/security     { password? , phone? }  (authenticated)
   → set/change password (>= 8 chars) and/or phone (SMS consent required
     in the UI at the moment the phone is added)

4. GET  /api/auth/me             → current user + families + can_create_family
5. POST /api/auth/logout         → clear cookie
```

Twilio's A2P 10DLC registration is an external dependency with no fixed
timeline, so login can't hard-depend on SMS delivery - the password path
above is what keeps accounts (including admins) usable while it's pending.

Elderly-friendly detail: the text message says only "Your verification code is
**482913**" in a short SMS. Each auth screen has one field and one big button.

## 5. API endpoints

All JSON, prefixed `/api`. 🔒 = auth required, 👑 = family admin.

**Auth** — `POST /auth/login-start` (creates the account if the username is new), `POST /auth/verify-otp`, `POST /auth/login-password`, `GET /auth/me` 🔒, `PATCH /auth/me` 🔒, `PATCH /auth/security` 🔒, `POST /auth/logout` 🔒

**Families**
- `POST /families` 🔒 — create family (creator becomes admin)
- `POST /families/join` 🔒 — `{ join_code }`
- `GET /families/:id` 🔒 — details + my role
- `GET /families/:id/members` 🔒
- `PATCH /families/:id/members/:memberId` 👑 — set role / household
- `DELETE /families/:id/members/:memberId` 👑

**Households**
- `GET|POST /families/:id/households` 🔒 / 👑
- `PATCH|DELETE /households/:id` 👑

**Events**
- `POST /families/:id/events` 👑 — name, date, budget, wishlist_limit, use_codenames
- `GET /families/:id/events` 🔒
- `GET|PATCH /events/:id` 🔒 / 👑
- `PUT /events/:id/participants` 👑 — `{ user_ids: [...] }` (the checkbox screen)
- `POST /events/:id/participants/:userId/opt-out` 🔒 — self only, before matching

**Assignments**
- `POST /events/:id/assignments/generate` 👑 — runs validation + matcher (see §6)
- `GET /events/:id/assignments/mine` 🔒 — my giftee (name or codename) + their wishlist
- `DELETE /events/:id/assignments` 👑 — only while status ≠ completed; re-roll

**Wishlists**
- `GET /events/:id/wishlists/mine` 🔒
- `POST /events/:id/wishlists` 🔒 — enforces `wishlist_limit`
- `PATCH|DELETE /wishlists/:itemId` 🔒 — owner only
- `GET /events/:id/wishlists/giftee` 🔒 — giver's view (purchase status visible)
- `POST /wishlists/:itemId/purchase` 🔒 — giver marks purchased; owner never sees this
- `GET /events/:id/wishlists` 👑 — all wishlists (admin view)

**Messages**
- `GET /events/:id/messages` 🔒 — my two threads (with my giver, with my giftee)
- `POST /events/:id/messages` 🔒 — `{ to: "giver"|"giftee", body }`
  Server resolves recipient from assignments; sender shown as "Your Secret Santa" or codename.

**Announcements** — `GET /families/:id/announcements` 🔒, `POST` 👑, `DELETE /announcements/:id` 👑

**Notifications** — `GET /notifications` 🔒, `POST /notifications/:id/read` 🔒, `POST /notifications/read-all` 🔒, `POST /push/subscribe` 🔒 (stores subscription; push delivery is a later phase)

## 6. Matching algorithm

**Validation gate (runs first, returns human-readable errors):**
1. Event status must be `open`.
2. Every checked participant must belong to a household → else: "Assign ___ to a household first."
3. Every participant must have `is_participating = 1`.
4. Minimum 3 participants (2-person "secret" santa isn't secret).
5. If `allow_same_household = 0`: no household may contain more than ⌊n/2⌋ participants, otherwise a valid matching is mathematically impossible → tell the admin exactly that.

**Matcher — randomized block-shift (guaranteed, O(n)):**

Shuffle members within each household, place the largest household's block
first, shuffle the remaining household blocks, lay everyone out in one line,
and have each person give to the person `m` seats ahead (wrapping around),
where `m` = size of the largest household.

This is always valid whenever `max household <= n/2` (which the validation
gate enforces): the shift is at least 1 (no self-match), every block is at
most `m` long so shifting by `m` always exits your own block, and the
wraparound lands inside the first (largest) block, which tail positions can
never belong to. Unlike backtracking, there are no pathological slow cases —
1,000 randomized 50-person draws complete in under 2 seconds in the test
suite. See `app/services/matching_service.py::solve` for the implementation
and proof sketch.

**Persistence & integrity:** insert all rows in one transaction. The DB itself enforces no-duplicates via `UNIQUE(event_id, giver_id)` and `UNIQUE(event_id, receiver_id)`, and no self-match via a CHECK constraint — so even a bug or a double-click can't corrupt the exchange. On success: set event `status='matched'`, generate codenames if enabled, and fan out an `assignment` notification to every participant.

**Scale note:** matching is per-event, so n is family-sized (5–200). Backtracking is instant at that scale even with thousands of families on the platform, because families never interact in the matcher.

## 7. Frontend structure (elderly-friendly)

Design tokens in `app.css`:

```css
:root {
  --bg: #FFFFFF;  --ink: #1A1A1A;
  --red: #C0392B;          /* primary actions */
  --green: #2E7D4F;        /* success, "purchased" */
  --yellow: #F5C518;       /* highlights, announcements */
  --touch-min: 64px;       /* every tappable target ≥ 64px tall */
  --font-body: 20px;       /* base font 20px, headings 28–36px */
  --radius: 16px;
}
```

Non-negotiable UX rules baked into every component:
- One primary action per screen, full-width red button, verb-first label: "See My Person", "Add a Gift Idea", "Send Message".
- Max ~8 words of instruction per screen. No jargon anywhere — "Sign in code" not "OTP", "Your person" not "assignee".
- Guided steps: wizard pattern (1 of 3 → 2 of 3) for anything multi-step, with a persistent "Go Back" button.
- WCAG AA contrast, focus outlines, `aria-live` for confirmations, works at 200% browser zoom.
- Sign in with a username, then either a texted 6-digit code (if a phone is on file) or a password.

Pages: Login (2 steps) → persistent left sidebar nav + content pane. The sidebar (My Person / My Wishlist / My Person's Wishlist / Messages / Announcements / Profile & Security / Sign Out) stays mounted across every page — clicking a link swaps only the content pane, not the whole screen — and collapses behind a hamburger into a slide-out overlay drawer below ~780px width. Admins additionally get "Manage Family", a WordPress-style expandable submenu (Members, Family Groups, Gift Exchanges, Post Announcement) leading to the admin content: members, households, events, participants checklist, rules form, big "Draw Names" button, all-wishlists view, post-announcement form. The sidebar itself intentionally uses a denser WordPress-admin scale (small text, tight padding) — the non-negotiable big-touch-target rules above still apply to all page *content* (forms, buttons, tables), just not to sidebar nav links.

## 8. PWA

- `manifest.json`: name, icons (192/512), `display: standalone`, theme color `#C0392B`.
- `sw.js`: cache-first for static assets, network-first for `/api/*`, offline fallback page ("You're offline — your wishlist will load when you reconnect").
- Push-ready: `push_subscriptions` table + `/api/push/subscribe` endpoint exist from day one; actually sending Web Push (pywebpush + VAPID keys) is a Phase-2 flip-of-a-switch, no schema change needed.

## 9. Security checklist

- OTP codes hashed (SHA-256 + server pepper), 10-min expiry, 5 attempts, rate-limited requests.
- JWT in httpOnly + Secure + SameSite=Lax cookie (not localStorage) → immune to XSS token theft.
- All queries via SQLAlchemy (parameterized) → no SQL injection.
- Jinja auto-escaping + never `innerHTML` untrusted content → XSS protection for wishlist/message text.
- Authorization on every endpoint: verify the user belongs to the family that owns the resource (multi-tenant isolation) — this is the #1 bug class in family apps.
- HTTPS enforced (free AutoSSL on Namecheap), HSTS header.
- `.env` never committed; secrets set in cPanel's Python app environment variables.
