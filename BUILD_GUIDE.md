# Secret Santa — Step-by-Step Build & Deployment Guide

This guide takes you from empty folder → deployed app on a Namecheap subdomain, using the exact workflow you've already set up for Genri Labs: **VS Code + Claude Code + GitHub + cPanel Git deployment**.

Structured as 6 sprints (~1 week each at part-time pace), each with a clear "done" definition — designed for sprint-based work.

---

## Phase 0 — Repo & environment (Day 1)

### 0.1 Create the repo on GitHub
1. github.com → New repository → `giftcircle` → Private → add Python `.gitignore` → Create.

### 0.2 Clone and open in VS Code
```powershell
cd C:\Users\<you>\projects
git clone https://github.com/<your-username>/giftcircle.git
cd giftcircle
code .
```

### 0.3 Local Python environment (Windows)
```powershell
py -3.11 -m venv venv
.\venv\Scripts\activate
pip install flask flask-sqlalchemy flask-migrate flask-mail pymysql python-dotenv pyjwt
pip freeze > requirements.txt
```

### 0.4 Local MySQL
Install MySQL 8 Community (or XAMPP if you prefer a GUI). Then:
```sql
CREATE DATABASE giftcircle CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'gc_dev'@'localhost' IDENTIFIED BY 'dev_password_here';
GRANT ALL PRIVILEGES ON giftcircle.* TO 'gc_dev'@'localhost';
```

### 0.5 Environment variables
Create `.env` (already in `.gitignore`) from this template — commit `.env.example` only:
```
FLASK_ENV=development
SECRET_KEY=change-me
JWT_SECRET=change-me-too
OTP_PEPPER=change-me-three
DATABASE_URL=mysql+pymysql://gc_dev:dev_password_here@localhost/giftcircle
MAIL_SERVER=mail.yourdomain.com
MAIL_PORT=465
MAIL_USE_SSL=true
MAIL_USERNAME=hello@yourdomain.com
MAIL_PASSWORD=
APP_BASE_URL=http://localhost:5000
```

✅ **Done when:** repo cloned, venv active, MySQL running, `.env` created.

---

## Phase 1 — Drive the build with Claude Code (Sprints 1–4)

Open the Claude Code panel/terminal inside VS Code at the repo root. The workflow for **every** feature is the same loop:

> **Plan → Build → Test → Review the diff → Commit → Push**

### 1.1 First: give Claude Code the context
Copy `schema.sql` and `ARCHITECTURE.md` into the repo root, then create `CLAUDE.md` in the root — Claude Code reads it automatically every session:

```markdown
# CLAUDE.md
Secret Santa: family gift-exchange app. Flask + SQLAlchemy + MySQL + vanilla JS PWA.
- Follow ARCHITECTURE.md exactly (structure, endpoints, roles).
- Schema is schema.sql — use Flask-Migrate, never raw ALTER in code.
- Auth: email OTP → JWT in httpOnly cookie. NO passwords anywhere.
- Every endpoint must check the user belongs to the resource's family.
- UI: base font 20px, buttons ≥64px tall, one primary action per screen,
  no jargon ("sign-in code" not "OTP"). Colors: white bg, #C0392B red,
  #2E7D4F green, #F5C518 yellow accents.
- Write pytest tests for services; run them before saying a task is done.
- Target deploy: Namecheap cPanel Python app (passenger_wsgi.py entry).
```

### 1.2 Sprint 1 — Foundation & Auth
Prompt Claude Code with one scoped task at a time (small prompts = reviewable diffs):

1. *"Scaffold the Flask app factory per ARCHITECTURE.md §2: app/__init__.py, config.py from env vars, register empty blueprints, run.py. Make `flask run` serve a hello route."*
2. *"Create SQLAlchemy models matching schema.sql exactly, then init Flask-Migrate and generate the initial migration. Run it against my local DB."*
3. *"Implement the OTP auth flow per ARCHITECTURE.md §4: otp_service, mail_service, auth blueprint, JWT cookie, @require_auth decorator. Include rate limiting and pytest tests for expiry, max attempts, and reuse."*
4. *"Build the login UI: two-step flow (email → code), 20px+ fonts, 64px buttons, plain language."*

After each task: run the app yourself, click through it, read the diff in VS Code's Source Control panel, then:
```powershell
git add -A
git commit -m "feat(auth): email OTP login with JWT cookie"
git push
```

✅ **Done when:** you can log in on your phone (same wifi) with a code emailed to you.

### 1.3 Sprint 2 — Families, households, members
5. *"Implement families blueprint: create family with join code, join by code, member list, admin role management, @require_family_admin decorator, multi-tenant checks. Tests included."*
6. *"Implement households CRUD and assigning members to households. Admin UI: member list with a big 'Set Household' picker per member."*

✅ **Done when:** two test accounts can be in one family, one as admin, both assigned to households.

### 1.4 Sprint 3 — Events, participants, matching (the heart)
7. *"Implement events CRUD with rules (budget, wishlist_limit, use_codenames) and the participant checkbox screen (PUT /events/:id/participants)."*
8. *"Implement matching_service exactly per ARCHITECTURE.md §6: validation gate with human-readable errors, backtracking matcher, single-transaction insert, codename generation, notifications fan-out. Write pytest tests covering: self-match impossible, same-household blocked, impossible-configuration error, duplicate-guard via DB constraints, and 1000 random 50-person runs all valid."*
9. *"Build the admin 'Draw Names' screen (validation errors shown in plain language) and the member 'My Person' reveal screen with a warm, large-type reveal."*

✅ **Done when:** the matcher test suite passes and a 5-person test family gets valid assignments.

### 1.5 Sprint 4 — Wishlists, messages, announcements, notifications
10. *"Implement wishlist CRUD with wishlist_limit enforcement, the giver's giftee-wishlist view with 'I Bought This' button, and the rule that owners never see purchase status. Tests for that privacy rule specifically."*
11. *"Implement anonymous messaging per §5: server resolves giver/giftee, sender displayed as 'Your Secret Santa' or codename."*
12. *"Implement announcements (admin post, family feed) and in-app notifications with unread badge."*

✅ **Done when:** full happy path works end-to-end with 3 test users on your phone.

---

## Phase 2 — PWA polish (Sprint 5)
13. *"Add manifest.json (name Secret Santa, theme #C0392B, 192/512 icons) and sw.js: cache-first static, network-first API, offline fallback page. Make Lighthouse PWA installable check pass."*
14. *"Add /api/push/subscribe storing to push_subscriptions (no sending yet — future-ready only)."*
15. *"Accessibility pass: WCAG AA contrast, focus states, aria-live confirmations, test at 200% zoom."*

✅ **Done when:** "Add to Home Screen" works on your phone and Lighthouse accessibility score ≥ 95.

---

## Phase 3 — Deploy to Namecheap subdomain (Sprint 6)

You've done most of this dance before with your portfolio — same moves.

### 3.1 Subdomain + database
1. cPanel → **Domains → Create a New Domain** → `gifts.yourdomain.com` (document root e.g. `~/gifts.yourdomain.com`).
2. cPanel → **MySQL® Databases** → create DB `<cpuser>_giftcircle`, user `<cpuser>_gc`, strong password, grant ALL. Note the full prefixed names.

### 3.2 Git deployment (cPanel Git Version Control)
3. cPanel → **Git™ Version Control → Create** → clone your GitHub repo (use the SSH URL; you already have SSH keys set up as `gladc`). Repository path: the subdomain's document root.
4. Add a `.cpanel.yml` in the repo so pushes deploy automatically:
```yaml
---
deployment:
  tasks:
    - export DEPLOYPATH=/home/<cpuser>/gifts.yourdomain.com
    - /bin/cp -R app migrations passenger_wsgi.py requirements.txt $DEPLOYPATH
```
5. Workflow from now on: `git push` to GitHub → pull in cPanel Git (or push directly to the cPanel remote) → Deploy HEAD.

### 3.3 Python app on cPanel
6. cPanel → **Setup Python App** → Create: Python 3.11, app root = subdomain folder, app URL = `gifts.yourdomain.com`, startup file `passenger_wsgi.py`, entry point `application`.
7. `passenger_wsgi.py`:
```python
from app import create_app
application = create_app()
```
8. In the Python App screen, add every variable from your `.env` as **environment variables** (DATABASE_URL now points to the cPanel DB: `mysql+pymysql://<cpuser>_gc:PASSWORD@localhost/<cpuser>_giftcircle`). Generate fresh SECRET_KEY / JWT_SECRET / OTP_PEPPER for production — never reuse dev secrets.
9. Open the app's virtualenv terminal command shown at the top of that screen, then:
```bash
pip install -r requirements.txt
flask db upgrade        # runs migrations against production DB
```
10. Restart the Python app.

### 3.4 Lock it down
11. cPanel → SSL/TLS Status → run **AutoSSL** for the subdomain; confirm https works.
12. Add HSTS + security headers (Claude Code task: *"Add Flask-Talisman or manual security headers: HSTS, X-Content-Type-Options, frame-ancestors none."*)
13. Set up the mail account (`hello@yourdomain.com`) in cPanel → Email Accounts and confirm OTP emails deliver (check spam scoring; add SPF/DKIM in Zone Editor if needed).
14. Smoke test on your phone over cellular: login → wishlist → draw names with test accounts → messages.

✅ **Done when:** a relative can install it from `https://gifts.yourdomain.com` and log in with just their email.

---

## Ongoing workflow cheat-sheet

```
VS Code (edit/review) ──> Claude Code (build/test) ──> git commit/push ──> GitHub
                                                              │
                                     cPanel Git pull + Deploy HEAD ──> flask db upgrade ──> restart app
```

Rules that will save you pain:
- **One feature per Claude Code prompt, one commit per feature.** Small diffs are reviewable diffs.
- **Never let Claude Code (or yourself) edit production directly.** Everything flows through Git.
- **Run `pytest` before every push.** Ask Claude Code to add a test whenever it fixes a bug.
- **Migrations only via Flask-Migrate.** Production schema changes = `flask db upgrade`, never hand-run SQL after launch.
- Branch when experimenting: `git checkout -b feature/push-notifications`, merge via PR on GitHub — good practice for your portfolio too.
