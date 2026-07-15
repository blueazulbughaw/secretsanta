# CLAUDE.md
Secret Santa: family gift-exchange app. Flask + SQLAlchemy + MySQL + vanilla JS PWA.
- Follow ARCHITECTURE.md exactly (structure, endpoints, roles).
- Schema of record is schema.sql; models live in app/models.py. Use Flask-Migrate for changes.
- Auth: username -> JWT in httpOnly cookie. Typing a new username creates the account
  (no separate signup step). If the account has a phone on file, sign-in sends an SMS
  OTP (Twilio); otherwise sign-in uses a password. Users set up a password and/or phone
  from Security settings after their first login.
- Every endpoint must verify the user belongs to the resource's family (see middleware/auth.py helpers).
- Wishlist privacy rule: owners NEVER see purchase status; givers do.
- Assignment secrecy: admins see counts only, never who drew whom.
- UI: persistent left sidebar nav (hamburger drawer on mobile), desktop-web density
  throughout (base font ~15px, buttons/inputs ~40px tall, 8px radius) — not oversized
  touch targets. One primary action per screen, plain language ("sign-in code" not
  "OTP"). White bg, #C0392B red, #2E7D4F green, #F5C518 yellow accents.
- Run pytest before declaring any task done.
- Deploy target: Namecheap cPanel Python app (passenger_wsgi.py entry).
