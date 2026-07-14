/* Secret Santa SPA — hash router + pages. No frameworks, no build step. */

const $app = document.getElementById("app");
const $title = document.getElementById("pageTitle");
const $back = document.getElementById("backBtn");
const $topbar = document.getElementById("topbar");
const $bell = document.getElementById("bellBtn");
const $badge = document.getElementById("bellBadge");

let ME = null;          // { user, families }
let FAMILY = null;      // active family {id, name, role}

// ---------- helpers ----------
function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}
function h(html) { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content; }
function render(title, html, { back = true } = {}) {
  $title.textContent = title;
  $back.hidden = !back;
  $app.innerHTML = "";
  $app.append(typeof html === "string" ? h(html) : html);
  window.scrollTo(0, 0);
}
function alertBox(msg, ok = false) {
  return `<div class="alert ${ok ? "alert-ok" : "alert-error"}" role="alert">${esc(msg)}</div>`;
}
function showError(e) {
  const el = document.getElementById("msg");
  if (el) el.innerHTML = alertBox(e.message);
  else window.alert(e.message);
}
function go(hash) { location.hash = hash; }

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
  for (const r of routes) {
    const m = path.match(r.pattern);
    if (m) { try { await r.fn(...m.slice(1)); } catch (e) { render("Oops", alertBox(e.message)); } return; }
  }
  go("/");
}
window.addEventListener("hashchange", navigate);
$back.onclick = () => history.back();
$bell.onclick = () => go("/notifications");

// ---------- boot ----------
async function boot() {
  try {
    ME = await api.get("/auth/me");
    $topbar.hidden = false;
    if (!ME.user.full_name) return pageName();
    if (ME.families.length === 0) return pageNoFamily();
    FAMILY = ME.families[0];
    refreshBadge();
    navigate();
  } catch (_) {
    $topbar.hidden = true;
    pageLogin();
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
    <div class="steps">Step 1 of 2</div>
    <label for="phone">Your phone number</label>
    <input id="phone" type="tel" inputmode="tel" autocomplete="tel" placeholder="(555) 123-4567">
    <div class="check-row" style="align-items:flex-start;margin-top:1rem">
      <input type="checkbox" id="smsConsent" style="margin-top:.3rem">
      <label for="smsConsent" style="margin:0;font-size:.85rem;font-weight:400">
        By checking this box, I agree to receive SMS messages from Genri Labs regarding my Secret Santa account,
        including one-time passwords (OTP) and account notifications. Message frequency varies.
        Message and data rates may apply. Reply STOP to unsubscribe and HELP for assistance.
        View our <a href="/privacy_terms#privacy" target="_blank" rel="noopener">Privacy Policy</a>
        and <a href="/privacy_terms#terms" target="_blank" rel="noopener">Terms of Service</a>.
      </label>
    </div>
    <div id="msg"></div>
    <button class="btn btn-primary" id="sendBtn">Text Me a Sign-In Code</button>
  `, { back: false });
  document.getElementById("sendBtn").onclick = async () => {
    const phone = document.getElementById("phone").value.trim();
    if (!document.getElementById("smsConsent").checked) {
      document.getElementById("msg").innerHTML =
        alertBox("Please check the box to agree to receive text messages before continuing.");
      return;
    }
    try {
      await api.post("/auth/request-otp", { phone });
      pageCode(phone);
    } catch (e) { showError(e); }
  };
}

function pageCode(phone) {
  render("", `
    <div class="steps">Step 2 of 2</div>
    <h2 class="center">Check your phone</h2>
    <p class="center">We sent a 6-digit code by text to<br><strong>${esc(phone)}</strong></p>
    <label for="code">Type the code here</label>
    <input id="code" class="code-input" inputmode="numeric" maxlength="6" autocomplete="one-time-code">
    <div id="msg"></div>
    <button class="btn btn-primary" id="verifyBtn">Sign In</button>
    <button class="btn btn-quiet" id="againBtn">Send a New Code</button>
  `, { back: false });
  document.getElementById("verifyBtn").onclick = async () => {
    try {
      await api.post("/auth/verify-otp", { phone, code: document.getElementById("code").value });
      location.hash = "/"; boot();
    } catch (e) { showError(e); }
  };
  document.getElementById("againBtn").onclick = async () => {
    try { await api.post("/auth/request-otp", { phone });
      document.getElementById("msg").innerHTML = alertBox("New code sent!", true);
    } catch (e) { showError(e); }
  };
}

function pageName() {
  render("Welcome!", `
    <h2>What's your name?</h2>
    <p class="muted">This is how your family will see you.</p>
    <label for="name">Your name</label>
    <input id="name" autocomplete="name" placeholder="e.g. Lola Nena">
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

function pageNoFamily() {
  render("Secret Santa", `
    <h2>Join your family</h2>
    <p class="muted">Ask your family organizer for the family code.</p>
    <label for="jcode">Family code</label>
    <input id="jcode" class="code-input" maxlength="8" placeholder="ABCD1234" style="text-transform:uppercase">
    <div id="msg"></div>
    <button class="btn btn-primary" id="joinBtn">Join Family</button>
    ${ME.can_create_family ? `
    <hr style="margin:2rem 0">
    <p class="muted center">Or start a brand-new family group:</p>
    <label for="fname">Family name</label>
    <input id="fname" placeholder="e.g. The Cedeño Family">
    <button class="btn btn-secondary" id="createBtn">Create a Family</button>` : ""}
  `, { back: false });
  document.getElementById("joinBtn").onclick = async () => {
    try { await api.post("/families/join", { join_code: document.getElementById("jcode").value }); boot(); }
    catch (e) { showError(e); }
  };
  const createBtn = document.getElementById("createBtn");
  if (createBtn) createBtn.onclick = async () => {
    try { await api.post("/families", { name: document.getElementById("fname").value }); boot(); }
    catch (e) { showError(e); }
  };
}

// ---------- main pages ----------
route(/^\/$/, async () => {
  const events = await api.get(`/families/${FAMILY.id}/events`);
  const current = events.find(e => e.status !== "completed" && e.status !== "cancelled");
  let cards = "";
  if (current) {
    cards += `
      <button class="card-btn" onclick="go('/events/${current.id}/my-person')">
        <span class="emoji">🎅</span><span>See My Person<span class="sub">${esc(current.name)}</span></span></button>
      <button class="card-btn" onclick="go('/events/${current.id}/wishlist')">
        <span class="emoji">📝</span><span>My Wishlist<span class="sub">Tell your Santa what you'd love</span></span></button>
      <button class="card-btn" onclick="go('/events/${current.id}/giftee')">
        <span class="emoji">🎁</span><span>My Person's Wishlist<span class="sub">See their gift ideas</span></span></button>
      <button class="card-btn" onclick="go('/events/${current.id}/messages')">
        <span class="emoji">💌</span><span>Messages<span class="sub">Chat without spoiling the surprise</span></span></button>`;
  } else {
    cards += `<div class="card center"><p>No gift exchange is happening right now.</p></div>`;
  }
  cards += `
    <button class="card-btn" onclick="go('/announcements')">
      <span class="emoji">📢</span><span>Announcements</span></button>`;
  if (FAMILY.role === "admin") {
    cards += `<button class="card-btn" onclick="go('/admin')">
      <span class="emoji">⚙️</span><span>Manage Family<span class="sub">Members, households & events</span></span></button>`;
  }
  cards += `<button class="btn btn-quiet" id="logoutBtn" style="margin-top:2rem">Sign Out</button>`;
  render(FAMILY.name, cards, { back: false });
  document.getElementById("logoutBtn").onclick = async () => { await api.post("/auth/logout"); location.reload(); };
});

route(/^\/events\/(\d+)\/my-person$/, async (id) => {
  const d = await api.get(`/events/${id}/assignments/mine`);
  if (!d.assigned) return render("My Person", `<div class="card center"><p>${esc(d.message)}</p></div>`);
  const budget = d.budget_amount
    ? `<p class="center muted">Gift budget: <strong>${esc(d.budget_currency)} ${d.budget_amount}</strong></p>` : "";
  render("My Person", `
    <p class="center" style="margin-top:2rem">You are giving a gift to…</p>
    <div class="reveal-name">🎁 ${esc(d.giftee_display_name)}</div>
    ${budget}
    <p class="center muted">Shh — it's a secret! 🤫</p>
    <button class="btn btn-primary" onclick="go('/events/${id}/giftee')">See Their Wishlist</button>
    <button class="btn btn-secondary" onclick="go('/events/${id}/messages')">Send Them a Secret Message</button>
  `);
});

route(/^\/events\/(\d+)\/wishlist$/, async (id) => {
  const d = await api.get(`/events/${id}/wishlists/mine`);
  const items = d.items.map(i => `
    <div class="card wish">
      <span class="name"><strong>${esc(i.item_name)}</strong>
        ${i.description ? `<br><span class="muted">${esc(i.description)}</span>` : ""}
        ${i.link_url ? `<br><a href="${esc(i.link_url)}" target="_blank" rel="noopener">See it online</a>` : ""}
      </span>
      <button class="icon-btn" aria-label="Remove ${esc(i.item_name)}" data-del="${i.id}">🗑</button>
    </div>`).join("") || `<div class="card center"><p>Your list is empty. Add your first gift idea!</p></div>`;
  render("My Wishlist", `
    <p class="muted center">${d.items.length} of ${d.limit} gifts</p>
    ${items}
    <h2>Add a gift idea</h2>
    <label>What would you love?</label>
    <input id="iname" placeholder="e.g. Warm slippers, size 7">
    <label>Anything else they should know? <span class="muted">(optional)</span></label>
    <input id="idesc" placeholder="e.g. Favorite color is blue">
    <label>Link to it online <span class="muted">(optional)</span></label>
    <input id="ilink" type="url" placeholder="https://…">
    <div id="msg"></div>
    <button class="btn btn-primary" id="addBtn">Add to My List</button>
  `);
  document.getElementById("addBtn").onclick = async () => {
    try {
      await api.post(`/events/${id}/wishlists`, {
        item_name: document.getElementById("iname").value,
        description: document.getElementById("idesc").value,
        link_url: document.getElementById("ilink").value,
      });
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
  const items = d.items.map(i => `
    <div class="card wish ${i.is_purchased ? "bought" : ""}">
      <span class="name"><strong>${esc(i.item_name)}</strong>
        ${i.description ? `<br><span class="muted">${esc(i.description)}</span>` : ""}
        ${i.link_url ? `<br><a href="${esc(i.link_url)}" target="_blank" rel="noopener">See it online</a>` : ""}
        ${i.is_purchased ? `<br><span class="tag-bought">✓ Bought</span>` : ""}
      </span>
      <button class="btn ${i.is_purchased ? "btn-quiet" : "btn-green"}" style="width:auto;min-height:48px"
        data-buy="${i.id}">${i.is_purchased ? "Undo" : "I Bought This"}</button>
    </div>`).join("") || `<div class="card center"><p>They haven't added any gift ideas yet. Send them a friendly nudge!</p></div>`;
  render("Their Wishlist", items + `
    <button class="btn btn-secondary" onclick="go('/events/${id}/messages')">Send a Secret Message</button>`);
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
  render("Manage Family", `
    <div class="card center">
      <p class="muted">Share this code so family can join:</p>
      <div class="reveal-name" style="font-size:1.8rem">${esc(fam.join_code)}</div>
    </div>
    <button class="card-btn" onclick="go('/admin/members')"><span class="emoji">👪</span><span>Members & Households</span></button>
    <button class="card-btn" onclick="go('/admin/events')"><span class="emoji">🎄</span><span>Gift Exchanges</span></button>
    <button class="card-btn" onclick="go('/admin/announce')"><span class="emoji">📢</span><span>Post an Announcement</span></button>
  `);
});

route(/^\/admin\/members$/, async () => {
  const [members, households] = await Promise.all([
    api.get(`/families/${FAMILY.id}/members`),
    api.get(`/families/${FAMILY.id}/households`),
  ]);
  const opts = hid => `<option value="">No household yet</option>` +
    households.map(hh => `<option value="${hh.id}" ${hh.id === hid ? "selected" : ""}>${esc(hh.name)}</option>`).join("");
  const rows = members.map(m => `
    <div class="card">
      <strong>${esc(m.user.display_name)}</strong>
      <div class="check-row">
        <input type="checkbox" id="admin-${m.membership_id}" data-role="${m.membership_id}" ${m.role === "admin" ? "checked" : ""}>
        <label for="admin-${m.membership_id}" style="margin:0">Organizer (can manage this family)</label>
      </div>
      <label>Household</label>
      <select data-house="${m.membership_id}">${opts(m.household_id)}</select>
    </div>`).join("");
  render("Members", `
    <div id="msg"></div>
    ${rows}
    <h2>Add a household</h2>
    <label>Household name</label>
    <input id="hname" placeholder="e.g. The Reyes House">
    <button class="btn btn-secondary" id="addHouse">Add Household</button>
    <p class="muted">People in the same household won't draw each other.</p>
  `);
  document.getElementById("addHouse").onclick = async () => {
    try { await api.post(`/families/${FAMILY.id}/households`, { name: document.getElementById("hname").value }); navigate(); }
    catch (e) { showError(e); }
  };
  $app.querySelectorAll("[data-house]").forEach(sel => sel.onchange = async () => {
    try {
      await api.patch(`/families/${FAMILY.id}/members/${sel.dataset.house}`,
        { household_id: sel.value ? Number(sel.value) : null });
      document.getElementById("msg").innerHTML = alertBox("Saved!", true);
    } catch (e) { showError(e); }
  });
  $app.querySelectorAll("[data-role]").forEach(cb => cb.onchange = async () => {
    try {
      await api.patch(`/families/${FAMILY.id}/members/${cb.dataset.role}`,
        { role: cb.checked ? "admin" : "member" });
      document.getElementById("msg").innerHTML = alertBox("Saved!", true);
    } catch (e) { cb.checked = !cb.checked; showError(e); }
  });
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
  `);
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
  `);
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
  render("All Wishlists", list);
});

route(/^\/admin\/announce$/, async () => {
  render("Post Announcement", `
    <label>Title</label><input id="atitle" placeholder="e.g. Party is at 6pm!">
    <label>Message</label><textarea id="abody" rows="4"></textarea>
    <div class="check-row"><input type="checkbox" id="apin"><label for="apin" style="margin:0">Pin to the top</label></div>
    <div id="msg"></div>
    <button class="btn btn-primary" id="postBtn">Post to the Family</button>
  `);
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
