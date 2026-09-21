/* Secret Santa SPA — hash router + pages. No frameworks, no build step. */

const $app = document.getElementById("app");
const $title = document.getElementById("pageTitle");
const $topbar = document.getElementById("topbar");
const $bell = document.getElementById("bellBtn");
const $badge = document.getElementById("bellBadge");
const $sidebar = document.getElementById("sidebar");
const $sidebarOverlay = document.getElementById("sidebarOverlay");
const $menuBtn = document.getElementById("menuBtn");
const $shell = document.getElementById("shell");
const $lightbox = document.getElementById("lightbox");
const $lightboxImg = document.getElementById("lightboxImg");
const $lightboxClose = document.getElementById("lightboxClose");

let ME = null;          // { user, families }
let FAMILY = null;      // active family {id, name, role}
let CURRENT_EVENT = null; // the family's active (non completed/cancelled) event, or null
let PENDING_JOIN_CODE = null;
let IS_REGISTER_ENTRY = false;

(function captureEntryIntent() {
  // Support both hash-based (#/join/CODE, #/register) and plain-path
  // (/join/CODE, /register) URLs, since people type or paste either form -
  // the server serves the same SPA shell for any path either way.
  const hashPath = location.hash.replace(/^#/, "");
  const plainPath = location.pathname.replace(/\/+$/, "") || "/";

  const hashJoin = hashPath.match(/^\/join\/([A-Za-z0-9]+)$/i);
  const plainJoin = plainPath.match(/^\/join\/([A-Za-z0-9]+)$/i);
  const joinMatch = hashJoin || plainJoin;
  if (joinMatch) {
    PENDING_JOIN_CODE = joinMatch[1].toUpperCase();
    if (hashJoin) history.replaceState(null, "", location.pathname + location.search);
  }
  if (hashPath === "/register" || plainPath === "/register") {
    IS_REGISTER_ENTRY = true;
  }
})();

// ---------- helpers ----------
function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}
// Turns what someone typed into a full http(s) link ("amazon.com/x" becomes
// "https://amazon.com/x"). Returns "" for nothing, or null when it isn't a valid
// web link. Mirrors normalize_link_url on the server.
function normalizeUrl(raw) {
  let url = (raw || "").trim();
  if (!url) return "";
  if (url.length > 500 || /\s/.test(url)) return null;
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(url)) {
    if (/^[a-z][a-z0-9+.-]*:(?!\d)/i.test(url)) return null;   // mailto:, javascript: ...
    url = "https://" + url.replace(/^\/+/, "");
  }
  let u;
  try { u = new URL(url); } catch (_) { return null; }
  if (!/^https?:$/.test(u.protocol) || !/^([a-z0-9-]+\.)+[a-z]{2,}$/i.test(u.hostname)) return null;
  return url;
}
const LINK_HELP = "Please enter a valid web link, like https://www.example.com/item";

const MAX_PHOTO_MB = 8;
function photoTooBig(file) { return !!file && file.size > MAX_PHOTO_MB * 1024 * 1024; }
const PHOTO_TOO_BIG = `Photos must be smaller than ${MAX_PHOTO_MB}MB.`;

// An archived (completed) gift exchange can still be looked at, but nothing in it can change.
const ARCHIVED_NOTE = "📦 This gift exchange is archived, so everything here is view-only.";
const archivedBanner = () => alertBox(ARCHIVED_NOTE, true);

function h(html) { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content; }
// card: put the whole page in one white card (forms, threads); pages made of
// several sections build their own cards instead.
function render(title, html, { wide = false, card = false } = {}) {
  $title.textContent = title;
  $app.classList.toggle("wide", wide);
  $app.innerHTML = "";
  if (card && typeof html === "string") html = `<div class="card page-card">${html}</div>`;
  $app.append(typeof html === "string" ? h(html) : html);
  window.scrollTo(0, 0);
}

const NAV = [
  { key: "dashboard", label: "My Dashboard", href: "/" },
  { key: "wishlist", label: "My Wishlist", eventPath: "wishlist" },
  { key: "clan", label: "My Clan", eventPath: "clan" },
  { key: "messages", label: "My Messages", eventPath: "messages/giver", children: [
    { key: "messages-giver", eventPath: "messages/giver", label: "Message to my Secret Santa" },
    { key: "messages-giftee", eventPath: "messages/giftee", label: "Message to my Giftee" },
  ] },
  { key: "past", label: "Past Gift Exchanges", href: "/past" },
  { key: "admin", label: "Manage My Clan", href: "/admin", adminOnly: true, children: [
    { key: "members", href: "/admin/members", label: "Members" },
    { key: "groups", href: "/admin/groups", label: "Households" },
    { key: "events", href: "/admin/events", label: "Gift Exchanges" },
    { key: "announce", href: "/admin/announce", label: "Post Announcement" },
  ] },
  { key: "security", label: "Profile & Security", href: "/security" },
];

async function refreshCurrentEvent() {
  const events = await api.get(`/families/${FAMILY.id}/events`);
  CURRENT_EVENT = events.find(e => e.status !== "completed" && e.status !== "cancelled") || null;
}

function navHref(item) {
  return item.eventPath ? (CURRENT_EVENT ? `/events/${CURRENT_EVENT.id}/${item.eventPath}` : null) : item.href;
}
function navChildHtml(item, activePath) {
  const href = navHref(item);
  if (!href) return `<span class="nav-link nav-child nav-disabled">${esc(item.label)}</span>`;
  return `<a href="#${href}" class="nav-link nav-child ${activePath === href ? "active" : ""}">${esc(item.label)}</a>`;
}
function navItemHtml(item, activePath) {
  const href = navHref(item);
  if (item.children) {
    if (!href) return `<span class="nav-link nav-disabled">${esc(item.label)}</span>`;
    const childHrefs = item.children.map(navHref);
    const isActive = activePath === href || childHrefs.some(h => h && activePath === h);
    const kids = item.children.map(c => navChildHtml(c, activePath)).join("");
    return `
      <div class="nav-group ${isActive ? "expanded" : ""}">
        <a href="#${href}" class="nav-link nav-parent ${isActive ? "active" : ""}">
          <span>${esc(item.label)}</span><span class="nav-caret">${isActive ? "▾" : "▸"}</span>
        </a>
        <div class="nav-children">${kids}</div>
      </div>`;
  }
  if (!href) return `<span class="nav-link nav-disabled">${esc(item.label)}</span>`;
  return `<a href="#${href}" class="nav-link ${activePath === href ? "active" : ""}">${esc(item.label)}</a>`;
}
function renderSidebar(activePath) {
  if (!FAMILY) return;
  const items = NAV.filter(i => !i.adminOnly || FAMILY.role === "admin")
    .map(i => navItemHtml(i, activePath)).join("");
  $sidebar.innerHTML = `
    <div class="sidebar-brand">${esc(FAMILY.name)}</div>
    <div class="nav-scroll">${items}</div>
    <a href="#" id="logoutLink" class="nav-link nav-logout">Sign Out</a>
  `;
  document.getElementById("logoutLink").onclick = async (e) => {
    e.preventDefault();
    await api.post("/auth/logout");
    location.reload();
  };
  $sidebar.querySelectorAll("a.nav-link").forEach(a => a.addEventListener("click", closeSidebar));
}
// Two modes, one menu button: on phones the sidebar is an off-canvas drawer
// (open/close); on desktop it collapses so the content fills the whole page,
// and that choice is remembered.
const MOBILE_MQ = window.matchMedia("(max-width: 780px)");
function syncMenuBtn() {
  const expanded = MOBILE_MQ.matches
    ? $sidebar.classList.contains("open")
    : !$shell.classList.contains("sidebar-collapsed");
  $menuBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
}
function openSidebar() {
  $sidebar.classList.add("open"); $sidebarOverlay.classList.add("open");
  document.body.classList.add("drawer-open"); syncMenuBtn();
}
function closeSidebar() {
  $sidebar.classList.remove("open"); $sidebarOverlay.classList.remove("open");
  document.body.classList.remove("drawer-open"); syncMenuBtn();
}
function setSidebarCollapsed(collapsed) {
  $shell.classList.toggle("sidebar-collapsed", collapsed);
  try { localStorage.setItem("sidebarCollapsed", collapsed ? "1" : "0"); } catch (_) {}
  syncMenuBtn();
}
function toggleSidebar() {
  if (MOBILE_MQ.matches) $sidebar.classList.contains("open") ? closeSidebar() : openSidebar();
  else setSidebarCollapsed(!$shell.classList.contains("sidebar-collapsed"));
}
function restoreSidebarState() {
  let collapsed = false;
  try { collapsed = localStorage.getItem("sidebarCollapsed") === "1"; } catch (_) {}
  $shell.classList.toggle("sidebar-collapsed", collapsed);
  syncMenuBtn();
}
MOBILE_MQ.addEventListener("change", closeSidebar);

function openLightbox(url) { $lightboxImg.src = url; $lightbox.hidden = false; }
function closeLightbox() { $lightbox.hidden = true; $lightboxImg.src = ""; }
document.addEventListener("click", (e) => {
  const trigger = e.target.closest("[data-photo]");
  if (trigger) { openLightbox(trigger.dataset.photo); return; }
  if (e.target === $lightbox) closeLightbox();
});
$lightboxClose.onclick = closeLightbox;
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeLightbox(); });
function alertBox(msg, ok = false) {
  return `<div class="alert ${ok ? "alert-ok" : "alert-error"}" role="alert">${esc(msg)}</div>`;
}
function showError(e) {
  const el = document.getElementById("msg");
  if (el) el.innerHTML = alertBox(e.message);
  else window.alert(e.message);
}
function go(hash) { location.hash = hash; }

function wishThumbCell(item) {
  return item.photo_url
    ? `<button type="button" class="wish-thumb-btn" data-photo="${esc(item.photo_url)}" aria-label="View photo of ${esc(item.item_name)} full size">
         <img src="${esc(item.photo_url)}" alt="" class="wish-thumb"></button>`
    : `<div class="wish-thumb wish-thumb-empty">🎁</div>`;
}

// Profile photo, or the person's initials on their colour when they have none.
function safeColor(c) { return /^#[0-9a-fA-F]{6}$/.test(c || "") ? c : "#C0392B"; }
function initialsOf(name) {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}
function avatarHtml(user, cls) {
  return user.photo_url
    ? `<img class="avatar ${cls}" src="${esc(user.photo_url)}" alt="">`
    : `<span class="avatar avatar-initials ${cls}" style="background:${safeColor(user.avatar_color)}" aria-hidden="true">${esc(initialsOf(user.display_name || user.full_name))}</span>`;
}

// Shared top of every wishlist card: small photo (if any), name, priority,
// description, and the link last. A gift's priority is its place in the list
// (`rank`, 1 = wanted most), which its owner sets by dragging.
function wishCardBody(item, rank) {
  return `
    <div class="wish-card-head">
      ${item.photo_url ? wishThumbCell(item) : ""}
      <div class="wish-card-title">
        <strong>${esc(item.item_name)}</strong>
        <span class="wish-priority">Priority ${rank}</span>
      </div>
    </div>
    ${item.description ? `<p class="wish-card-desc">${esc(item.description)}</p>` : ""}
    ${normalizeUrl(item.link_url) ? `<a class="wish-link" href="${esc(normalizeUrl(item.link_url))}" target="_blank" rel="noopener">See it online ↗</a>` : ""}`;
}

// A gift as seen by someone other than its owner: the card, plus whether it's
// been bought. Owners never get is_purchased for their own items, so their own
// card just has no purchase footer. Bought cards go light grey (.bought).
function clanWishCard(item, index, readOnly = false) {
  let footer = "";
  if (item.is_purchased === undefined) footer = "";
  else if (readOnly) footer = item.is_purchased
    ? `<span class="tag-bought">${item.bought_by_me ? "✓ Bought by you" : "✓ Already bought"}</span>` : "";
  else if (!item.is_purchased) footer = `<button class="btn btn-green" data-buy="${item.id}">I Bought This</button>`;
  else if (item.bought_by_me) footer = `<span class="tag-bought">✓ Bought by you</span><button class="btn btn-quiet" data-buy="${item.id}">Unbought</button>`;
  else footer = `<span class="tag-bought">✓ Already bought</span>`;
  return `<article class="wish-card ${item.is_purchased ? "bought" : ""}">
    ${wishCardBody(item, index + 1)}
    ${footer ? `<div class="wish-card-actions">${footer}</div>` : ""}
  </article>`;
}
function clanWishGrid(items, readOnly = false) {
  return `<div class="wish-grid">${items.map((item, n) => clanWishCard(item, n, readOnly)).join("")}</div>`;
}
// Wires the "I Bought This" / "Unbought" buttons anywhere on the page.
function wireBuyButtons() {
  $app.querySelectorAll("[data-buy]").forEach(b => b.onclick = async () => {
    try { await api.post(`/wishlists/${b.dataset.buy}/purchase`); navigate(); }
    catch (e) { showError(e); }
  });
}

// My Wishlist card (own items): small photo, name/priority, description, link
// last, then Edit/Delete at the bottom - or a plain sentence once the item is
// locked (someone bought it). The locked flag is all the owner ever learns.
function myWishCard(item, eventId, rank, readOnly = false) {
  const footer = readOnly ? ""
    : item.locked
    ? `<span class="muted wish-locked-msg">Cannot edit this item as it has already been bought.</span>`
    : `<button class="btn btn-secondary" data-edit>Edit</button>
       <button class="btn btn-quiet" data-del>Delete</button>`;
  const card = h(`<article class="wish-card" data-id="${item.id}">
    ${wishCardBody(item, rank)}
    ${footer ? `<div class="wish-card-actions">${footer}</div>` : ""}
  </article>`).firstElementChild;
  if (!readOnly && !item.locked) {
    card.querySelector("[data-edit]").onclick = () => go(`/events/${eventId}/wishlist/${item.id}/edit`);
    card.querySelector("[data-del]").onclick = async () => {
      if (!confirm("Remove this gift from your list?")) return;
      try { await api.del(`/wishlists/${item.id}`); navigate(); }
      catch (e) { showError(e); }
    };
  }
  return card;
}

// Long-press a card (mouse or finger), then drag it to a new place; `onDrop` gets
// the cards' data-id values in their new order. A quick tap or a scroll never
// starts a drag, and the Edit / Delete buttons and links keep working.
function enableLongPressReorder(grid, onDrop) {
  const HOLD_MS = 350, MOVE_TOLERANCE = 8, EDGE = 70;
  let timer = null, dragging = null, ghost = null, start = null, offset = null, pointerId = null;
  let initialOrder = "", swallowClick = false;
  const cards = () => [...grid.querySelectorAll(":scope > .wish-card")];
  const order = () => cards().map(c => c.dataset.id);

  function beginDrag(card) {
    const r = card.getBoundingClientRect();
    dragging = card;
    offset = { x: start.x - r.left, y: start.y - r.top };
    initialOrder = order().join(",");
    ghost = card.cloneNode(true);
    ghost.classList.add("drag-ghost");
    ghost.style.width = r.width + "px";
    ghost.style.height = r.height + "px";
    document.body.append(ghost);
    card.classList.add("drag-placeholder");
    document.body.classList.add("dragging-cards");
    moveGhost(start.x, start.y);
    if (navigator.vibrate) navigator.vibrate(15);
  }
  function moveGhost(x, y) {
    ghost.style.left = (x - offset.x) + "px";
    ghost.style.top = (y - offset.y) + "px";
  }
  function onMove(e) {
    if (e.pointerId !== pointerId) return;
    if (!dragging) {   // moved before the hold finished: that's a scroll or a swipe, not a drag
      if (Math.hypot(e.clientX - start.x, e.clientY - start.y) > MOVE_TOLERANCE) stop();
      return;
    }
    e.preventDefault();
    moveGhost(e.clientX, e.clientY);
    const over = document.elementFromPoint(e.clientX, e.clientY)?.closest(".wish-card");
    if (over && over !== dragging && over.parentElement === grid) {
      const all = cards();
      if (all.indexOf(dragging) < all.indexOf(over)) over.after(dragging); else over.before(dragging);
    }
    if (e.clientY < EDGE) window.scrollBy(0, -14);
    else if (e.clientY > window.innerHeight - EDGE) window.scrollBy(0, 14);
  }
  function stop() {
    clearTimeout(timer); timer = null;
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onUp);
    if (dragging) {
      dragging.classList.remove("drag-placeholder");
      ghost.remove();
      document.body.classList.remove("dragging-cards");
      dragging = ghost = null;
      swallowClick = true;   // the release can look like a click on a button underneath
      setTimeout(() => { swallowClick = false; }, 0);
    }
  }
  function onUp(e) {
    if (e.pointerId !== pointerId) return;
    const moved = dragging && order().join(",") !== initialOrder;
    stop();
    if (moved) onDrop(order());
  }

  grid.classList.add("reorderable");
  grid.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    const card = e.target.closest(".wish-card");
    if (!card || card.parentElement !== grid || e.target.closest(".wish-card-actions, a")) return;
    pointerId = e.pointerId;
    start = { x: e.clientX, y: e.clientY };
    window.addEventListener("pointermove", onMove, { passive: false });
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    timer = setTimeout(() => { timer = null; beginDrag(card); }, HOLD_MS);
  });
  // Once a drag is on, stop the page from scrolling under the finger; no menu / image drag.
  grid.addEventListener("touchmove", (e) => { if (dragging) e.preventDefault(); }, { passive: false });
  grid.addEventListener("contextmenu", (e) => { if (timer || dragging) e.preventDefault(); });
  grid.addEventListener("dragstart", (e) => e.preventDefault());
  grid.addEventListener("click", (e) => { if (swallowClick) { e.stopPropagation(); e.preventDefault(); } }, true);
}

function annRowReadOnly(a) {
  const del = FAMILY.role === "admin"
    ? `<button class="icon-btn" aria-label="Delete announcement" data-del-ann="${a.id}">🗑</button>` : "";
  return `
    <tr>
      <td data-label="Title"><strong>${esc(a.title)}</strong></td>
      <td data-label="Message" class="wrap-cell">${esc(a.body)}</td>
      <td data-label="From">${esc(a.author)}</td>
      <td data-label="Date">${new Date(a.at).toLocaleDateString()}</td>
      <td data-label="" class="table-actions">${del}</td>
    </tr>`;
}
function annTable(anns) {
  return `
    <div class="table-wrap">
      <table class="data ann-table">
        <colgroup>
          <col style="width:18%"><col style="width:42%">
          <col style="width:15%"><col style="width:15%"><col style="width:10%">
        </colgroup>
        <thead><tr><th>Title</th><th>Message</th><th>From</th><th>Date</th><th></th></tr></thead>
        <tbody>${anns.map(annRowReadOnly).join("")}</tbody>
      </table>
    </div>`;
}

async function refreshBadge() {
  try {
    const n = await api.get("/notifications");
    $badge.hidden = n.unread === 0;
    $badge.textContent = n.unread;
  } catch (_) {}
}

// ---------- router ----------
const routes = [];
function route(pattern, fn) { routes.push({ pattern, fn }); }
async function navigate() {
  const path = location.hash.replace(/^#/, "") || "/";
  renderSidebar(path.replace(/^(\/events\/\d+\/wishlist)\/.+$/, "$1")
    .replace(/^(\/events\/\d+\/clan)\/.+$/, "$1")
    .replace(/^\/events\/\d+$/, "/")
    .replace(/^(\/admin\/events)\/.+$/, "$1"));
  closeSidebar();
  for (const r of routes) {
    const m = path.match(r.pattern);
    if (m) { try { await r.fn(...m.slice(1)); } catch (e) { render("Oops", alertBox(e.message)); } return; }
  }
  go("/");
}
window.addEventListener("hashchange", navigate);
$bell.onclick = () => go("/notifications");
$menuBtn.onclick = toggleSidebar;
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSidebar(); });
$sidebarOverlay.onclick = closeSidebar;

// ---------- boot ----------
async function boot() {
  try {
    ME = await api.get("/auth/me");
    $topbar.hidden = false;
    if (!ME.user.full_name) return pageName();
    if (ME.must_change_password) return pageForcedPasswordChange();
    if (ME.needs_security_setup) return pageSecuritySetup(true);
    if (ME.families.length === 0) return pageNoFamily();
    FAMILY = ME.families[0];
    await refreshCurrentEvent();
    $sidebar.hidden = false;
    $menuBtn.hidden = false;
    $shell.classList.add("authed");
    restoreSidebarState();
    refreshBadge();
    navigate();
  } catch (_) {
    $topbar.hidden = true;
    $sidebar.hidden = true;
    $shell.classList.remove("authed");
    $menuBtn.hidden = true;
    if (IS_REGISTER_ENTRY) pageRegisterStart();
    else pageLogin();
  }
}

// ---------- auth pages ----------
function pageLogin() {
  render("", `
    <div class="center" style="margin-top:2rem">
      <div style="font-size:4rem">🎁</div>
      <h2>Welcome to Secret Santa</h2>
      <p class="muted">Family gift exchanges made simple.</p>
    </div>
    <label for="username">Username</label>
    <input id="username" autocomplete="username">
    <label for="password">Password</label>
    <div class="password-field">
      <input id="password" type="password" autocomplete="current-password">
      <button type="button" class="password-toggle" id="togglePw" aria-label="Show password">👁</button>
    </div>
    <div id="msg"></div>
    <button class="btn btn-primary" id="loginBtn">Sign In</button>
    <p class="muted center" style="font-size:.78rem;margin-top:2rem">
      By continuing you agree to our
      <a href="/privacy_terms#terms" target="_blank" rel="noopener">Terms of Service</a>
      and <a href="/privacy_terms#privacy" target="_blank" rel="noopener">Privacy Policy</a>.
    </p>
  `);
  document.getElementById("togglePw").onclick = () => {
    const pw = document.getElementById("password");
    const btn = document.getElementById("togglePw");
    const showing = pw.type === "password";
    pw.type = showing ? "text" : "password";
    btn.textContent = showing ? "🙈" : "👁";
    btn.setAttribute("aria-label", showing ? "Hide password" : "Show password");
  };
  document.getElementById("loginBtn").onclick = async () => {
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;
    try {
      await api.post("/auth/login-password", { username, password });
      location.hash = "/"; boot();
    } catch (e) { showError(e); }
  };
}

function pageRegisterStart() {
  render("", `
    <div class="center" style="margin-top:2rem">
      <div style="font-size:4rem">🎁</div>
      <h2>Create Your Account</h2>
      <p class="muted">Pick a username to get started.</p>
    </div>
    <label for="newUsername">Create Username</label>
    <input id="newUsername" autocomplete="username">
    <div id="msg"></div>
    <button class="btn btn-primary" id="continueBtn">Continue</button>
    <button class="btn btn-quiet" id="loginInsteadBtn">I already have an account</button>
  `);
  document.getElementById("continueBtn").onclick = async () => {
    const username = document.getElementById("newUsername").value.trim();
    try {
      const r = await api.post("/auth/login-start", { username });
      if (r.exists === false) pageRegister(username);
      else {
        document.getElementById("msg").innerHTML =
          alertBox("That username is already taken. Try logging in instead.");
      }
    } catch (e) { showError(e); }
  };
  document.getElementById("loginInsteadBtn").onclick = () => { location.hash = ""; pageLogin(); };
}

function pageRegister(username) {
  const joining = !!PENDING_JOIN_CODE;
  render("", `
    <h2 class="center">Create your account</h2>
    <p class="muted center">Username: <strong>${esc(username)}</strong></p>
    <label for="regPassword">Create Password</label>
    <input id="regPassword" type="password" autocomplete="new-password">
    <div id="msg"></div>
    <button class="btn btn-primary" id="createBtn">Create Account</button>
  `);
  document.getElementById("createBtn").onclick = async () => {
    try {
      const r = await api.post("/auth/register", {
        username,
        password: document.getElementById("regPassword").value,
        clan_name: joining ? "" : `${username}'s Clan`,
      });
      if (r.family) pageClanCreated(r.family);
      else boot();
    } catch (e) { showError(e); }
  };
}

function pageClanCreated(family) {
  const regUrl = `${location.origin}/#/join/${family.join_code}`;
  render("", `
    <div class="center" style="margin-top:1rem"><div style="font-size:3rem">🎉</div></div>
    <h2 class="center">${esc(family.name)} is ready!</h2>
    <p class="muted center">You're its clan admin. Share this code or link so family can join:</p>
    <div class="card center">
      <div class="reveal-name" style="font-size:1.8rem">${esc(family.join_code)}</div>
      <button class="btn btn-quiet" id="copyLinkBtn" style="margin-top:.5rem">Copy Registration Link</button>
      <div id="copyMsg"></div>
    </div>
    <button class="btn btn-primary" id="continueBtn">Continue to Dashboard</button>
  `);
  document.getElementById("copyLinkBtn").onclick = async () => {
    try {
      await navigator.clipboard.writeText(regUrl);
      document.getElementById("copyMsg").innerHTML = alertBox("Link copied!", true);
    } catch (e) {
      document.getElementById("copyMsg").innerHTML = alertBox(regUrl, true);
    }
  };
  document.getElementById("continueBtn").onclick = () => boot();
}

function pageName() {
  render("Welcome!", `
    <h2>What's your name?</h2>
    <p class="muted">This is how your family will see you.</p>
    <label for="name">Your name</label>
    <input id="name" autocomplete="name">
    <div id="msg"></div>
    <button class="btn btn-primary" id="saveBtn">Continue</button>
  `);
  document.getElementById("saveBtn").onclick = async () => {
    try {
      await api.patch("/auth/me", { full_name: document.getElementById("name").value });
      boot();
    } catch (e) { showError(e); }
  };
}

function pageForcedPasswordChange() {
  render("Set a New Password", `
    <h2>Please set a new password</h2>
    <p class="muted">Your clan admin gave you a temporary password. Choose a new one only you know.</p>
    <label for="newPw">New password</label>
    <input id="newPw" type="password" autocomplete="new-password">
    <div id="msg"></div>
    <button class="btn btn-primary" id="setPwBtn">Reset Password</button>
  `);
  document.getElementById("setPwBtn").onclick = async () => {
    try {
      await api.patch("/auth/security", { password: document.getElementById("newPw").value });
      boot();
    } catch (e) { showError(e); }
  };
}

function pageSecuritySetup(forced) {
  // A brand-new account has to set a password first, so that card leads (and
  // holds the primary button); otherwise the profile leads.
  const canEditName = !ME.user.full_name || FAMILY?.role === "admin" || ME.user.is_app_admin;
  const profileCard = `
    <section class="card form-card">
      <h2>My profile</h2>
      <p class="muted">Your clan sees this on My Clan, so they know what to get you.</p>
      <div class="profile-photo-row">
        <div id="avatarPreview"></div>
        <div>
          <label for="photoInput" style="margin-top:0" id="photoLabel"></label>
          <input id="photoInput" type="file" accept="image/*">
          <p class="muted" style="margin:0 0 .4rem;font-size:.8rem">Up to ${MAX_PHOTO_MB}MB. It's cropped to a square.</p>
          <button class="btn btn-quiet" style="width:auto" id="removePhotoBtn">Remove Photo</button>
        </div>
      </div>
      <div id="photoMsg"></div>

      ${canEditName ? `
      <label for="displayName">Your name</label>
      <input id="displayName" value="${esc(ME.user.full_name)}">` : `
      <label>Your name</label>
      <p style="margin:0 0 .2rem"><strong>${esc(ME.user.full_name)}</strong></p>
      <p class="muted" style="margin:0">Only your clan admin can change your name.</p>`}
      <label for="aboutMe">About me</label>
      <textarea id="aboutMe" rows="3" maxlength="1000">${esc(ME.user.about_me)}</textarea>
      <label for="likes">My likes</label>
      <textarea id="likes" rows="3" maxlength="1000">${esc(ME.user.likes)}</textarea>
      <label for="favColor">My favorite color <span class="muted">(optional)</span></label>
      <input id="favColor" maxlength="40" value="${esc(ME.user.favorite_color)}">
      <label for="avoidGifts">What not to give me</label>
      <textarea id="avoidGifts" rows="3" maxlength="1000">${esc(ME.user.avoid_gifts)}</textarea>
      <div id="nameMsg"></div>
      <button class="btn ${forced ? 'btn-secondary' : 'btn-primary'}" id="saveNameBtn">Save Profile</button>
    </section>
  `;
  // Someone who already has a password resets it with the current one (masked);
  // an account with none yet just sets one.
  const hasPw = !!ME.user.has_password;
  const passwordCard = `
    <section class="card form-card">
    <h2>${hasPw ? "Reset your password" : "Set up your password"}</h2>
    <p class="muted">${hasPw ? "Enter your current password, then a new one." : "You'll use this to sign in."} At least 8 characters.</p>
    ${hasPw ? `
    <label for="currentPassword">Current password</label>
    <input id="currentPassword" type="password" autocomplete="current-password">` : ""}
    <label for="newPassword">${hasPw ? "New password" : "Password"}</label>
    <input id="newPassword" type="password" autocomplete="new-password">
    <div id="pwMsg"></div>
    <button class="btn ${forced ? 'btn-primary' : 'btn-secondary'}" id="savePwBtn">${hasPw ? "Reset Password" : "Save Password"}</button>
    </section>
  `;
  render("Profile & Security", `
    ${forced ? passwordCard + profileCard : profileCard + passwordCard}
    ${!forced ? `<button class="btn btn-quiet" id="doneBtn">Done</button>` : ""}
  `);
  const refreshPhotoUi = () => {
    document.getElementById("avatarPreview").innerHTML = avatarHtml(ME.user, "avatar-lg");
    document.getElementById("photoLabel").textContent = ME.user.photo_url ? "Change photo" : "Add a photo";
    document.getElementById("removePhotoBtn").hidden = !ME.user.photo_url;
  };
  refreshPhotoUi();
  document.getElementById("photoInput").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const msg = document.getElementById("photoMsg");
    if (photoTooBig(file)) {
      msg.innerHTML = alertBox(PHOTO_TOO_BIG);
      e.target.value = "";
      return;
    }
    try {
      const fd = new FormData();
      fd.append("photo", file);
      const r = await api.postForm("/auth/me/photo", fd);
      ME.user = r.user;
      msg.innerHTML = alertBox("Photo saved!", true);
    } catch (err) { msg.innerHTML = alertBox(err.message); }
    e.target.value = "";
    refreshPhotoUi();
  };
  document.getElementById("removePhotoBtn").onclick = async () => {
    const msg = document.getElementById("photoMsg");
    try {
      const r = await api.del("/auth/me/photo");
      ME.user = r.user;
      msg.innerHTML = alertBox("Photo removed.", true);
    } catch (err) { msg.innerHTML = alertBox(err.message); }
    refreshPhotoUi();
  };
  document.getElementById("saveNameBtn").onclick = async () => {
    try {
      const val = (id) => document.getElementById(id).value;
      const body = {
        about_me: val("aboutMe"), likes: val("likes"),
        favorite_color: val("favColor"), avoid_gifts: val("avoidGifts"),
      };
      if (canEditName) body.full_name = val("displayName");
      const r = await api.patch("/auth/me", body);
      ME.user = r.user;
      document.getElementById("nameMsg").innerHTML = alertBox("Profile saved!", true);
    } catch (e) {
      document.getElementById("nameMsg").innerHTML = alertBox(e.message);
    }
  };
  document.getElementById("savePwBtn").onclick = async () => {
    const password = document.getElementById("newPassword").value;
    const current = document.getElementById("currentPassword");
    try {
      await api.patch("/auth/security", { password, current_password: current ? current.value : undefined });
      if (forced) return boot();
      ME.user.has_password = true;
      document.getElementById("pwMsg").innerHTML = alertBox(hasPw ? "Password reset!" : "Password saved!", true);
      document.getElementById("newPassword").value = "";
      if (current) current.value = "";
    } catch (e) {
      const el = document.getElementById("pwMsg");
      el.innerHTML = alertBox(e.message);
    }
  };
  const doneBtn = document.getElementById("doneBtn");
  if (doneBtn) doneBtn.onclick = () => { history.back(); };
}

route(/^\/security$/, () => pageSecuritySetup(false));

function pageNoFamily() {
  const hasPending = !!PENDING_JOIN_CODE;
  render("Secret Santa", `
    <h2>Join your family</h2>
    <p class="muted">${hasPending ? "Confirm below to join." : "Have a family code? Enter it below."}</p>
    <label for="jcode">Family code</label>
    <input id="jcode" class="code-input" maxlength="8" style="text-transform:uppercase"
      value="${esc(PENDING_JOIN_CODE || "")}" ${hasPending ? "readonly" : ""}>
    <div id="msg"></div>
    <button class="btn btn-primary" id="joinBtn">Join Family</button>
    ${!hasPending ? `
    <hr style="margin:2rem 0">
    <p class="muted center">Or start your own clan:</p>
    <label for="fname">Clan name</label>
    <input id="fname">
    <button class="btn btn-secondary" id="createBtn">Start My Clan</button>` : ""}
  `);
  document.getElementById("joinBtn").onclick = async () => {
    try {
      await api.post("/families/join", { join_code: document.getElementById("jcode").value });
      PENDING_JOIN_CODE = null;
      boot();
    } catch (e) { showError(e); }
  };
  const createBtn = document.getElementById("createBtn");
  if (createBtn) createBtn.onclick = async () => {
    try { await api.post("/families", { name: document.getElementById("fname").value }); boot(); }
    catch (e) { showError(e); }
  };
}

// ---------- main pages ----------
// One label/value row of a details list (skipped when there's no value).
function detailRow(label, valueHtml, cls = "") {
  return valueHtml ? `<dt>${label}</dt><dd class="${cls}">${valueHtml}</dd>` : "";
}
const TBA = `<span class="muted">To be announced</span>`;

// My giftee's name for an event; a link to their profile unless codenames are on
// (the profile would reveal the real name). `d` is my assignment (assigned: true).
function gifteeLink(ev, d) {
  return ev.use_codenames || !d.giftee_user_id
    ? `<strong>${esc(d.giftee_display_name)}</strong>`
    : `<a class="person-link" href="#/events/${ev.id}/clan/${d.giftee_user_id}"><strong>${esc(d.giftee_display_name)}</strong> →</a>`;
}

// One upcoming gift exchange on the dashboard. `d` is my assignment there (null when I'm not in it).
function dashEventBlock(e, d) {
  const gifteeHtml = !d ? `<span class="muted">You're not in this gift exchange.</span>`
    : !d.assigned ? `<span class="muted">${esc(d.message)}</span>`
    : gifteeLink(e, d);
  return `
    <div class="event-block">
      <h3 class="event-title"><a class="person-link" href="#/events/${e.id}">${esc(e.name)}</a></h3>
      <dl class="detail-list">
        <dt>My Giftee</dt><dd>${gifteeHtml}</dd>
        <dt>Date</dt><dd>${esc(fmtEventDate(e.event_date))}</dd>
        ${e.theme ? `<dt>Theme</dt><dd>${esc(e.theme)}</dd>` : ""}
      </dl>
      ${d && d.assigned ? `<div class="event-actions">
        <button class="btn btn-outline" onclick="go('/events/${e.id}/messages/giftee')">Message My Giftee</button>
        <button class="btn btn-outline" onclick="go('/events/${e.id}/messages/giver')">Message My Secret Santa</button>
      </div>` : ""}
      <button class="btn btn-secondary btn-block" onclick="go('/events/${e.id}')">View Event Details</button>
    </div>`;
}

route(/^\/$/, async () => {
  const first = (ME.user.full_name || "").trim().split(/\s+/)[0] || "there";
  const [all, anns] = await Promise.all([
    api.get(`/families/${FAMILY.id}/events`),
    api.get(`/families/${FAMILY.id}/announcements`),
  ]);
  const upcoming = all.filter(e => !eventHasHappened(e) && e.status !== "cancelled")
    .sort((x, y) => x.event_date.localeCompare(y.event_date));
  const mine = await Promise.all(upcoming.map(e =>
    e.i_am_participating ? api.get(`/events/${e.id}/assignments/mine`) : null));
  const clanEvent = CURRENT_EVENT || upcoming[0];
  const annHtml = anns.length ? annTable(anns) : `<p class="muted" style="margin:0">No announcements yet.</p>`;
  const sections = [
    `<div class="greeting"><h2>Hello, ${esc(first)}! 👋</h2></div>`,
    `<div class="dash-section"><h2>Announcements</h2>${annHtml}</div>`,
  ];

  sections.push(upcoming.length ? `
    <section class="card">
      <h2>My upcoming gift exchange${upcoming.length === 1 ? "" : "s"}</h2>
      ${upcoming.map((e, i) => dashEventBlock(e, mine[i])).join("")}
    </section>` : `
    <section class="card">
      <h2>My upcoming gift exchange</h2>
      <p class="muted">No gift exchange is happening right now.${FAMILY.role === "admin" ? "" : " Check back soon!"}</p>
      ${FAMILY.role === "admin" ? `<button class="btn btn-secondary" style="width:auto" onclick="go('/admin/events')">Create a Gift Exchange</button>` : ""}
    </section>`);

  // Shortcuts, in their own card at the very bottom. Wishlist and clan are per gift
  // exchange, so they only show when there is one.
  sections.push(`
    <section class="card">
      <h2>My Links</h2>
      <div class="event-actions" style="margin-bottom:0">
        <button class="btn btn-primary" onclick="go('/security')">Edit My Profile</button>
        ${clanEvent ? `
        <button class="btn btn-primary" onclick="go('/events/${clanEvent.id}/wishlist')">View My Wishlist</button>
        <button class="btn btn-primary" onclick="go('/events/${clanEvent.id}/clan')">View My Clan</button>` : ""}
      </div>
    </section>`);

  render("My Dashboard", sections.join(""));
  $app.querySelectorAll("[data-del-ann]").forEach(b => b.onclick = async () => {
    if (!confirm("Delete this announcement?")) return;
    await api.del(`/announcements/${b.dataset.delAnn}`);
    navigate();
  });
});

// Dish sign-up card on the event page. It opens once names are drawn; each person
// has ONE entry that can hold several dishes, which they can edit or remove.
const MAX_DISHES = 10;
function mountDishes(el, ev, initial) {
  let entries = initial;
  const canEdit = ev.i_am_participating && ev.status === "matched";
  const mineEntry = () => entries.find(e => e.user.id === ME.user.id);
  const msg = (html) => { el.querySelector("#dishMsg").innerHTML = html; };

  function view() {
    let body;
    if (ev.status === "open") {
      body = `<p class="muted" style="margin:0">Dish sign-up opens once names are drawn.</p>`;
    } else {
      const list = entries.length ? `<ul class="dish-list">${entries.map(e => `
        <li class="dish-entry">
          <a class="person-link" href="#/events/${ev.id}/clan/${e.user.id}">${avatarHtml(e.user, "avatar-sm")}<span>${esc(e.user.display_name)}${e.user.id === ME.user.id ? ` <span class="muted">(you)</span>` : ""}</span></a>
          <div class="dish-chips">${e.dishes.map(d => `<span class="dish-chip">${esc(d.name)}</span>`).join("")}</div>
          ${canEdit && e.user.id === ME.user.id ? `<div class="dish-entry-actions">
            <button class="btn btn-secondary" data-edit-dishes>Edit</button>
            <button class="btn btn-quiet" data-remove-dishes>Remove</button></div>` : ""}
        </li>`).join("")}</ul>`
        : `<p class="muted" style="margin:0 0 .6rem">No one has added a dish yet.</p>`;
      body = list + (canEdit && !mineEntry()
        ? `<button class="btn btn-primary" style="width:auto;margin-bottom:0" data-edit-dishes>Add My Dishes</button>` : "");
    }
    el.innerHTML = `<h2>Dishes to bring</h2><div id="dishMsg"></div>${body}`;
    el.querySelectorAll("[data-edit-dishes]").forEach(b => b.onclick = editor);
    const remove = el.querySelector("[data-remove-dishes]");
    if (remove) remove.onclick = async () => {
      if (!confirm("Remove all of your dishes from the list?")) return;
      try { entries = await api.del(`/events/${ev.id}/dishes/mine`); view(); }
      catch (e) { msg(alertBox(e.message)); }
    };
  }

  function editor() {
    const mine = mineEntry();
    el.innerHTML = `
      <h2>${mine ? "Edit my dishes" : "What are you bringing?"}</h2>
      <div id="dishMsg"></div>
      <div id="dishRows"></div>
      <button type="button" class="btn btn-quiet" style="width:auto" id="addDishRow">+ Add another dish</button>
      <div class="form-actions">
        <button class="btn btn-primary" id="saveDishes">Save</button>
        <button class="btn btn-quiet" id="cancelDishes">Cancel</button>
      </div>`;
    const rows = el.querySelector("#dishRows");
    const addBtn = el.querySelector("#addDishRow");
    const sync = () => {   // keep one row at least, and cap how many
      addBtn.hidden = rows.children.length >= MAX_DISHES;
      rows.querySelectorAll(".icon-btn").forEach(b => { b.hidden = rows.children.length === 1; });
    };
    const addRow = (value = "") => {
      const row = h(`<div class="dish-row"><input maxlength="120" aria-label="Dish name" value="${esc(value)}"><button type="button" class="icon-btn" aria-label="Remove this dish">✕</button></div>`).firstElementChild;
      row.querySelector(".icon-btn").onclick = () => { row.remove(); sync(); };
      row.querySelector("input").onkeydown = (e) => {   // Enter starts the next dish
        if (e.key !== "Enter") return;
        e.preventDefault();
        if (e.target.value.trim() && rows.children.length < MAX_DISHES) addRow().querySelector("input").focus();
      };
      rows.append(row);
      sync();
      return row;
    };
    (mine ? mine.dishes.map(d => d.name) : [""]).forEach(name => addRow(name));
    rows.querySelector("input").focus();
    addBtn.onclick = () => addRow().querySelector("input").focus();
    el.querySelector("#cancelDishes").onclick = view;
    el.querySelector("#saveDishes").onclick = async () => {
      const dishes = [...rows.querySelectorAll("input")].map(i => i.value.trim()).filter(Boolean);
      if (!dishes.length) return msg(alertBox("Please type a dish, or press Cancel."));
      try { entries = await api.put(`/events/${ev.id}/dishes/mine`, { dishes }); view(); }
      catch (e) { msg(alertBox(e.message)); }
    };
  }
  view();
}

// Past Gift Exchanges: everything that has happened, archived or not, newest first.
// An archived one opens as a read-only record.
function pastEventCard(e) {
  const st = eventStatus(e);
  return `<a class="wish-card card-link" href="#/events/${e.id}">
    <div class="wish-card-head">
      <span class="event-emoji" aria-hidden="true">${st.emoji}</span>
      <div class="wish-card-title">
        <strong>${esc(e.name)}</strong>
        <span class="wish-priority">${esc(fmtEventDate(e.event_date))}</span>
      </div>
    </div>
    <div><span class="status-tag ${st.cls}">${st.label}</span></div>
  </a>`;
}
route(/^\/past$/, async () => {
  const all = await api.get(`/families/${FAMILY.id}/events`);
  const past = all.filter(eventHasHappened).sort((x, y) => y.event_date.localeCompare(x.event_date));
  render("Past Gift Exchanges", past.length
    ? `<p class="muted" style="margin-top:0">Open one to look back at its details, messages and wishlists. Archived gift exchanges are view-only.</p>
       <div class="wish-grid">${past.map(pastEventCard).join("")}</div>`
    : `<div class="card"><p class="muted" style="margin:0">No past gift exchanges yet.</p></div>`);
});

// The event page any clan member can open: what/where/when, the rules the clan
// admin set, and who's coming (each row opens that person's profile).
route(/^\/events\/(\d+)$/, async (id) => {
  const [ev, people, dishes] = await Promise.all([
    api.get(`/events/${id}`), api.get(`/events/${id}/attendees`), api.get(`/events/${id}/dishes`),
  ]);
  const st = eventStatus(ev);
  const mine = ev.i_am_participating ? await api.get(`/events/${id}/assignments/mine`) : null;
  const gm = people.find(u => u.id === ev.game_master_id);
  const extras = [
    detailRow("Game master", gm ? `<a class="person-link" href="#/events/${id}/clan/${gm.id}">${esc(gm.display_name)}</a>` : ""),
    detailRow("Theme", esc(ev.theme)),
    detailRow("Gift amount", ev.budget_amount ? `${esc(ev.budget_currency)} ${ev.budget_amount}` : ""),
    detailRow("Rules", esc(ev.rules)),
    detailRow("What to bring", esc(ev.what_to_bring)),
    detailRow("Additional Details", esc(ev.other_info)),
  ].join("");
  const isAdmin = FAMILY.role === "admin";
  const rows = people.map(u => `
    <li><a class="person-link person-row" href="#/events/${id}/clan/${u.id}">${avatarHtml(u, "avatar-sm")}<span>${esc(u.display_name)}${u.id === ME.user.id ? ` <span class="muted">(you)</span>` : ""}</span></a></li>`).join("");
  render(ev.name, `
    ${ev.status === "completed" ? archivedBanner() : ""}
    <section class="card">
      <h2>${esc(ev.name)} <span class="status-tag ${st.cls}">${st.label}</span></h2>
      <dl class="detail-list">
        <dt>Date</dt><dd>${esc(fmtEventDate(ev.event_date))}</dd>
        <dt>Time</dt><dd>${ev.event_time ? esc(fmtEventTime(ev.event_time)) : TBA}</dd>
        <dt>Where</dt><dd>${ev.location ? esc(ev.location) : TBA}</dd>
        ${extras}
      </dl>
      ${extras ? "" : `<p class="muted">Your clan admin hasn't added rules or other details yet.</p>`}
      <div class="form-actions">
        <button class="btn btn-primary" onclick="go('/events/${id}/clan')">View Clan &amp; Wishlists</button>
        ${ev.i_am_participating ? `<button class="btn btn-primary" onclick="go('/events/${id}/messages')">View My Messages</button>` : ""}
        ${isAdmin && ev.status !== "completed" ? `<button class="btn btn-secondary" onclick="go('/admin/events/${id}/edit')">Edit Details</button>` : ""}
        ${isAdmin ? `<button class="btn btn-quiet" onclick="go('/admin/events/${id}')">Manage Gift Exchange</button>` : ""}
      </div>
    </section>
    ${mine && mine.assigned ? `
    <section class="card">
      <h2>Your Giftee is</h2>
      <p class="giftee-name">${gifteeLink(ev, mine)}</p>
    </section>` : ""}
    <section class="card" id="dishCard"></section>
    <section class="card">
      <h2>Who's coming (${people.length})</h2>
      ${people.length
        ? `<ul class="people-rows">${rows}</ul>`
        : `<p class="muted" style="margin:0">No one has been added to this gift exchange yet.</p>`}
    </section>
  `, { wide: true });
  mountDishes(document.getElementById("dishCard"), ev, dishes);
});

route(/^\/events\/(\d+)\/my-person$/, async (id) => {
  const [d, ev] = await Promise.all([api.get(`/events/${id}/assignments/mine`), api.get(`/events/${id}`)]);
  if (!d.assigned) return render("My Giftee", `<div class="card center"><p>${esc(d.message)}</p></div>`);
  const archived = ev.status === "completed";
  const budget = d.budget_amount
    ? `<p class="center muted">Gift budget: <strong>${esc(d.budget_currency)} ${d.budget_amount}</strong></p>` : "";
  render("My Giftee", `
    ${archived ? archivedBanner() : ""}
    <p class="center" style="margin-top:2rem">You ${archived ? "gave" : "are giving"} a gift to…</p>
    <div class="reveal-name">🎁 ${esc(d.giftee_display_name)}</div>
    ${budget}
    ${archived ? "" : `<p class="center muted">Shh — it's a secret! 🤫</p>`}
    <button class="btn btn-primary" onclick="go('/events/${id}/giftee')">See Their Wishlist</button>
    ${archived ? "" : `<button class="btn btn-secondary" onclick="go('/events/${id}/messages/giftee')">Send Them a Secret Message</button>`}
  `, { card: true });
});

route(/^\/events\/(\d+)\/wishlist$/, async (id) => {
  const d = await api.get(`/events/${id}/wishlists/mine`);
  const full = d.items.length >= d.limit;
  render("My Wishlist", `
    <div id="msg"></div>
    ${d.archived ? archivedBanner() : ""}
    <div class="wish-toolbar">
      <p class="muted" style="margin:0">${d.items.length} of ${d.limit} gifts${full && !d.archived ? " — your list is full" : ""}</p>
      ${full || d.archived ? "" : `<button class="btn btn-primary" style="width:auto;margin:0" id="newWishBtn">+ Add a Gift Idea</button>`}
    </div>
    ${d.items.length > 1 && !d.archived ? `<p class="muted" style="margin-top:0">Press and hold a gift, then drag it to change its priority. The gift at the top is the one you want most.</p>` : ""}
    ${d.items.length
      ? `<div class="wish-grid" id="myWishGrid"></div>`
      : `<div class="card"><p class="muted" style="margin:0">Your list is empty. Add your first gift idea!</p></div>`}
  `);
  const grid = document.getElementById("myWishGrid");
  if (grid) {
    d.items.forEach((i, n) => grid.append(myWishCard(i, id, n + 1, d.archived)));
    if (d.items.length > 1 && !d.archived) enableLongPressReorder(grid, async (order) => {
      grid.querySelectorAll(".wish-priority").forEach((el, n) => { el.textContent = `Priority ${n + 1}`; });
      try {
        await api.put(`/events/${id}/wishlists/order`, { item_ids: order.map(Number) });
        document.getElementById("msg").innerHTML = alertBox("Order saved!", true);
      } catch (e) { showError(e); navigate(); }
    });
  }
  const newBtn = document.getElementById("newWishBtn");
  if (newBtn) newBtn.onclick = () => go(`/events/${id}/wishlist/new`);
});

// Add / edit share one form; `item` is null when adding.
function renderWishForm(eventId, d, item) {
  const editing = !!item;
  render(editing ? "Edit Gift Idea" : "Add a Gift Idea", `
    <div id="msg"></div>
    <label for="iname">What would you love?</label>
    <input id="iname" value="${esc(editing ? item.item_name : "")}">
    <label for="idesc">Anything else they should know? <span class="muted">(optional)</span></label>
    <textarea id="idesc" rows="4" maxlength="1000">${esc(editing ? item.description || "" : "")}</textarea>
    <label for="ilink">Link to it online <span class="muted">(optional)</span></label>
    <input id="ilink" type="text" inputmode="url" autocapitalize="none" autocomplete="off" spellcheck="false" value="${esc(editing ? item.link_url || "" : "")}">
    <label for="iphoto">${editing && item.photo_url ? "Replace photo" : "Photo"} <span class="muted">(optional, up to ${MAX_PHOTO_MB}MB)</span></label>
    ${editing && item.photo_url ? `<div style="margin-bottom:.4rem">${wishThumbCell(item)}</div>` : ""}
    <input id="iphoto" type="file" accept="image/*">
    <div class="form-actions">
      <button class="btn btn-primary" id="saveWishBtn">${editing ? "Save Changes" : "Add to My List"}</button>
      <button class="btn btn-quiet" id="cancelWishBtn">Cancel</button>
    </div>
  `, { card: true });
  const backToList = () => go(`/events/${eventId}/wishlist`);
  document.getElementById("cancelWishBtn").onclick = backToList;
  // Fill in https:// as soon as they leave the field, so they see what will be saved.
  document.getElementById("ilink").onchange = (e) => {
    const link = normalizeUrl(e.target.value);
    if (link === null) showError({ message: LINK_HELP });
    else { e.target.value = link; document.getElementById("msg").innerHTML = ""; }
  };
  document.getElementById("saveWishBtn").onclick = async () => {
    try {
      const link = normalizeUrl(document.getElementById("ilink").value);
      if (link === null) { showError({ message: LINK_HELP }); window.scrollTo(0, 0); return; }
      const photo = document.getElementById("iphoto").files[0];
      if (photoTooBig(photo)) { showError({ message: PHOTO_TOO_BIG }); window.scrollTo(0, 0); return; }
      const fd = new FormData();
      fd.append("item_name", document.getElementById("iname").value);
      fd.append("description", document.getElementById("idesc").value);
      fd.append("link_url", link);
      if (photo) fd.append("photo", photo);
      if (editing) await api.patchForm(`/wishlists/${item.id}`, fd);
      else await api.postForm(`/events/${eventId}/wishlists`, fd);
      backToList();
    } catch (e) { showError(e); }
  };
}

function wishFormBlocked(eventId, msg) {
  render("My Wishlist", alertBox(msg) + `
    <button class="btn btn-secondary" style="width:auto" onclick="go('/events/${eventId}/wishlist')">Back to My Wishlist</button>`);
}

route(/^\/events\/(\d+)\/wishlist\/new$/, async (id) => {
  const d = await api.get(`/events/${id}/wishlists/mine`);
  if (d.archived) return wishFormBlocked(id, "This gift exchange is archived, so wishlists are view-only.");
  if (d.items.length >= d.limit) {
    return wishFormBlocked(id, `Your list is full (${d.limit} gifts). Remove one to add another.`);
  }
  renderWishForm(id, d, null);
});

route(/^\/events\/(\d+)\/wishlist\/(\d+)\/edit$/, async (id, itemId) => {
  const d = await api.get(`/events/${id}/wishlists/mine`);
  if (d.archived) return wishFormBlocked(id, "This gift exchange is archived, so wishlists are view-only.");
  const item = d.items.find(i => i.id === Number(itemId));
  if (!item) return wishFormBlocked(id, "We couldn't find that gift idea.");
  if (item.locked) return wishFormBlocked(id, "Cannot edit this item as it has already been bought.");
  renderWishForm(id, d, item);
});

route(/^\/events\/(\d+)\/giftee$/, async (id) => {
  let d;
  try { d = await api.get(`/events/${id}/wishlists/giftee`); }
  catch (e) { return render("Their Wishlist", alertBox(e.message)); }
  const items = d.items.length
    ? clanWishGrid(d.items, d.archived)
    : `<div class="card"><p class="muted" style="margin:0">${d.archived ? "They didn't add any gift ideas." : "They haven't added any gift ideas yet. Send them a friendly nudge!"}</p></div>`;
  render("Their Wishlist", (d.archived ? archivedBanner() : "") + items + (d.archived ? "" : `
    <button class="btn btn-secondary" style="width:auto;margin-top:.75rem" onclick="go('/events/${id}/messages/giftee')">Send a Secret Message</button>`));
  wireBuyButtons();
});

// The person's profile shown like an ID: photo on the side, details beside it
// (stacked on a phone). Empty fields are skipped.
function colorSwatchHtml(color) {
  return color && window.CSS && CSS.supports("color", color)
    ? `<span class="color-swatch" style="background:${esc(color)}" aria-hidden="true"></span>` : "";
}
function idCardHtml(user) {
  const name = user.display_name || user.full_name;
  const swatch = colorSwatchHtml(user.favorite_color);
  const rows = [
    ["About me", user.about_me ? esc(user.about_me) : ""],
    ["Likes", user.likes ? esc(user.likes) : ""],
    ["Favorite color", user.favorite_color ? `${swatch}${esc(user.favorite_color)}` : ""],
    ["Please don't give me", user.avoid_gifts ? esc(user.avoid_gifts) : "", "id-avoid"],
  ].filter(r => r[1]);
  return `
    <section class="id-card">
      <div class="id-band">🎄 ${esc(FAMILY.name)}</div>
      <div class="id-body">
        <div class="id-photo">${user.photo_url
          ? `<img class="id-img" src="${esc(user.photo_url)}" alt="Photo of ${esc(name)}">`
          : `<span class="id-initials" style="background:${safeColor(user.avatar_color)}" aria-hidden="true">${esc(initialsOf(name))}</span>`}</div>
        <div class="id-details">
          <h2 class="id-name">${esc(name)}</h2>
          ${rows.length
            ? `<dl class="id-fields">${rows.map(([k, v, cls]) => `<dt>${k}</dt><dd class="${cls || ""}">${v}</dd>`).join("")}</dl>`
            : `<p class="muted">${esc(name)} hasn't filled out their profile yet.</p>`}
        </div>
      </div>
    </section>`;
}

function personCard(user, eventId) {
  const name = user.display_name || user.full_name;
  const photo = user.photo_url
    ? `<img class="person-img" src="${esc(user.photo_url)}" alt="">`
    : `<span class="person-initials" style="background:${safeColor(user.avatar_color)}" aria-hidden="true">${esc(initialsOf(name))}</span>`;
  const card = h(`<button type="button" class="person-card" aria-label="${esc(name)}'s profile and wishlist">
    <span class="person-photo">${photo}</span>
    <span class="person-name">${esc(name)}</span>
  </button>`).firstElementChild;
  card.onclick = () => go(`/events/${eventId}/clan/${user.id}`);
  return card;
}

route(/^\/events\/(\d+)\/clan$/, async (id) => {
  const list = await api.get(`/events/${id}/wishlists/clan`);
  list.sort((a, b) => a.user.display_name.localeCompare(b.user.display_name));
  render("My Clan", list.length
    ? `<p class="muted">Tap someone to see their profile and wishlist.</p><div class="person-grid" id="personGrid"></div>`
    : `<div class="card center"><p>No one's joined this gift exchange yet.</p></div>`);
  const grid = document.getElementById("personGrid");
  if (grid) list.forEach(entry => grid.append(personCard(entry.user, id)));
});

route(/^\/events\/(\d+)\/clan\/(\d+)$/, async (id, uid) => {
  const [list, mine, ev] = await Promise.all([
    api.get(`/events/${id}/wishlists/clan`), api.get(`/events/${id}/assignments/mine`),
    api.get(`/events/${id}`),
  ]);
  const archived = ev.status === "completed";
  const entry = list.find(e => e.user.id === Number(uid));
  if (!entry) {
    return render("My Clan", alertBox("We couldn't find that person in this gift exchange.") + `
      <button class="btn btn-secondary" style="width:auto" onclick="go('/events/${id}/clan')">Back to My Clan</button>`);
  }
  const n = entry.items.length;
  const name = entry.user.display_name;
  const isMyGiftee = mine.assigned && mine.giftee_user_id === entry.user.id && !archived;
  render("My Clan", `
    ${archived ? archivedBanner() : ""}
    ${idCardHtml(entry.user)}
    ${isMyGiftee ? `
    <section class="card">
      <button class="btn btn-secondary" style="width:auto;margin-top:0" onclick="go('/events/${id}/messages/giftee')">Message ${esc(name)}</button>
      <p class="muted" style="margin:.4rem 0 0">You're ${esc(name)}'s Secret Santa. Your message is sent anonymously, so they'll only see that it's from their Secret Santa.</p>
    </section>` : ""}
    <h2 class="section-title">Wishlist${n ? ` <span class="muted">· ${n} gift idea${n === 1 ? "" : "s"}</span>` : ""}</h2>
    ${n ? clanWishGrid(entry.items, archived) : `<div class="card"><p class="muted" style="margin:0">No gift ideas yet.</p></div>`}
  `);
  wireBuyButtons();
});

route(/^\/events\/(\d+)\/messages$/, async (id) => {
  const [d, ev] = await Promise.all([api.get(`/events/${id}/messages`), api.get(`/events/${id}`)]);
  const archived = ev.status === "completed";
  function thread(key, label) {
    const t = d[key];
    if (!t) return "";
    const msgs = t.messages.map(m =>
      `<div class="bubble ${m.mine ? "mine" : "theirs"}">${esc(m.body)}</div>`).join("")
      || `<p class="muted center">${archived ? "No messages." : "No messages yet. Say hello!"}</p>`;
    return `<section class="card"><h2>${label}: ${esc(t.with_display_name)}</h2>
      <div>${msgs}</div>
      ${archived ? "" : `<label for="in-${key}">Write a message</label>
      <input id="in-${key}" maxlength="2000">
      <button class="btn btn-primary" data-send="${key}">Send</button>`}</section>`;
  }
  render("Messages", `
    <div id="msg"></div>
    <p class="muted" style="margin-top:0">Gift exchange: <strong>${esc(ev.name)}</strong>. These conversations are only for this gift exchange.</p>
    ${archived ? archivedBanner() : ""}
    ${thread("giftee", "To my person")}
    ${thread("giver", "With my Secret Santa")}
    ${!d.giftee && !d.giver ? `<div class="card center"><p>Messages open up after names are drawn.</p></div>` : ""}
  `);
  $app.querySelectorAll("[data-send]").forEach(b => b.onclick = async () => {
    const key = b.dataset.send;
    const input = document.getElementById(`in-${key}`);
    if (!input.value.trim()) return;
    try { await api.post(`/events/${id}/messages`, { to: key, body: input.value }); navigate(); }
    catch (e) { showError(e); }
  });
});

async function renderMessageThread(id, key, label) {
  const [d, ev] = await Promise.all([api.get(`/events/${id}/messages`), api.get(`/events/${id}`)]);
  const t = d[key];
  const archived = ev.status === "completed";
  if (!t) {
    render(label, `<div class="card center"><p>Messages open up after names are drawn.</p></div>`);
    return;
  }
  const msgs = t.messages.map(m =>
    `<div class="bubble ${m.mine ? "mine" : "theirs"}">${esc(m.body)}</div>`).join("")
    || `<p class="muted center">${archived ? "No messages." : "No messages yet. Say hello!"}</p>`;
  render(label, `
    <div id="msg"></div>
    <p class="muted" style="margin-top:0">Gift exchange: <strong>${esc(ev.name)}</strong>. This conversation is only for this gift exchange.</p>
    <h2>${esc(t.with_display_name)}</h2>
    ${archived ? archivedBanner() : key === "giftee" ? `<p class="muted" style="margin-top:0">Your messages here are sent anonymously.</p>` : ""}
    <div>${msgs}</div>
    ${archived ? "" : `
    <label for="msgin">Write a message</label>
    <input id="msgin" maxlength="2000">
    <button class="btn btn-primary" id="sendBtn">Send</button>`}
  `, { card: true });
  const sendBtn = document.getElementById("sendBtn");
  if (sendBtn) sendBtn.onclick = async () => {
    const input = document.getElementById("msgin");
    if (!input.value.trim()) return;
    try { await api.post(`/events/${id}/messages`, { to: key, body: input.value }); navigate(); }
    catch (e) { showError(e); }
  };
}
route(/^\/events\/(\d+)\/messages\/giver$/, (id) => renderMessageThread(id, "giver", "Message to my Secret Santa"));
route(/^\/events\/(\d+)\/messages\/giftee$/, (id) => renderMessageThread(id, "giftee", "Message to my Giftee"));

route(/^\/announcements$/, async () => {
  const anns = await api.get(`/families/${FAMILY.id}/announcements`);
  const list = anns.length ? annTable(anns) : `<div class="card center"><p>No announcements yet.</p></div>`;
  render("Announcements", list);
  $app.querySelectorAll("[data-del-ann]").forEach(b => b.onclick = async () => {
    if (!confirm("Delete this announcement?")) return;
    await api.del(`/announcements/${b.dataset.delAnn}`);
    navigate();
  });
});

route(/^\/notifications$/, async () => {
  const d = await api.get("/notifications");
  const list = d.items.map(n => {
    const inner = `
      <strong>${esc(n.title)}</strong>
      ${n.body ? `<p>${esc(n.body)}</p>` : ""}
      <p class="muted">${new Date(n.at).toLocaleString()}</p>`;
    const style = n.is_read ? "opacity:.65" : "";
    return n.link_path
      ? `<a class="card notif-card" href="#${esc(n.link_path)}" data-notif="${n.id}" style="${style}">${inner}</a>`
      : `<div class="card" style="${style}">${inner}</div>`;
  }).join("") || `<div class="card center"><p>Nothing here yet.</p></div>`;
  render("Notifications", `
    ${d.unread ? `<button class="btn btn-quiet" id="readAll">Mark All as Read</button>` : ""}
    ${list}`);
  // Opening one marks it read; the link itself does the navigating.
  $app.querySelectorAll("[data-notif]").forEach(a => a.addEventListener("click", () => {
    api.post(`/notifications/${a.dataset.notif}/read`).then(refreshBadge).catch(() => {});
  }));
  const ra = document.getElementById("readAll");
  if (ra) ra.onclick = async () => { await api.post("/notifications/read-all"); refreshBadge(); navigate(); };
  refreshBadge();
});

// ---------- admin ----------
route(/^\/admin$/, async () => {
  const fam = await api.get(`/families/${FAMILY.id}`);
  const regUrl = `${location.origin}/#/join/${fam.join_code}`;
  render("Clan Admin Dashboard", `
    <section class="card form-card">
      <h2>Clan name</h2>
      <label for="clanName">Name</label>
      <input id="clanName" value="${esc(fam.name)}">
      <div id="nameMsg"></div>
      <button class="btn btn-secondary" id="saveClanName">Save Clan Name</button>
    </section>

    <div class="card form-card center">
      <p class="muted">Share this code so family can join:</p>
      <div class="reveal-name" style="font-size:1.8rem">${esc(fam.join_code)}</div>
      <button class="btn btn-quiet" id="copyLinkBtn" style="margin-top:.5rem">Copy Registration Link</button>
      <div id="copyMsg"></div>
    </div>
  `, { wide: true });
  document.getElementById("saveClanName").onclick = async () => {
    try {
      const r = await api.patch(`/families/${FAMILY.id}`, { name: document.getElementById("clanName").value });
      FAMILY.name = r.family.name;
      document.getElementById("nameMsg").innerHTML = alertBox("Clan name saved!", true);
    } catch (e) { showError(e); }
  };
  document.getElementById("copyLinkBtn").onclick = async () => {
    try {
      await navigator.clipboard.writeText(regUrl);
      document.getElementById("copyMsg").innerHTML = alertBox("Link copied!", true);
    } catch (e) {
      document.getElementById("copyMsg").innerHTML = alertBox(regUrl, true);
    }
  };
});

route(/^\/admin\/members$/, async () => {
  const current = CURRENT_EVENT;
  const households = await api.get(`/families/${FAMILY.id}/households`);
  const participants = current
    ? await api.get(`/events/${current.id}/participants`)
    : [];
  const participating = new Set(
    participants.filter(p => p.is_participating).map(p => p.user.id));

  const houseOpts = hid => `<option value="">—</option>` +
    households.map(hh => `<option value="${hh.id}" ${hh.id === hid ? "selected" : ""}>${esc(hh.name)}</option>`).join("");

  function memberRow(m) {
    const tr = h(`<tr>
      <td data-label="Name"><input data-name value="${esc(m.user.full_name)}" title="${esc(m.user.full_name)}"></td>
      <td data-label="Phone"><input data-phone value="${esc(m.user.phone || "")}" title="${esc(m.user.phone || "")}"></td>
      <td data-label="Email"><input data-email value="${esc(m.user.email || "")}" title="${esc(m.user.email || "")}"></td>
      <td data-label="Household"><select data-house>${houseOpts(m.household_id)}</select></td>
      <td data-label="Admin"><input type="checkbox" data-role ${m.role === "admin" ? "checked" : ""} aria-label="Clan admin"></td>
      <td data-label="Joining">${current
        ? `<input type="checkbox" data-joining ${participating.has(m.user.id) ? "checked" : ""} aria-label="Joining this year">`
        : "—"}</td>
      <td class="table-actions">
        <button class="btn btn-secondary" data-save>Save</button>
        <button class="btn btn-quiet" data-reset>Reset Password</button>
        <button class="btn btn-quiet" data-remove>Remove</button>
      </td>
    </tr>`).firstElementChild;
    wireRow(tr, m.membership_id, m.user.id);
    return tr;
  }

  function wireRow(tr, membershipId, userId) {
    const msg = () => document.getElementById("msg");
    tr.querySelector("[data-save]").onclick = async () => {
      const nameEl = tr.querySelector("[data-name]");
      const phoneEl = tr.querySelector("[data-phone]");
      const emailEl = tr.querySelector("[data-email]");
      try {
        await api.patch(`/families/${FAMILY.id}/members/${membershipId}`, {
          full_name: nameEl.value, phone: phoneEl.value, email: emailEl.value,
        });
        nameEl.title = nameEl.value; phoneEl.title = phoneEl.value; emailEl.title = emailEl.value;
        msg().innerHTML = alertBox("Saved!", true);
      } catch (err) { showError(err); }
    };
    tr.querySelector("[data-house]").onchange = async e => {
      try {
        await api.patch(`/families/${FAMILY.id}/members/${membershipId}`,
          { household_id: e.target.value ? Number(e.target.value) : null });
        msg().innerHTML = alertBox("Saved!", true);
      } catch (err) { showError(err); }
    };
    tr.querySelector("[data-role]").onchange = async e => {
      try {
        await api.patch(`/families/${FAMILY.id}/members/${membershipId}`,
          { role: e.target.checked ? "admin" : "member" });
        msg().innerHTML = alertBox("Saved!", true);
      } catch (err) { e.target.checked = !e.target.checked; showError(err); }
    };
    const joining = tr.querySelector("[data-joining]");
    if (joining) joining.onchange = async e => {
      if (e.target.checked) participating.add(userId); else participating.delete(userId);
      try {
        await api.put(`/events/${current.id}/participants`, { user_ids: [...participating] });
        msg().innerHTML = alertBox("Saved!", true);
      } catch (err) { e.target.checked = !e.target.checked; showError(err); }
    };
    tr.querySelector("[data-reset]").onclick = async () => {
      if (!confirm("Reset this person's password? Their old password will stop working.")) return;
      try {
        const r = await api.post(`/families/${FAMILY.id}/members/${membershipId}/reset-password`);
        msg().innerHTML = alertBox(
          `Password reset! New password: ${r.temp_password} (write this down, it won't be shown again). ` +
          `They'll be asked to choose their own password next time they sign in.`, true);
      } catch (err) { showError(err); }
    };
    tr.querySelector("[data-remove]").onclick = async () => {
      if (!confirm("Remove this person from the clan? This can't be undone.")) return;
      try {
        await api.del(`/families/${FAMILY.id}/members/${membershipId}`);
        tr.remove();
      } catch (err) { showError(err); }
    };
  }

  const members = await api.get(`/families/${FAMILY.id}/members`);
  render("Members", `
    <div id="msg"></div>
    ${current ? "" : `<div class="card center"><p class="muted">Create a gift exchange first to track who's joining this year.</p></div>`}
    <div class="table-wrap">
      <table class="data" id="membersTable">
        <colgroup>
          <col style="width:15%"><col style="width:13%"><col style="width:21%">
          <col style="width:13%"><col style="width:7%"><col style="width:9%"><col style="width:22%">
        </colgroup>
        <thead><tr>
          <th>Name</th><th>Phone</th><th>Email</th><th>Household</th>
          <th>Admin</th><th>Joining${current ? ` (${esc(current.name)})` : ""}</th><th></th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>

    <section class="card form-card" style="margin-top:1.25rem">
    <h2>Add a member</h2>
    <p class="muted">Adds their account directly — you'll get a username and password to give them.</p>
    <label for="newName">Name</label>
    <input id="newName">
    <label for="newPhone">Phone number (optional)</label>
    <input id="newPhone" type="tel" inputmode="tel">
    <label for="newEmail">Email (optional)</label>
    <input id="newEmail" type="email">
    ${current ? `
    <div class="check-row">
      <input type="checkbox" id="newJoining">
      <label for="newJoining" style="margin:0">Joining ${esc(current.name)} this year</label>
    </div>` : ""}
    <div id="addMsg"></div>
    <button class="btn btn-primary" id="addMemberBtn">Add Member</button>
    </section>
  `, { wide: true });
  const tbody = $app.querySelector("#membersTable tbody");
  members.forEach(m => tbody.append(memberRow(m)));

  document.getElementById("addMemberBtn").onclick = async () => {
    try {
      const r = await api.post(`/families/${FAMILY.id}/members`, {
        full_name: document.getElementById("newName").value,
        phone: document.getElementById("newPhone").value,
        email: document.getElementById("newEmail").value,
      });
      const newJoining = document.getElementById("newJoining");
      if (current && newJoining && newJoining.checked) {
        participating.add(r.user.id);
        await api.put(`/events/${current.id}/participants`, { user_ids: [...participating] });
      }
      document.getElementById("addMsg").innerHTML = alertBox(
        `Added! Username: ${r.username} — Password: ${r.temp_password} (write this down, it won't be shown again)`, true);
      document.getElementById("newName").value = "";
      document.getElementById("newPhone").value = "";
      document.getElementById("newEmail").value = "";
      if (newJoining) newJoining.checked = false;
      tbody.append(memberRow({
        membership_id: r.membership_id, role: "member", household_id: null, user: r.user,
      }));
    } catch (e) { showError(e); }
  };
});

route(/^\/admin\/groups$/, async () => {
  const households = await api.get(`/families/${FAMILY.id}/households`);

  function groupRow(hh) {
    const tr = h(`<tr>
      <td data-label="Household Name"><input data-name value="${esc(hh.name)}"></td>
      <td class="table-actions">
        <button class="btn btn-secondary" data-save>Save</button>
        <button class="btn btn-quiet" data-del>Delete</button>
      </td>
    </tr>`).firstElementChild;
    const msg = () => document.getElementById("msg");
    tr.querySelector("[data-save]").onclick = async () => {
      try {
        await api.patch(`/households/${hh.id}`, { name: tr.querySelector("[data-name]").value });
        msg().innerHTML = alertBox("Saved!", true);
      } catch (e) { showError(e); }
    };
    tr.querySelector("[data-del]").onclick = async () => {
      try {
        await api.del(`/households/${hh.id}`);
        tr.remove();
        updateEmptyState();
      } catch (e) { showError(e); }
    };
    return tr;
  }

  render("Households", `
    <p class="muted">People in the same household won't draw each other's names.</p>
    <div id="msg"></div>
    <div class="table-wrap">
      <table class="data" id="groupsTable">
        <colgroup><col style="width:70%"><col style="width:30%"></colgroup>
        <thead><tr><th>Household Name</th><th></th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <p class="muted center" id="noGroups">No households yet.</p>
    <section class="card form-card" style="margin-top:1.25rem">
    <h2>Add a household</h2>
    <label>Household name</label>
    <input id="hname">
    <button class="btn btn-primary" id="addHouse">Add Household</button>
    </section>
  `, { wide: true });
  const gtbody = $app.querySelector("#groupsTable tbody");
  const noGroups = document.getElementById("noGroups");
  function updateEmptyState() {
    noGroups.style.display = gtbody.children.length ? "none" : "";
  }
  households.forEach(hh => gtbody.append(groupRow(hh)));
  updateEmptyState();
  document.getElementById("addHouse").onclick = async () => {
    try {
      const r = await api.post(`/families/${FAMILY.id}/households`,
        { name: document.getElementById("hname").value });
      document.getElementById("hname").value = "";
      gtbody.append(groupRow(r.household));
      updateEmptyState();
    } catch (e) { showError(e); }
  };
});

// Each gift exchange has its own participants, wishlists and giftee/gifter
// pairs, so who's joining is chosen per exchange (from the clan's members).
function fmtEventDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined,
    { weekday: "short", month: "short", day: "numeric", year: "numeric" });
}
function fmtEventTime(hhmm) {
  const [hh, mm] = hhmm.split(":").map(Number);
  return new Date(2000, 0, 1, hh, mm).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
const EVENT_STATUS = {
  open:      { emoji: "🎄", label: "Not drawn yet", cls: "tag-open" },
  matched:   { emoji: "✅", label: "Names drawn",   cls: "tag-drawn" },
  completed: { emoji: "📦", label: "Archived",      cls: "tag-done" },
};
function eventStatus(e) { return EVENT_STATUS[e.status] || { emoji: "🚫", label: e.status, cls: "tag-done" }; }

// A gift exchange has happened once its day has passed or it's archived.
function todayIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function eventHasHappened(e) { return e.status === "completed" || e.event_date < todayIso(); }

// Permanently deletes a gift exchange after a confirmation, then runs `done`.
async function deleteEvent(ev, done) {
  if (!confirm(`Delete "${ev.name}"? This permanently erases the gift exchange and everything in it (name draw, wishlists, messages, dishes and its announcements) for everyone. It can't be undone.`)) return;
  try {
    await api.del(`/events/${ev.id}`);
    await refreshCurrentEvent();
    done();
  } catch (e) { showError(e); }
}

function eventCard(e) {
  const st = eventStatus(e);
  const rules = [e.use_codenames ? "Fun codenames" : "", e.allow_same_household ? "Same-household matches allowed" : ""]
    .filter(Boolean).join(" · ");
  const card = h(`<article class="wish-card event-card">
    <div class="wish-card-head">
      <span class="event-emoji" aria-hidden="true">${st.emoji}</span>
      <div class="wish-card-title">
        <strong>${esc(e.name)}</strong>
        <span class="wish-priority">${esc(fmtEventDate(e.event_date))}</span>
      </div>
    </div>
    <div><span class="status-tag ${st.cls}">${st.label}</span></div>
    <ul class="event-meta">
      <li>👥 ${e.participant_count ?? 0} joining</li>
      <li>🎁 Up to ${e.wishlist_limit} gifts each</li>
      ${e.budget_amount ? `<li>💰 Budget ${esc(e.budget_currency)} ${e.budget_amount}</li>` : ""}
      ${rules ? `<li>⚙️ ${esc(rules)}</li>` : ""}
    </ul>
    <div class="wish-card-actions">
      <button class="btn btn-secondary" data-open>Manage</button>
      ${e.status !== "completed" ? `<button class="btn btn-quiet" data-edit>Edit</button>` : ""}
      <button class="btn btn-quiet" data-delete>Delete</button>
    </div>
  </article>`).firstElementChild;
  card.querySelector("[data-open]").onclick = () => go(`/admin/events/${e.id}`);
  const edit = card.querySelector("[data-edit]");
  if (edit) edit.onclick = () => go(`/admin/events/${e.id}/edit`);
  card.querySelector("[data-delete]").onclick = () => deleteEvent(e, () => navigate());
  return card;
}

route(/^\/admin\/events$/, async () => {
  const events = await api.get(`/families/${FAMILY.id}/events`);
  render("Gift Exchanges", `
    <div class="wish-toolbar">
      <p class="muted" style="margin:0">${events.length ? `${events.length} gift exchange${events.length === 1 ? "" : "s"}` : ""}</p>
      <button class="btn btn-primary" style="width:auto;margin:0" id="newEventBtn">+ Create a Gift Exchange</button>
    </div>
    ${events.length
      ? `<div class="wish-grid" id="eventGrid"></div>`
      : `<div class="card"><p class="muted" style="margin:0">No gift exchanges yet. Create one and pick who's joining.</p></div>`}
  `, { wide: true });
  const grid = document.getElementById("eventGrid");
  if (grid) events.forEach(e => grid.append(eventCard(e)));
  document.getElementById("newEventBtn").onclick = () => go("/admin/events/new");
});

// Add / edit share one form; `ev` is null when creating.
async function renderEventForm(ev) {
  const editing = !!ev;
  const [members, households, parts] = await Promise.all([
    api.get(`/families/${FAMILY.id}/members`),
    api.get(`/families/${FAMILY.id}/households`),
    editing ? api.get(`/events/${ev.id}/participants`) : Promise.resolve(null),
  ]);
  const houseName = Object.fromEntries(households.map(x => [x.id, x.name]));
  // New exchange: everyone starts checked (uncheck who's sitting this one out).
  const joining = editing
    ? new Set(parts.filter(p => p.is_participating).map(p => p.user.id))
    : new Set(members.map(m => m.user.id));
  const people = [...members].sort((x, y) => x.user.display_name.localeCompare(y.user.display_name));
  const rows = people.map(m => `
    <label class="check-row">
      <input type="checkbox" data-uid="${m.user.id}" ${joining.has(m.user.id) ? "checked" : ""}>
      <span>${esc(m.user.display_name)}
        <span class="muted">${m.household_id ? "• " + esc(houseName[m.household_id] || "") : "• ⚠ no household yet"}</span></span>
    </label>`).join("");

  // After the draw, who's joining and the draw rules are locked; the event
  // details (when, where, what to bring...) stay editable.
  const locked = editing && ev.status === "matched";
  const textarea = (id, label, value, hint) => `
    <label for="${id}">${label}${hint ? ` <span class="muted">${hint}</span>` : ""}</label>
    <textarea id="${id}" rows="3" maxlength="2000">${esc(value)}</textarea>`;

  render(editing ? "Edit Gift Exchange" : "Create a Gift Exchange", `
    <div id="msg"></div>
    <label for="ename">Name</label>
    <input id="ename" value="${esc(editing ? ev.name : "")}">
    <label for="edate">Date of the exchange</label>
    <input id="edate" type="date" value="${esc(editing ? ev.event_date : "")}">
    <label for="etime">Time <span class="muted">(optional)</span></label>
    <input id="etime" type="time" value="${esc(editing ? ev.event_time || "" : "")}">
    <label for="eplace">Where <span class="muted">(optional)</span></label>
    <input id="eplace" maxlength="255" value="${esc(editing ? ev.location : "")}">
    <label for="etheme">Theme <span class="muted">(optional)</span></label>
    <input id="etheme" maxlength="120" value="${esc(editing ? ev.theme : "")}">
    <label for="egm">Game master <span class="muted">(optional, one of the people joining)</span></label>
    <select id="egm"></select>
    <label for="ebudget">Gift amount <span class="muted">(optional)</span></label>
    <input id="ebudget" type="number" inputmode="decimal" value="${esc(editing && ev.budget_amount ? ev.budget_amount : "")}">

    <h2 style="margin-top:1.5rem">Good to know</h2>
    <p class="muted">Everyone in the clan sees these on the event page.</p>
    ${textarea("erules", "Rules", editing ? ev.rules : "")}
    ${textarea("ebring", "What to bring", editing ? ev.what_to_bring : "")}
    ${textarea("eother", "Additional details", editing ? ev.other_info : "")}

    ${locked ? `
    <div class="alert alert-ok" style="max-width:480px">🔒 Names are already drawn, so who's joining and the draw rules can't change. Use "Start Over" on the gift exchange page if you need to.</div>
    ` : `
    <h2 style="margin-top:1.5rem">Draw rules</h2>
    <label for="elimit">Wishlist size <span class="muted">(gifts each person can list)</span></label>
    <input id="elimit" type="number" min="1" max="20" value="${editing ? ev.wishlist_limit : 5}">
    <div class="check-row"><input type="checkbox" id="ecodes" ${editing && ev.use_codenames ? "checked" : ""}><label for="ecodes" style="margin:0">Use fun codenames instead of real names</label></div>
    <div class="check-row"><input type="checkbox" id="esame" ${editing && ev.allow_same_household ? "checked" : ""}><label for="esame" style="margin:0">Allow matches within the same household</label></div>

    <h2 style="margin-top:1.5rem">Who's joining?</h2>
    <p class="muted">Each gift exchange has its own wishlists and its own giftee/Secret Santa pairs, made only from the people checked here.</p>
    <div class="picker-tools">
      <span class="muted" id="joinCount"></span>
      <button type="button" class="btn btn-quiet" id="pickAll">Select everyone</button>
      <button type="button" class="btn btn-quiet" id="pickNone">Clear</button>
    </div>
    <div class="people-picker">${rows || `<p class="muted" style="padding:.6rem">No members in this clan yet.</p>`}</div>
    `}

    <div class="form-actions">
      <button class="btn btn-primary" id="saveEventBtn">${editing ? "Save Changes" : "Create Gift Exchange"}</button>
      <button class="btn btn-quiet" id="cancelEventBtn">Cancel</button>
    </div>
  `, { wide: true, card: true });

  const boxes = () => [...$app.querySelectorAll("[data-uid]")];
  // The game master menu lists only the people who are joining, and follows the checkboxes.
  let gmValue = editing && ev.game_master_id ? String(ev.game_master_id) : "";
  const gmSelect = document.getElementById("egm");
  gmSelect.onchange = () => { gmValue = gmSelect.value; };
  const fillGameMaster = (ids) => {
    gmSelect.innerHTML = `<option value="">No game master</option>` + people
      .filter(m => ids.has(m.user.id))
      .map(m => `<option value="${m.user.id}">${esc(m.user.display_name)}</option>`).join("");
    gmSelect.value = ids.has(Number(gmValue)) ? gmValue : "";
    gmValue = gmSelect.value;
  };
  if (locked) fillGameMaster(joining);
  if (!locked) {
    const updateCount = () => {
      const n = boxes().filter(c => c.checked).length;
      document.getElementById("joinCount").textContent = `${n} of ${boxes().length} joining`;
      fillGameMaster(new Set(boxes().filter(c => c.checked).map(c => Number(c.dataset.uid))));
    };
    $app.querySelector(".people-picker").addEventListener("change", updateCount);
    document.getElementById("pickAll").onclick = () => { boxes().forEach(c => c.checked = true); updateCount(); };
    document.getElementById("pickNone").onclick = () => { boxes().forEach(c => c.checked = false); updateCount(); };
    updateCount();
  }
  document.getElementById("cancelEventBtn").onclick = () =>
    go(editing ? `/admin/events/${ev.id}` : "/admin/events");

  document.getElementById("saveEventBtn").onclick = async () => {
    const val = (id) => document.getElementById(id).value;
    const body = {
      name: val("ename"),
      event_date: val("edate"),
      event_time: val("etime"),
      location: val("eplace"),
      theme: val("etheme"),
      budget_amount: val("ebudget") || null,
      rules: val("erules"),
      what_to_bring: val("ebring"),
      other_info: val("eother"),
    };
    if (!locked) {
      body.wishlist_limit = Number(val("elimit")) || 5;
      body.use_codenames = document.getElementById("ecodes").checked;
      body.allow_same_household = document.getElementById("esame").checked;
    }
    const ids = boxes().filter(c => c.checked).map(c => Number(c.dataset.uid));
    try {
      if (editing) {
        // Who's joining first, so the game master can be someone just added.
        if (!locked) await api.put(`/events/${ev.id}/participants`, { user_ids: ids });
        body.game_master_id = gmValue ? Number(gmValue) : null;
        await api.patch(`/events/${ev.id}`, body);
        await refreshCurrentEvent();
        return go(`/admin/events/${ev.id}`);
      }
      const r = await api.post(`/families/${FAMILY.id}/events`, body);
      const newId = r.event.id;
      try {
        await api.put(`/events/${newId}/participants`, { user_ids: ids });
        if (gmValue) await api.patch(`/events/${newId}`, { game_master_id: Number(gmValue) });
      } catch (e) {
        await refreshCurrentEvent();
        window.alert(`The gift exchange was created, but saving who's joining (or the game master) failed: ${e.message}`);
        return go(`/admin/events/${newId}/edit`);
      }
      await refreshCurrentEvent();
      go(`/admin/events/${newId}`);
    } catch (e) { showError(e); }
  };
}

function eventFormBlocked(id, msg) {
  render("Edit Gift Exchange", alertBox(msg) + `
    <button class="btn btn-secondary" style="width:auto" onclick="go('/admin/events/${id}')">Back to Gift Exchange</button>`,
    { wide: true });
}

route(/^\/admin\/events\/new$/, async () => { await renderEventForm(null); });

route(/^\/admin\/events\/(\d+)\/edit$/, async (id) => {
  const ev = await api.get(`/events/${id}`);
  if (ev.status === "completed") {
    return eventFormBlocked(id, "This gift exchange is archived and can't be edited.");
  }
  await renderEventForm(ev);
});

route(/^\/admin\/events\/(\d+)$/, async (id) => {
  const [ev, parts, st] = await Promise.all([
    api.get(`/events/${id}`),
    api.get(`/events/${id}/participants`),
    api.get(`/events/${id}/assignments/status`),
  ]);
  const status = eventStatus(ev);
  const joining = parts.filter(p => p.is_participating)
    .sort((x, y) => x.user.display_name.localeCompare(y.user.display_name));
  const people = joining.length
    ? `<ul class="people-list">${joining.map(p => `<li>${esc(p.user.display_name)}
        <span class="muted">${p.household_name ? "• " + esc(p.household_name) : "• ⚠ no household yet"}</span></li>`).join("")}</ul>`
    : `<p class="muted">No one is joining yet.${ev.status === "open" ? " Use Edit to choose who's in." : ""}</p>`;
  const drawSection = ev.status === "completed"
    ? `<div class="alert alert-ok">📦 This gift exchange is archived. Everyone can look at it, but nothing in it can be changed.</div>`
    : ev.status === "matched"
      ? `<div class="alert alert-ok">✅ Names are drawn! ${st.revealed} of ${st.matched} people have peeked.</div>
         <button class="btn btn-quiet" id="reroll">Start Over (Re-Draw Names)</button>`
      : `<button class="btn btn-primary" id="draw">🎲 Draw Names</button>`;
  const doneBtn = ev.status !== "completed"
    ? `<button class="btn btn-quiet" id="markDone">Archive Gift Exchange</button>` : "";
  const deleteBtn = `<button class="btn btn-quiet" id="deleteEvent">Delete Gift Exchange</button>`;
  render(ev.name, `
    <div id="msg"></div>
    <div class="card">
    <p><span class="status-tag ${status.cls}">${status.emoji} ${status.label}</span>
      <span class="muted">&nbsp;${esc(fmtEventDate(ev.event_date))}
      ${ev.budget_amount ? ` • Budget ${esc(ev.budget_currency)} ${ev.budget_amount}` : ""}
      • Up to ${ev.wishlist_limit} gifts each</span></p>
    <div class="form-actions" style="margin-bottom:.5rem">
      ${ev.status !== "completed" ? `<button class="btn btn-secondary" id="editEvent">Edit Gift Exchange</button>` : ""}
      <button class="btn btn-quiet" onclick="go('/events/${id}')">See Event Page</button>
    </div>
    <h2 style="margin-top:1.25rem">Who's joining (${joining.length})</h2>
    ${people}
    </div>
    <div class="card">
    ${drawSection}
    ${doneBtn}
    <button class="btn btn-quiet" onclick="go('/admin/events/${id}/wishlists')">View Everyone's Wishlists</button>
    ${deleteBtn}
    </div>
  `, { wide: true });
  const editBtn = document.getElementById("editEvent");
  if (editBtn) editBtn.onclick = () => go(`/admin/events/${id}/edit`);
  const draw = document.getElementById("draw");
  if (draw) draw.onclick = async () => {
    try {
      const r = await api.post(`/events/${id}/assignments/generate`);
      document.getElementById("msg").innerHTML = alertBox(`🎉 Done! ${r.matched} people matched.`, true);
      setTimeout(navigate, 1200);
    } catch (e) { showError(e); }
  };
  const rr = document.getElementById("reroll");
  if (rr) rr.onclick = async () => {
    if (confirm("This erases everyone's matches so you can draw again. Continue?")) {
      await api.del(`/events/${id}/assignments`); navigate();
    }
  };
  const deleteBtnEl = document.getElementById("deleteEvent");
  if (deleteBtnEl) deleteBtnEl.onclick = () => deleteEvent(ev, () => go("/admin/events"));
  const markDone = document.getElementById("markDone");
  if (markDone) markDone.onclick = async () => {
    if (!confirm("Archive this gift exchange? Everyone can still look at its messages, wishlists and dishes, but no one will be able to send messages, change wishlists, add dishes or edit it anymore. This can't be undone.")) return;
    try {
      await api.post(`/events/${id}/complete`);
      await refreshCurrentEvent();
      navigate();
    } catch (e) { showError(e); }
  };
});

route(/^\/admin\/events\/(\d+)\/wishlists$/, async (id) => {
  const [all, ev] = await Promise.all([api.get(`/events/${id}/wishlists`), api.get(`/events/${id}`)]);
  const archived = ev.status === "completed";
  all.sort((a, b) => a.user.display_name.localeCompare(b.user.display_name));
  const people = all.map(w => `
    <section class="person-section">
      <div class="person-head">
        ${avatarHtml(w.user, "avatar-md")}
        <h2 style="margin:0">${esc(w.user.display_name)}</h2>
      </div>
      ${w.items.length ? clanWishGrid(w.items, archived) : `<div class="card"><p class="muted" style="margin:0">No gift ideas yet.</p></div>`}
    </section>`).join("");
  render("All Wishlists", all.length
    ? (archived ? archivedBanner() : "") + people
    : `<div class="card"><p class="muted" style="margin:0">No one's joined this gift exchange yet.</p></div>`, { wide: true });
  wireBuyButtons();
});

route(/^\/admin\/announce$/, async () => {
  const anns = await api.get(`/families/${FAMILY.id}/announcements?scope=all`);

  function annRow(a) {
    const tr = h(`<tr>
      <td data-label="Title"><input data-title value="${esc(a.title)}"></td>
      <td data-label="Message"><textarea data-body rows="2">${esc(a.body)}</textarea></td>
      <td data-label="Show on Dashboard"><input type="checkbox" data-published ${a.is_published ? "checked" : ""} aria-label="Show on Clan Dashboard"></td>
      <td class="table-actions">
        <button class="btn btn-secondary" data-save>Save</button>
        <button class="btn btn-quiet" data-del>Delete</button>
      </td>
    </tr>`).firstElementChild;
    tr.querySelector("[data-save]").onclick = async () => {
      try {
        await api.patch(`/announcements/${a.id}`, {
          title: tr.querySelector("[data-title]").value,
          body: tr.querySelector("[data-body]").value,
          is_published: tr.querySelector("[data-published]").checked,
        });
        document.getElementById("msg").innerHTML = alertBox("Saved!", true);
      } catch (e) { showError(e); }
    };
    tr.querySelector("[data-del]").onclick = async () => {
      if (!confirm("Delete this announcement?")) return;
      try {
        await api.del(`/announcements/${a.id}`);
        tr.remove();
      } catch (e) { showError(e); }
    };
    return tr;
  }

  render("Announcements", `
    <div id="msg"></div>
    <h2 class="section-title">Existing announcements</h2>
    ${anns.length ? `
      <div class="table-wrap">
        <table class="data" id="annTable">
          <colgroup>
            <col style="width:22%"><col style="width:42%"><col style="width:14%"><col style="width:22%">
          </colgroup>
          <thead><tr><th>Title</th><th>Message</th><th>Show on Dashboard</th><th></th></tr></thead>
          <tbody></tbody>
        </table>
      </div>` : `<div class="card"><p class="muted" style="margin:0">No announcements yet.</p></div>`}
    <section class="card form-card" style="margin-top:1.25rem">
    <h2>Post a new announcement</h2>
    <label>Title</label><input id="atitle">
    <label>Message</label><textarea id="abody" rows="4"></textarea>
    <div class="check-row"><input type="checkbox" id="apub" checked><label for="apub" style="margin:0">Show on Clan Dashboard</label></div>
    <button class="btn btn-primary" id="postBtn">Post to the Family</button>
    </section>
  `, { wide: true });

  const tbody = document.querySelector("#annTable tbody");
  if (tbody) anns.forEach(a => tbody.append(annRow(a)));

  document.getElementById("postBtn").onclick = async () => {
    try {
      await api.post(`/families/${FAMILY.id}/announcements`, {
        title: document.getElementById("atitle").value,
        body: document.getElementById("abody").value,
        is_published: document.getElementById("apub").checked,
      });
      go("/");
    } catch (e) { showError(e); }
  };
});

window.go = go;
boot();
