/* Secret Santa SPA — hash router + pages. No frameworks, no build step. */

const $app = document.getElementById("app");
const $title = document.getElementById("pageTitle");
const $back = document.getElementById("backBtn");
const $topbar = document.getElementById("topbar");
const $bell = document.getElementById("bellBtn");
const $badge = document.getElementById("bellBadge");
const $sidebar = document.getElementById("sidebar");
const $sidebarOverlay = document.getElementById("sidebarOverlay");
const $menuBtn = document.getElementById("menuBtn");

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
function h(html) { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content; }
function render(title, html, { back = true, wide = false } = {}) {
  $title.textContent = title;
  $back.hidden = !back;
  $app.classList.toggle("wide", wide);
  $app.innerHTML = "";
  $app.append(typeof html === "string" ? h(html) : html);
  window.scrollTo(0, 0);
}

const NAV = [
  { key: "dashboard", label: "My Dashboard", href: "/" },
  { key: "wishlist", label: "My Wishlist", eventPath: "wishlist" },
  { key: "messages", label: "My Messages", eventPath: "messages/giver", children: [
    { key: "messages-giver", eventPath: "messages/giver", label: "Message to my Secret Santa" },
    { key: "messages-giftee", eventPath: "messages/giftee", label: "Message to my Giftee" },
  ] },
  { key: "admin", label: "Manage Family", href: "/admin", adminOnly: true, children: [
    { key: "members", href: "/admin/members", label: "Members" },
    { key: "groups", href: "/admin/groups", label: "Family Groups" },
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
function openSidebar() { $sidebar.classList.add("open"); $sidebarOverlay.classList.add("open"); }
function closeSidebar() { $sidebar.classList.remove("open"); $sidebarOverlay.classList.remove("open"); }
function alertBox(msg, ok = false) {
  return `<div class="alert ${ok ? "alert-ok" : "alert-error"}" role="alert">${esc(msg)}</div>`;
}
function showError(e) {
  const el = document.getElementById("msg");
  if (el) el.innerHTML = alertBox(e.message);
  else window.alert(e.message);
}
function go(hash) { location.hash = hash; }

function wishItemRow(item, { showBuy = false, showDelete = false } = {}) {
  const thumb = item.photo_url
    ? `<img src="${esc(item.photo_url)}" alt="" class="wish-thumb">`
    : `<div class="wish-thumb wish-thumb-empty">🎁</div>`;
  const meta = [
    item.description ? esc(item.description) : "",
    item.link_url ? `<a href="${esc(item.link_url)}" target="_blank" rel="noopener">See it online</a>` : "",
  ].filter(Boolean).join(" · ");
  let action = "";
  if (showBuy) {
    action = `<button class="btn ${item.is_purchased ? "btn-quiet" : "btn-green"}" style="width:auto" data-buy="${item.id}">${item.is_purchased ? "Undo" : "I Bought This"}</button>`;
  } else if (showDelete) {
    action = `<button class="icon-btn" aria-label="Remove ${esc(item.item_name)}" data-del="${item.id}">🗑</button>`;
  }
  return `
    <div class="wish-row ${item.is_purchased ? "bought" : ""}">
      ${thumb}
      <div class="wish-info">
        <strong>${esc(item.item_name)}</strong>
        <span class="wish-priority">P${item.priority}</span>
        ${meta ? `<div class="muted wish-meta">${meta}</div>` : ""}
        ${item.is_purchased ? `<span class="tag-bought">✓ Bought</span>` : ""}
      </div>
      ${action}
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
  renderSidebar(path);
  closeSidebar();
  for (const r of routes) {
    const m = path.match(r.pattern);
    if (m) { try { await r.fn(...m.slice(1)); } catch (e) { render("Oops", alertBox(e.message)); } return; }
  }
  go("/");
}
window.addEventListener("hashchange", navigate);
$back.onclick = () => history.back();
$bell.onclick = () => go("/notifications");
$menuBtn.onclick = () => { $sidebar.classList.contains("open") ? closeSidebar() : openSidebar(); };
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
    refreshBadge();
    navigate();
  } catch (_) {
    $topbar.hidden = true;
    $sidebar.hidden = true;
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
    <input id="password" type="password" autocomplete="current-password">
    <div id="msg"></div>
    <button class="btn btn-primary" id="loginBtn">Sign In</button>
  `, { back: false });
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
  `, { back: false });
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
  `, { back: true });
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
  `, { back: false });
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
  `, { back: false });
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
    <button class="btn btn-primary" id="setPwBtn">Save Password</button>
  `, { back: false });
  document.getElementById("setPwBtn").onclick = async () => {
    try {
      await api.patch("/auth/security", { password: document.getElementById("newPw").value });
      boot();
    } catch (e) { showError(e); }
  };
}

function pageSecuritySetup(forced) {
  render("Profile & Security", `
    <h2>Your name</h2>
    <p class="muted">This is how your family will see you.</p>
    <label for="displayName">Your name</label>
    <input id="displayName" value="${esc(ME.user.full_name)}">
    <div id="nameMsg"></div>
    <button class="btn btn-secondary" id="saveNameBtn">Save Name</button>

    <hr style="margin:2rem 0">
    <h2>Set up your password</h2>
    <p class="muted">You'll use this to sign in. At least 8 characters.</p>
    <label for="newPassword">Password</label>
    <input id="newPassword" type="password" autocomplete="new-password">
    <div id="pwMsg"></div>
    <button class="btn btn-primary" id="savePwBtn">Save Password</button>

    <hr style="margin:2rem 0">
    <h2>Add a phone number (optional)</h2>
    <p class="muted">Get a text with a 6-digit code instead of typing your password.</p>
    <label for="secPhone">Phone number</label>
    <input id="secPhone" type="tel" inputmode="tel" autocomplete="tel" placeholder="(555) 123-4567">
    <div class="check-row" style="align-items:flex-start;margin-top:1rem">
      <input type="checkbox" id="smsConsent" style="margin-top:.3rem">
      <label for="smsConsent" style="margin:0;font-size:.85rem;font-weight:400">
        By checking this box, I agree to receive SMS messages from Genri Labs for account authentication,
        including one-time passwords (OTP) used to verify my identity when signing in. Message frequency
        varies based on sign-in activity. Message and data rates may apply. Reply STOP to opt out and
        HELP for assistance. View our
        <a href="/privacy_terms#privacy" target="_blank" rel="noopener">Privacy Policy</a>
        and <a href="/privacy_terms#terms" target="_blank" rel="noopener">Terms of Service</a>.
      </label>
    </div>
    <div id="phoneMsg"></div>
    <button class="btn btn-secondary" id="savePhoneBtn">Save Phone Number</button>
    ${!forced ? `<button class="btn btn-quiet" id="doneBtn">Done</button>` : ""}
  `, { back: !forced });
  document.getElementById("saveNameBtn").onclick = async () => {
    try {
      const r = await api.patch("/auth/me", { full_name: document.getElementById("displayName").value });
      ME.user = r.user;
      document.getElementById("nameMsg").innerHTML = alertBox("Name saved!", true);
    } catch (e) {
      document.getElementById("nameMsg").innerHTML = alertBox(e.message);
    }
  };
  document.getElementById("savePwBtn").onclick = async () => {
    const password = document.getElementById("newPassword").value;
    try {
      await api.patch("/auth/security", { password });
      document.getElementById("pwMsg").innerHTML = alertBox("Password saved!", true);
      if (forced) boot();
    } catch (e) {
      const el = document.getElementById("pwMsg");
      el.innerHTML = alertBox(e.message);
    }
  };
  document.getElementById("savePhoneBtn").onclick = async () => {
    if (!document.getElementById("smsConsent").checked) {
      document.getElementById("phoneMsg").innerHTML =
        alertBox("Please check the box to agree to receive text messages before continuing.");
      return;
    }
    const phone = document.getElementById("secPhone").value.trim();
    try {
      await api.patch("/auth/security", { phone });
      document.getElementById("phoneMsg").innerHTML = alertBox("Phone number saved!", true);
    } catch (e) {
      document.getElementById("phoneMsg").innerHTML = alertBox(e.message);
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
    <input id="jcode" class="code-input" maxlength="8" placeholder="ABCD1234" style="text-transform:uppercase"
      value="${esc(PENDING_JOIN_CODE || "")}" ${hasPending ? "readonly" : ""}>
    <div id="msg"></div>
    <button class="btn btn-primary" id="joinBtn">Join Family</button>
    ${!hasPending ? `
    <hr style="margin:2rem 0">
    <p class="muted center">Or start your own clan:</p>
    <label for="fname">Clan name</label>
    <input id="fname" placeholder="e.g. The Cedeño Clan">
    <button class="btn btn-secondary" id="createBtn">Start My Clan</button>` : ""}
  `, { back: false });
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
route(/^\/$/, async () => {
  const sections = [`<h2 style="margin-top:0">Welcome, ${esc(ME.user.full_name)}!</h2>`];

  if (!CURRENT_EVENT) {
    sections.push(`
      <div class="dash-section">
        <p class="muted">No gift exchange is happening right now.${FAMILY.role === "admin" ? "" : " Check back soon!"}</p>
        ${FAMILY.role === "admin" ? `<button class="btn btn-primary" style="width:auto" onclick="go('/admin/events')">Create a Gift Exchange</button>` : ""}
      </div>`);
  } else {
    const d = await api.get(`/events/${CURRENT_EVENT.id}/assignments/mine`);
    if (!d.assigned) {
      sections.push(`
        <div class="dash-section">
          <h2>My Giftee</h2>
          <p class="muted">${esc(d.message)}</p>
        </div>`);
    } else {
      let giftItems = [];
      try {
        const gd = await api.get(`/events/${CURRENT_EVENT.id}/wishlists/giftee`);
        giftItems = gd.items;
      } catch (e) { /* names just drawn but not yet queryable — show empty state below */ }
      const budget = d.budget_amount
        ? `<p class="muted">Gift budget: <strong>${esc(d.budget_currency)} ${d.budget_amount}</strong></p>` : "";
      const itemsHtml = giftItems.length
        ? giftItems.map(i => wishItemRow(i, { showBuy: true })).join("")
        : `<p class="muted">They haven't added any gift ideas yet. Send them a friendly nudge!</p>`;
      sections.push(`
        <div class="dash-section">
          <h2>My Giftee: ${esc(d.giftee_display_name)}</h2>
          ${budget}
          ${itemsHtml}
          <button class="btn btn-secondary" style="width:auto;margin-top:.5rem" onclick="go('/events/${CURRENT_EVENT.id}/messages/giftee')">Send a Message</button>
        </div>`);
    }
  }

  const anns = await api.get(`/families/${FAMILY.id}/announcements`);
  const annHtml = anns.length
    ? anns.map(a => `
        <div class="ann-row">
          <strong>${a.is_pinned ? "📌 " : ""}${esc(a.title)}</strong>
          <p>${esc(a.body)}</p>
          <p class="muted">${esc(a.author)} • ${new Date(a.at).toLocaleDateString()}</p>
        </div>`).join("")
    : `<p class="muted">No announcements yet.</p>`;
  sections.push(`<div class="dash-section"><h2>Announcements</h2>${annHtml}</div>`);

  render("My Dashboard", sections.join(""), { back: false });
  $app.querySelectorAll("[data-buy]").forEach(b => b.onclick = async () => {
    await api.post(`/wishlists/${b.dataset.buy}/purchase`); navigate();
  });
});

route(/^\/events\/(\d+)\/my-person$/, async (id) => {
  const d = await api.get(`/events/${id}/assignments/mine`);
  if (!d.assigned) return render("My Giftee", `<div class="card center"><p>${esc(d.message)}</p></div>`);
  const budget = d.budget_amount
    ? `<p class="center muted">Gift budget: <strong>${esc(d.budget_currency)} ${d.budget_amount}</strong></p>` : "";
  render("My Giftee", `
    <p class="center" style="margin-top:2rem">You are giving a gift to…</p>
    <div class="reveal-name">🎁 ${esc(d.giftee_display_name)}</div>
    ${budget}
    <p class="center muted">Shh — it's a secret! 🤫</p>
    <button class="btn btn-primary" onclick="go('/events/${id}/giftee')">See Their Wishlist</button>
    <button class="btn btn-secondary" onclick="go('/events/${id}/messages/giftee')">Send Them a Secret Message</button>
  `);
});

route(/^\/events\/(\d+)\/wishlist$/, async (id) => {
  const d = await api.get(`/events/${id}/wishlists/mine`);
  const priorityOptions = Array.from({ length: d.limit }, (_, n) => n + 1)
    .map(n => `<option value="${n}" ${n === Math.min(3, d.limit) ? "selected" : ""}>${n}</option>`).join("");
  const items = d.items.length
    ? d.items.map(i => wishItemRow(i, { showDelete: true })).join("")
    : `<p class="muted">Your list is empty. Add your first gift idea!</p>`;
  render("My Wishlist", `
    <p class="muted">${d.items.length} of ${d.limit} gifts</p>
    <h2>Add a gift idea</h2>
    <label>What would you love?</label>
    <input id="iname" placeholder="e.g. Warm slippers, size 7">
    <label>Anything else they should know? <span class="muted">(optional)</span></label>
    <input id="idesc" placeholder="e.g. Favorite color is blue">
    <label>Link to it online <span class="muted">(optional)</span></label>
    <input id="ilink" type="url" placeholder="https://…">
    <label>Priority</label>
    <select id="ipriority">${priorityOptions}</select>
    <label>Photo <span class="muted">(optional)</span></label>
    <input id="iphoto" type="file" accept="image/*">
    <div id="msg"></div>
    <button class="btn btn-primary" id="addBtn">Add to My List</button>
    <h2 style="margin-top:1.5rem">Your gift ideas</h2>
    ${items}
  `);
  document.getElementById("addBtn").onclick = async () => {
    try {
      const fd = new FormData();
      fd.append("item_name", document.getElementById("iname").value);
      fd.append("description", document.getElementById("idesc").value);
      fd.append("link_url", document.getElementById("ilink").value);
      fd.append("priority", document.getElementById("ipriority").value);
      const photo = document.getElementById("iphoto").files[0];
      if (photo) fd.append("photo", photo);
      await api.postForm(`/events/${id}/wishlists`, fd);
      navigate();
    } catch (e) { showError(e); }
  };
  $app.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    if (confirm("Remove this gift from your list?")) { await api.del(`/wishlists/${b.dataset.del}`); navigate(); }
  });
});

route(/^\/events\/(\d+)\/giftee$/, async (id) => {
  let d;
  try { d = await api.get(`/events/${id}/wishlists/giftee`); }
  catch (e) { return render("Their Wishlist", alertBox(e.message)); }
  const items = d.items.length
    ? d.items.map(i => wishItemRow(i, { showBuy: true })).join("")
    : `<p class="muted">They haven't added any gift ideas yet. Send them a friendly nudge!</p>`;
  render("Their Wishlist", items + `
    <button class="btn btn-secondary" style="width:auto;margin-top:.5rem" onclick="go('/events/${id}/messages/giftee')">Send a Secret Message</button>`);
  $app.querySelectorAll("[data-buy]").forEach(b => b.onclick = async () => {
    await api.post(`/wishlists/${b.dataset.buy}/purchase`); navigate();
  });
});

route(/^\/events\/(\d+)\/messages$/, async (id) => {
  const d = await api.get(`/events/${id}/messages`);
  function thread(key, label) {
    const t = d[key];
    if (!t) return "";
    const msgs = t.messages.map(m =>
      `<div class="bubble ${m.mine ? "mine" : "theirs"}">${esc(m.body)}</div>`).join("")
      || `<p class="muted center">No messages yet. Say hello!</p>`;
    return `<h2>${label}: ${esc(t.with_display_name)}</h2>
      <div>${msgs}</div>
      <label for="in-${key}">Write a message</label>
      <input id="in-${key}" maxlength="2000" placeholder="Type here…">
      <button class="btn btn-primary" data-send="${key}">Send</button><hr style="margin:2rem 0">`;
  }
  render("Messages", `
    <div id="msg"></div>
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
  const d = await api.get(`/events/${id}/messages`);
  const t = d[key];
  if (!t) {
    render(label, `<div class="card center"><p>Messages open up after names are drawn.</p></div>`);
    return;
  }
  const msgs = t.messages.map(m =>
    `<div class="bubble ${m.mine ? "mine" : "theirs"}">${esc(m.body)}</div>`).join("")
    || `<p class="muted center">No messages yet. Say hello!</p>`;
  render(label, `
    <div id="msg"></div>
    <h2>${esc(t.with_display_name)}</h2>
    <div>${msgs}</div>
    <label for="msgin">Write a message</label>
    <input id="msgin" maxlength="2000" placeholder="Type here…">
    <button class="btn btn-primary" id="sendBtn">Send</button>
  `);
  document.getElementById("sendBtn").onclick = async () => {
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
  const list = anns.map(a => `
    <div class="card ann">
      <strong>${a.is_pinned ? "📌 " : ""}${esc(a.title)}</strong>
      <p>${esc(a.body)}</p>
      <p class="muted">${esc(a.author)} • ${new Date(a.at).toLocaleDateString()}</p>
    </div>`).join("") || `<div class="card center"><p>No announcements yet.</p></div>`;
  render("Announcements", list);
});

route(/^\/notifications$/, async () => {
  const d = await api.get("/notifications");
  const list = d.items.map(n => `
    <div class="card" style="${n.is_read ? "opacity:.65" : ""}">
      <strong>${esc(n.title)}</strong>
      ${n.body ? `<p>${esc(n.body)}</p>` : ""}
      <p class="muted">${new Date(n.at).toLocaleString()}</p>
    </div>`).join("") || `<div class="card center"><p>Nothing here yet.</p></div>`;
  render("Notifications", `
    ${d.unread ? `<button class="btn btn-quiet" id="readAll">Mark All as Read</button>` : ""}
    ${list}`);
  const ra = document.getElementById("readAll");
  if (ra) ra.onclick = async () => { await api.post("/notifications/read-all"); refreshBadge(); navigate(); };
  refreshBadge();
});

// ---------- admin ----------
route(/^\/admin$/, async () => {
  const fam = await api.get(`/families/${FAMILY.id}`);
  const regUrl = `${location.origin}/#/join/${fam.join_code}`;
  render("Clan Admin Dashboard", `
    <h2>Clan name</h2>
    <label for="clanName">Name</label>
    <input id="clanName" value="${esc(fam.name)}">
    <div id="nameMsg"></div>
    <button class="btn btn-secondary" id="saveClanName">Save Clan Name</button>

    <div class="card center" style="margin-top:1.5rem">
      <p class="muted">Share this code so family can join:</p>
      <div class="reveal-name" style="font-size:1.8rem">${esc(fam.join_code)}</div>
      <button class="btn btn-quiet" id="copyLinkBtn" style="margin-top:.5rem">Copy Registration Link</button>
      <div id="copyMsg"></div>
    </div>
  `, { back: false, wide: true });
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
      <td data-label="Phone"><input data-phone value="${esc(m.user.phone || "")}" placeholder="(555) 123-4567" title="${esc(m.user.phone || "")}"></td>
      <td data-label="Email"><input data-email value="${esc(m.user.email || "")}" placeholder="name@example.com" title="${esc(m.user.email || "")}"></td>
      <td data-label="Family Group"><select data-house>${houseOpts(m.household_id)}</select></td>
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
          <th>Name</th><th>Phone</th><th>Email</th><th>Family Group</th>
          <th>Admin</th><th>Joining${current ? ` (${esc(current.name)})` : ""}</th><th></th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>

    <h2>Add a member</h2>
    <p class="muted">Adds their account directly — you'll get a username and password to give them.</p>
    <label for="newName">Name</label>
    <input id="newName">
    <label for="newPhone">Phone number (optional)</label>
    <input id="newPhone" type="tel" inputmode="tel" placeholder="(555) 123-4567">
    <label for="newEmail">Email (optional)</label>
    <input id="newEmail" type="email" placeholder="name@example.com">
    ${current ? `
    <div class="check-row">
      <input type="checkbox" id="newJoining">
      <label for="newJoining" style="margin:0">Joining ${esc(current.name)} this year</label>
    </div>` : ""}
    <div id="addMsg"></div>
    <button class="btn btn-primary" id="addMemberBtn">Add Member</button>
  `, { back: false, wide: true });
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
      <td data-label="Group Name"><input data-name value="${esc(hh.name)}"></td>
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

  render("Family Groups", `
    <p class="muted">People in the same family group won't draw each other's names.</p>
    <div id="msg"></div>
    <div class="table-wrap">
      <table class="data" id="groupsTable">
        <colgroup><col style="width:70%"><col style="width:30%"></colgroup>
        <thead><tr><th>Group Name</th><th></th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <p class="muted center" id="noGroups">No family groups yet.</p>
    <h2>Add a family group</h2>
    <label>Group name</label>
    <input id="hname">
    <button class="btn btn-primary" id="addHouse">Add Family Group</button>
  `, { back: false, wide: true });
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

route(/^\/admin\/events$/, async () => {
  const events = await api.get(`/families/${FAMILY.id}/events`);
  const list = events.map(e => `
    <button class="card-btn" onclick="go('/admin/events/${e.id}')">
      <span class="emoji">${e.status === "matched" ? "✅" : "🎄"}</span>
      <span>${esc(e.name)}<span class="sub">${esc(e.event_date)} • ${e.status === "matched" ? "Names drawn" : "Not drawn yet"}</span></span>
    </button>`).join("");
  render("Gift Exchanges", `
    ${list}
    <h2>Create a new exchange</h2>
    <label>Name</label><input id="ename" placeholder="e.g. Christmas 2026">
    <label>Date of the exchange</label><input id="edate" type="date">
    <label>Gift budget (optional)</label><input id="ebudget" type="number" inputmode="decimal" placeholder="e.g. 30">
    <label>Wishlist size</label><input id="elimit" type="number" value="5" min="1" max="20">
    <div class="check-row"><input type="checkbox" id="ecodes"><label for="ecodes" style="margin:0">Use fun codenames instead of real names</label></div>
    <div class="check-row"><input type="checkbox" id="esame"><label for="esame" style="margin:0">Allow matches within the same household</label></div>
    <div id="msg"></div>
    <button class="btn btn-primary" id="createEv">Create Exchange</button>
  `, { back: false, wide: true });
  document.getElementById("createEv").onclick = async () => {
    try {
      await api.post(`/families/${FAMILY.id}/events`, {
        name: document.getElementById("ename").value,
        event_date: document.getElementById("edate").value,
        budget_amount: document.getElementById("ebudget").value || null,
        wishlist_limit: document.getElementById("elimit").value,
        use_codenames: document.getElementById("ecodes").checked,
        allow_same_household: document.getElementById("esame").checked,
      });
      await refreshCurrentEvent();
      navigate();
    } catch (e) { showError(e); }
  };
});

route(/^\/admin\/events\/(\d+)$/, async (id) => {
  const [ev, parts, st] = await Promise.all([
    api.get(`/events/${id}`),
    api.get(`/events/${id}/participants`),
    api.get(`/events/${id}/assignments/status`),
  ]);
  const rows = parts.map(p => `
    <label class="check-row">
      <input type="checkbox" data-uid="${p.user.id}" ${p.is_participating ? "checked" : ""}
        ${ev.status === "matched" ? "disabled" : ""}>
      <span>${esc(p.user.display_name)}
        <span class="muted">${p.household_name ? "• " + esc(p.household_name) : "• ⚠ no household yet"}</span></span>
    </label>`).join("");
  const drawSection = ev.status === "matched"
    ? `<div class="alert alert-ok">✅ Names are drawn! ${st.revealed} of ${st.matched} people have peeked.</div>
       <button class="btn btn-quiet" id="reroll">Start Over (Re-Draw Names)</button>`
    : `<button class="btn btn-primary" id="draw">🎲 Draw Names</button>`;
  render(ev.name, `
    <div id="msg"></div>
    <h2>Who's joining?</h2>
    ${rows}
    ${ev.status !== "matched" ? `<button class="btn btn-secondary" id="saveParts">Save Participants</button>` : ""}
    <hr style="margin:1.5rem 0">
    ${drawSection}
    <button class="btn btn-quiet" onclick="go('/admin/events/${id}/wishlists')">View Everyone's Wishlists</button>
  `, { back: true, wide: true });
  const save = document.getElementById("saveParts");
  if (save) save.onclick = async () => {
    const ids = [...$app.querySelectorAll("[data-uid]:checked")].map(c => Number(c.dataset.uid));
    try { await api.put(`/events/${id}/participants`, { user_ids: ids });
      document.getElementById("msg").innerHTML = alertBox("Participants saved!", true);
    } catch (e) { showError(e); }
  };
  const draw = document.getElementById("draw");
  if (draw) draw.onclick = async () => {
    try {
      const ids = [...$app.querySelectorAll("[data-uid]:checked")].map(c => Number(c.dataset.uid));
      await api.put(`/events/${id}/participants`, { user_ids: ids });
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
});

route(/^\/admin\/events\/(\d+)\/wishlists$/, async (id) => {
  const all = await api.get(`/events/${id}/wishlists`);
  const list = all.map(w => `
    <div class="card">
      <strong>${esc(w.user.display_name)}</strong>
      ${w.items.length
        ? "<ul>" + w.items.map(i => `<li>${esc(i.item_name)}</li>`).join("") + "</ul>"
        : `<p class="muted">No gift ideas yet.</p>`}
    </div>`).join("");
  render("All Wishlists", list, { back: true, wide: true });
});

route(/^\/admin\/announce$/, async () => {
  render("Post Announcement", `
    <label>Title</label><input id="atitle" placeholder="e.g. Party is at 6pm!">
    <label>Message</label><textarea id="abody" rows="4"></textarea>
    <div class="check-row"><input type="checkbox" id="apin"><label for="apin" style="margin:0">Pin to the top</label></div>
    <div id="msg"></div>
    <button class="btn btn-primary" id="postBtn">Post to the Family</button>
  `, { back: false, wide: true });
  document.getElementById("postBtn").onclick = async () => {
    try {
      await api.post(`/families/${FAMILY.id}/announcements`, {
        title: document.getElementById("atitle").value,
        body: document.getElementById("abody").value,
        is_pinned: document.getElementById("apin").checked,
      });
      go("/announcements");
    } catch (e) { showError(e); }
  };
});

window.go = go;
boot();
