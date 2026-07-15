# CLAUDE.md
Secret Santa: family gift-exchange app. Flask + SQLAlchemy + MySQL + vanilla JS PWA.
- Follow ARCHITECTURE.md exactly (structure, endpoints, roles).
- Schema of record is schema.sql; models live in app/models.py. Use Flask-Migrate for changes.
- Auth: username -> JWT in httpOnly cookie. Typing a new username creates the account
  (no separate signup step). If the account has a phone on file, sign-in sends an SMS
  OTP (Twilio); otherwise sign-in uses a password. Users set up a password and/or phone
  from Security settings after their first login.
- Every endpoint must verify the user belongs to the resource's family (see middleware/auth.py helpers).
- Wishlist privacy rule: owners NEVER see purchase status. Everyone else in the family
  can — not just the assigned Secret Santa — via My Clan (`/events/:id/wishlists/clan`),
  so the whole clan can coordinate gifts beyond the one drawn assignment.
- Assignment secrecy: admins see counts only, never who drew whom.
- UI: persistent left sidebar nav (hamburger drawer on mobile), desktop-web density
  throughout (base font ~17px, buttons/inputs ~44px tall, 8px radius) — not oversized
  touch targets. Signed-in pages fill the space beside the sidebar; pre-login pages
  stay centered. One primary action per screen, plain language ("sign-in code" not
  "OTP"). White bg, #C0392B red, #2E7D4F green, #F5C518 yellow accents.
- Run pytest before declaring any task done.
- Deploy target: Namecheap cPanel Python app (passenger_wsgi.py entry).
