# CLAUDE.md
Secret Santa: family gift-exchange app. Flask + SQLAlchemy + MySQL + vanilla JS PWA.
- Follow ARCHITECTURE.md exactly (structure, endpoints, roles).
- Schema of record is schema.sql; models live in app/models.py. Use Flask-Migrate for changes.
- Auth: username -> JWT in httpOnly cookie. Typing a new username creates the account
  (no separate signup step). If the account has a phone on file, sign-in sends an SMS
  OTP (Twilio); otherwise sign-in uses a password. Users set or reset their password
  from Profile & Security (resetting asks for the current password, except for a
  temporary admin-issued one). The phone number is not offered on the profile page.
- Names: only a clan admin can change a name (their own included; members get it
  read-only on their profile). The admin renames people on the Members page.
- Every endpoint must verify the user belongs to the resource's family (see middleware/auth.py helpers).
- Wishlist privacy rule: owners NEVER see purchase status (who/when). Everyone else in
  the family can, and can toggle it — not just the assigned Secret Santa — via My Clan
  (`/events/:id/wishlists/clan`) and the admin all-wishlists view, so the whole clan can
  coordinate gifts beyond the one drawn assignment. Once purchased, an item is locked:
  the owner can no longer edit or delete it (they just lose the delete control — the
  `locked` flag on `WishlistItem.to_dict()` is the only signal that ever reaches them).
- Assignment secrecy: admins see counts only, never who drew whom.
- UI: persistent left sidebar nav (hamburger drawer on mobile), desktop-web density
  throughout (base font ~17px, buttons/inputs ~44px tall, 8px radius) — not oversized
  touch targets. Signed-in pages fill the space beside the sidebar; pre-login pages
  stay centered. One primary action per screen, plain language ("sign-in code" not
  "OTP"). Every page is cards on a very light washed-red background (`--bg`): all
  cards white (`--card`), except a gift that's already been bought, which is very
  light grey (`--card-done`). Never put content directly on the bg or use bare
  `<hr>`-separated sections — wrap it in a card. #C0392B red, #2E7D4F green,
  #F5C518 yellow accents.
- Dashboard (`/`): greeting card with a View My Clan button, then a "My upcoming gift
  exchange" card (what / where / date / time / My Giftee), then announcements. The event
  name and My Giftee link to `/events/:id` (details: date, time, where, theme, gift amount,
  rules, what to bring, other things to know, plus a who's-coming table) and the giftee's
  profile; every attendee row opens that person's profile. The giftee is NOT linked when
  the event uses codenames (the profile would reveal the real name).
- No "← Back" link in the top bar, and no placeholder text in any input (labels only).
- Gift exchanges can be deleted by the clan admin (erases wishlists, draw, messages).
- Profile: photo, about me, likes, favorite color, "what not to give me" live on
  `users` (PATCH /auth/me + /auth/me/photo) and are shown to the clan as an ID-style
  card on `/events/:id/clan/:userId` (photo beside details, wishlist cards below).
  My Clan itself is just a name-sorted grid of photo + name tiles.
- Run pytest before declaring any task done.
- Deploy target: Namecheap cPanel Python app (passenger_wsgi.py entry).
