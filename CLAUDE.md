# CLAUDE.md
Secret Santa: family gift-exchange app. Flask + SQLAlchemy + MySQL + vanilla JS PWA.
- Follow ARCHITECTURE.md exactly (structure, endpoints, roles).
- Schema of record is schema.sql; models live in app/models.py. Use Flask-Migrate for changes.
- Auth: username -> JWT in httpOnly cookie. If the account has a phone on file, sign-in
  sends an SMS OTP (Twilio); otherwise sign-in uses a password. Users set up a password
  and/or phone from Security settings after their first login. A hidden password-only
  route at /ss-admin (env var ADMIN_BACKDOOR_PASSWORD) logs in as/creates an is_app_admin
  user, bypassing SMS entirely.
- Every endpoint must verify the user belongs to the resource's family (see middleware/auth.py helpers).
- Wishlist privacy rule: owners NEVER see purchase status; givers do.
- Assignment secrecy: admins see counts only, never who drew whom.
- UI: base font 20px, buttons >=64px tall, one primary action per screen,
  plain language ("sign-in code" not "OTP"). White bg, #C0392B red,
  #2E7D4F green, #F5C518 yellow accents.
- Run pytest before declaring any task done.
- Deploy target: Namecheap cPanel Python app (passenger_wsgi.py entry).
