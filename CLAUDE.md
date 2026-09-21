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
- Dashboard (`/`), top to bottom: plain greeting (not in a card), Announcements card
  (a phone shows only the message text), ONE "My upcoming gift exchange(s)" card holding
  every upcoming event split by lines, then a shortcuts card at the very bottom (Edit My
  Profile, View My Wishlist, View My Clan).
  Each event shows what / where / date / time / My Giftee, then Message My Giftee + Message
  My Secret Santa side by side (the one place buttons are white with a red border and red
  text, `.btn-outline`), then a full-width View Event Details. The event name and
  giftee link to `/events/:id` and the giftee's profile; the giftee is NOT linked when the
  event uses codenames (the profile would reveal the real name).
- Announcements have one visibility switch, "Show on Clan Dashboard" (`is_published`);
  there is no pinning.
- Every button is red with white text (all `.btn-*` variants look the same), except
  `.btn-outline` (the two dashboard message buttons). Cards that
  hold a form use `.form-card` (or render's `card:true` = `.page-card`): on desktop they are
  640px wide, centred, and their fields/buttons fill the card. Don't leave a form floating
  narrow on the left of a wide card.
- A new gift exchange gets different giver -> giftee pairs: `matching_service.solve_distinct`
  bans every pair from the clan's other events (falling back to just the latest event, then
  nothing, for tiny groups) and reports `repeated`. Don't draw with plain `solve`.
- Messages belong to one gift exchange: threads come from that event's draw and every
  thread page says which event it is. Notifications are links to what they're about.
- A giftee's profile shows the Secret Santa a Message button with a note that it's anonymous.
- A giftee's wishlist is viewed on their profile (`/events/:id/clan/:userId`, top bar = their
  name); there is no separate "Their Wishlist" page (`/events/:id/giftee` only redirects, for
  old notifications). With codenames on, links go to the reveal page (`/my-person`) instead.
- Admins see an "Admin" card at the bottom of the dashboard (Manage My Clan). Manage My Clan
  (`/admin`) is a stack of centred cards: clan name, then name-only lists of gift exchanges,
  members and households, each with its Manage... button underneath, then Post Announcement,
  and the registration code card LAST.
- Links (wishlist `link_url`) are validated and stored as absolute http(s) URLs
  (`normalize_link_url`; mirrored by `normalizeUrl` in app.js). Never put a raw
  user-typed URL in an href.
- Photos: real images only (Pillow), 8MB upload cap, gift photos shrunk to 1200px,
  profile photos cropped to a 512px square. Tests must upload real images.
- Any gift exchange can be deleted by the clan admin, old or archived, taking everything
  with it (draw, wishlists + photos, messages, dishes, its announcements) - that's how test
  data is cleaned up.
- Archiving (admin "Archive Gift Exchange", status `completed`) turns an event into a
  view-only record. Everything stays readable (event page, dishes, messages, wishlists,
  profiles, purchase tags) but nothing can change: no messages, wishlist add/edit/delete/
  reorder, buy/unbuy, dishes, event edits, participants or re-draw. This is enforced
  server-side with `archived_error(ev)` (middleware/auth.py); every new write endpoint that
  belongs to an event must call it. The UI hides the controls too. Everyone finds archived
  (and any past) events under "Past Gift Exchanges" (`/past`).
- Wishlist priority is the order of the cards: no priority field anywhere; the owner
  long-presses a card on My Wishlist and drags it (`enableLongPressReorder`, saved with
  PUT /events/:id/wishlists/order). Everyone else sees that order, labelled Priority 1, 2...
  New gifts go to the bottom. "Anything else they should know?" is multiline.
- Event page extras: a Game master row (clan admin picks ONE attendee on the event form;
  editable after the draw) and a "Dishes to bring" card. Dish sign-up opens only once names
  are drawn (status matched) and closes when the event is done; each attendee has ONE entry
  holding up to 10 dishes, which they can edit or remove (PUT/DELETE /events/:id/dishes/mine).
- Profile: photo, about me, likes, favorite color, "what not to give me" live on
  `users` (PATCH /auth/me + /auth/me/photo) and are shown to the clan as an ID-style
  card on `/events/:id/clan/:userId` (photo beside details, wishlist cards below).
  My Clan itself is just a name-sorted grid of photo + name tiles.
- Run pytest before declaring any task done.
- Deploy target: Namecheap cPanel Python app (passenger_wsgi.py entry).
