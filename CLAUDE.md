# CLAUDE.md
Secret Santa: family gift-exchange app. Flask + SQLAlchemy + MySQL + vanilla JS PWA.
- Follow ARCHITECTURE.md exactly (structure, endpoints, roles).
- Schema of record is schema.sql; models live in app/models.py. Use Flask-Migrate for changes.
- Auth: username -> JWT in httpOnly cookie. The password ALWAYS works. If the account has
  a phone (admin-set), the sign-in page also offers "Text Me a Sign-In Code" (Twilio, POST
  /auth/send-code then /auth/verify-otp) with the SMS consent wording beside the button; a code
  is only ever sent when asked for (login-start never texts). Keep the password until text
  delivery (Twilio A2P 10DLC) is confirmed. Public /privacy and /terms are server-rendered
  pages (they carry the SMS terms Twilio reviews); don't turn them back into SPA routes. Users set or reset their password
  from Profile & Security (resetting asks for the current password, except for a
  temporary admin-issued one). The phone number is not offered on the profile page.
- Display name: it is the name the clan sees ("Display Name" in every label), separate from
  the username. Sign-up asks for it (required, must differ from the username), and after that
  only a clan admin can change it (their own included; members see it read-only on their
  profile) - enforced for both `full_name` and `display_name` on PATCH /auth/me. The admin
  renames people on the Members page. A profile shows Username, Display Name and Household
  (ID cards show the household too).
- Every endpoint must verify the user belongs to the resource's family (see middleware/auth.py helpers).
- Wishlist privacy rule: owners NEVER see purchase status (who/when). Everyone else in
  the family can, and can toggle it — not just the assigned Secret Santa — via the event's Clan & Wishlists page
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
  (a phone shows only the message text), ONE "My upcoming event(s)" card holding
  every upcoming event split by lines, then a shortcuts card at the very bottom (Edit My
  Profile, View My Wishlist when they join an event).
  Each event shows what / where / date / time / My Giftee, then My Wishlist + Message My Secret Santa
  side by side (the one place buttons are white with a red border and red
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
- A new event gets different giver -> giftee pairs: `matching_service.solve_distinct`
  bans every pair from the clan's other events (falling back to just the latest event, then
  nothing, for tiny groups) and reports `repeated`. Don't draw with plain `solve`.
- Messages belong to one event: threads come from that event's draw and every
  thread page says which event it is. Notifications are links to what they're about.
- A giftee's profile shows the Secret Santa a Message button with a note that it's anonymous.
- A giftee's wishlist is viewed on their profile (`/events/:id/clan/:userId`, top bar = their
  name); there is no separate "Their Wishlist" page (`/events/:id/giftee` only redirects, for
  old notifications). With codenames on, links go to the reveal page (`/my-person`) instead.
- Admins see an "Admin" card at the bottom of the dashboard (Manage My Clan). Manage My Clan
  (`/admin`) is a stack of centred cards: clan name, then name-only lists of events,
  members and households, each with its Manage... button underneath, then Post Announcement,
  and the registration code card LAST.
- Links (wishlist `link_url`) are validated and stored as absolute http(s) URLs
  (`normalize_link_url`; mirrored by `normalizeUrl` in app.js). Never put a raw
  user-typed URL in an href.
- Photos: real images only (Pillow), 8MB upload cap, gift photos shrunk to 1200px,
  profile photos cropped to a 512px square. Tests must upload real images.
- Add a member and the Members table's edit rows show the same fields (Display Name, Username,
  Phone, Email, Household, Clan admin); an admin can edit a username too (unique, tidied, never
  equal to the display name). Joining is only ever set on the event - the Members table has no
  Joining column.
- Add member / Add household are one-line cards on a desktop (`.inline-form`; stacked on a
  phone) above their tables.
- Admin pages with a list (Members, Households, Announcements): the add/post form card
  comes first at the top, the list below it. Lists that show a household (Manage My Clan >
  Clan Members, Who's coming on the event page) put it in a right-hand column under a
  "Household" header.
- Events are visible only to the people joining them (clan admins see all): a member's event
  list, event page, attendees, dishes, messages, wishlists and profiles-in-event are limited to
  events they're in (`require_event_access` in middleware/auth.py - use it for every new
  event-scoped endpoint). There is no "My Clan" page or link: the people in an event are on that
  event's page / Clan & Wishlists. The sidebar's My Wishlist and My Messages are event-aware
  (`eventChooser` in app.js, routes `/wishlist` and `/messages`): with one upcoming event
  they go straight to it; with several, a bare picker of cards showing only "<Event Name>
  Wishlist" / "<Event Name> Messages" (no giftee/date/theme/buttons - that full-detail layout
  is what the Events page and dashboard use, and is deliberately NOT shown here); with none,
  the "You're not joining any upcoming events..." message. Every event on the dashboard also
  has its own My Wishlist, Message My Secret Santa and View Event Details (a giftee is
  messaged from their profile), and the event page has My Wishlist / View My Messages / View
  Clan & Wishlists. Only the admin's Manage My Clan lists every member.
- Wording: always say "event". Never "gift exchange" (user-facing text, errors, docs).
- There is no separate admin page for a single event. The event page (`/events/:id`) is the
  one place: for clan admins it ends with an Admin card (Draw Names / Start Over (Re-Draw
  Names), Archive Event, View Everyone's Wishlists, Delete Event). Event cards on
  Manage My Clan > Events open it (`/admin/events/:id` just redirects). Who's coming shows a
  household beside each name.
- Any event can be deleted by the clan admin, old or archived, taking everything
  with it (draw, wishlists + photos, messages, dishes, its announcements) - that's how test
  data is cleaned up.
- Archiving (admin "Archive Event", status `completed`) turns an event into a
  view-only record. Everything stays readable (event page, dishes, messages, wishlists,
  profiles, purchase tags) but nothing can change: no messages, wishlist add/edit/delete/
  reorder, buy/unbuy, dishes, event edits, participants or re-draw. This is enforced
  server-side with `archived_error(ev)` (middleware/auth.py); every new write endpoint that
  belongs to an event must call it. The UI hides the controls too. Everyone finds archived
  (and any past) events on the sidebar's "Events" page (`/events`: upcoming on top, past below, one card
  per event laid out like the dashboard; `/past` redirects there). The admin's full list is
  Manage My Clan > Manage Events.
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
  The event's Clan & Wishlists page (`/events/:id/clan`) is a name-sorted grid of photo + name tiles of the people joining THAT event.
- Run pytest before declaring any task done.
- Deploy target: Namecheap cPanel Python app (passenger_wsgi.py entry).
