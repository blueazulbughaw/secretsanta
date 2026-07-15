-- ============================================================
-- GIFTCIRCLE — Family Gift Exchange Platform
-- MySQL 8.0 Schema (works on Namecheap shared hosting MySQL/MariaDB)
-- Charset: utf8mb4 for emoji support in wishlists/messages
-- ============================================================

CREATE DATABASE IF NOT EXISTS giftcircle
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE giftcircle;

-- ------------------------------------------------------------
-- USERS — global identity. Username is the login identifier; phone
-- (SMS OTP) and password are both optional, alternate sign-in methods.
-- ------------------------------------------------------------
CREATE TABLE users (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  username      VARCHAR(60)  NOT NULL UNIQUE,
  phone         VARCHAR(30)  NULL UNIQUE,
  email         VARCHAR(255) NULL UNIQUE,
  password_hash VARCHAR(255) NULL,
  must_change_password TINYINT(1) NOT NULL DEFAULT 0,
  is_app_admin  TINYINT(1)   NOT NULL DEFAULT 0,
  full_name     VARCHAR(120) NOT NULL,
  display_name  VARCHAR(60)  NULL,           -- "Lola Nena", "Tito Ben"
  avatar_color  CHAR(7)      NOT NULL DEFAULT '#C0392B', -- accessible identicon fallback
  is_active     TINYINT(1)   NOT NULL DEFAULT 1,
  last_login_at DATETIME     NULL,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_users_username (username),
  INDEX idx_users_phone (phone)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- OTP_CODES — passwordless login. Codes are hashed, never stored raw.
-- ------------------------------------------------------------
CREATE TABLE otp_codes (
  id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  phone       VARCHAR(30)  NOT NULL,          -- keyed by phone so signup + login share flow
  code_hash   CHAR(64)     NOT NULL,          -- SHA-256 of 6-digit code + server pepper
  purpose     ENUM('login','join_family')     NOT NULL DEFAULT 'login',
  attempts    TINYINT UNSIGNED NOT NULL DEFAULT 0,   -- lock after 5
  expires_at  DATETIME     NOT NULL,           -- now + 10 minutes
  used_at     DATETIME     NULL,
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_otp_phone_expires (phone, expires_at)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- FAMILIES — top-level tenant. One family = one circle of members.
-- ------------------------------------------------------------
CREATE TABLE families (
  id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(120) NOT NULL,
  join_code   CHAR(8)      NOT NULL UNIQUE,   -- human-friendly invite code, e.g. "CEDENO26"
  created_by  BIGINT UNSIGNED NOT NULL,
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_families_creator FOREIGN KEY (created_by)
    REFERENCES users(id) ON DELETE RESTRICT,
  INDEX idx_families_join_code (join_code)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- HOUSEHOLDS — sub-groups within a family (e.g., "The Reyes House").
-- Used by the matcher to prevent spouses/housemates drawing each other.
-- ------------------------------------------------------------
CREATE TABLE households (
  id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  family_id   BIGINT UNSIGNED NOT NULL,
  name        VARCHAR(120) NOT NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_households_family FOREIGN KEY (family_id)
    REFERENCES families(id) ON DELETE CASCADE,
  UNIQUE KEY uq_household_name_per_family (family_id, name),
  INDEX idx_households_family (family_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- FAMILY_MEMBERS — join table users↔families. Role lives HERE,
-- not on users, because a person can be admin of one family
-- and a regular member of another.
-- ------------------------------------------------------------
CREATE TABLE family_members (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  family_id     BIGINT UNSIGNED NOT NULL,
  user_id       BIGINT UNSIGNED NOT NULL,
  household_id  BIGINT UNSIGNED NULL,          -- NULL = not yet assigned (blocks matching)
  role          ENUM('admin','member') NOT NULL DEFAULT 'member',
  joined_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_fm_family    FOREIGN KEY (family_id)    REFERENCES families(id)   ON DELETE CASCADE,
  CONSTRAINT fk_fm_user      FOREIGN KEY (user_id)      REFERENCES users(id)      ON DELETE CASCADE,
  CONSTRAINT fk_fm_household FOREIGN KEY (household_id) REFERENCES households(id) ON DELETE SET NULL,
  UNIQUE KEY uq_member_per_family (family_id, user_id),
  INDEX idx_fm_user (user_id),
  INDEX idx_fm_household (household_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- EVENTS — a single gift exchange (e.g., "Christmas 2026").
-- Rules (budget, wishlist limit, codenames) are set per event.
-- ------------------------------------------------------------
CREATE TABLE events (
  id                 BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  family_id          BIGINT UNSIGNED NOT NULL,
  name               VARCHAR(120) NOT NULL,
  event_date         DATE NOT NULL,
  budget_amount      DECIMAL(10,2) NULL,       -- NULL = no budget rule
  budget_currency    CHAR(3) NOT NULL DEFAULT 'USD',
  wishlist_limit     TINYINT UNSIGNED NOT NULL DEFAULT 5,
  use_codenames      TINYINT(1) NOT NULL DEFAULT 0,
  allow_same_household TINYINT(1) NOT NULL DEFAULT 0, -- admin can relax the rule
  status             ENUM('draft','open','matched','completed','cancelled')
                     NOT NULL DEFAULT 'draft',
  matched_at         DATETIME NULL,
  created_by         BIGINT UNSIGNED NOT NULL,
  created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_events_family  FOREIGN KEY (family_id)  REFERENCES families(id) ON DELETE CASCADE,
  CONSTRAINT fk_events_creator FOREIGN KEY (created_by) REFERENCES users(id)    ON DELETE RESTRICT,
  INDEX idx_events_family_status (family_id, status),
  INDEX idx_events_date (event_date)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- EVENT_PARTICIPANTS — who is in this specific exchange.
-- Admin checks boxes; codename generated if event.use_codenames.
-- ------------------------------------------------------------
CREATE TABLE event_participants (
  id               BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  event_id         BIGINT UNSIGNED NOT NULL,
  user_id          BIGINT UNSIGNED NOT NULL,
  codename         VARCHAR(60) NULL,           -- "Jolly Penguin" etc.
  is_participating TINYINT(1) NOT NULL DEFAULT 1,
  opted_out_at     DATETIME NULL,
  created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_ep_event FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
  CONSTRAINT fk_ep_user  FOREIGN KEY (user_id)  REFERENCES users(id)  ON DELETE CASCADE,
  UNIQUE KEY uq_participant_per_event (event_id, user_id),
  UNIQUE KEY uq_codename_per_event (event_id, codename),
  INDEX idx_ep_user (user_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- ASSIGNMENTS — the Secret Santa matches. One row per giver.
-- DB-level guards: a giver can only appear once per event,
-- and a receiver can only appear once per event.
-- ------------------------------------------------------------
CREATE TABLE assignments (
  id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  event_id     BIGINT UNSIGNED NOT NULL,
  giver_id     BIGINT UNSIGNED NOT NULL,       -- user id
  receiver_id  BIGINT UNSIGNED NOT NULL,       -- user id
  revealed_at  DATETIME NULL,                  -- when giver first viewed it
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_a_event    FOREIGN KEY (event_id)    REFERENCES events(id) ON DELETE CASCADE,
  CONSTRAINT fk_a_giver    FOREIGN KEY (giver_id)    REFERENCES users(id)  ON DELETE CASCADE,
  CONSTRAINT fk_a_receiver FOREIGN KEY (receiver_id) REFERENCES users(id)  ON DELETE CASCADE,
  UNIQUE KEY uq_giver_per_event    (event_id, giver_id),      -- prevents duplicate matches
  UNIQUE KEY uq_receiver_per_event (event_id, receiver_id),   -- prevents duplicate matches
  CONSTRAINT chk_no_self CHECK (giver_id <> receiver_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- WISHLISTS — items a participant wants, scoped to an event.
-- purchased_by is HIDDEN from the wishlist owner in the API layer.
-- ------------------------------------------------------------
CREATE TABLE wishlists (
  id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  event_id        BIGINT UNSIGNED NOT NULL,
  user_id         BIGINT UNSIGNED NOT NULL,    -- the wishlist owner
  item_name       VARCHAR(200) NOT NULL,
  description     TEXT NULL,
  link_url        VARCHAR(500) NULL,
  price_estimate  DECIMAL(10,2) NULL,
  priority        TINYINT UNSIGNED NOT NULL DEFAULT 3,  -- 1 = most wanted
  photo_path      VARCHAR(255) NULL,           -- relative path under app/static/
  is_purchased    TINYINT(1) NOT NULL DEFAULT 0,
  purchased_by    BIGINT UNSIGNED NULL,        -- never exposed to owner
  purchased_at    DATETIME NULL,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                  ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_w_event FOREIGN KEY (event_id)     REFERENCES events(id) ON DELETE CASCADE,
  CONSTRAINT fk_w_user  FOREIGN KEY (user_id)      REFERENCES users(id)  ON DELETE CASCADE,
  CONSTRAINT fk_w_buyer FOREIGN KEY (purchased_by) REFERENCES users(id)  ON DELETE SET NULL,
  INDEX idx_w_event_user (event_id, user_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- MESSAGES — anonymous giver↔giftee chat, scoped to an event.
-- Sender identity is stored (for abuse handling) but the API
-- shows only "Your Secret Santa" / codename to the recipient.
-- ------------------------------------------------------------
CREATE TABLE messages (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  event_id      BIGINT UNSIGNED NOT NULL,
  sender_id     BIGINT UNSIGNED NOT NULL,
  recipient_id  BIGINT UNSIGNED NOT NULL,
  body          TEXT NOT NULL,
  is_anonymous  TINYINT(1) NOT NULL DEFAULT 1,
  read_at       DATETIME NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_m_event     FOREIGN KEY (event_id)     REFERENCES events(id) ON DELETE CASCADE,
  CONSTRAINT fk_m_sender    FOREIGN KEY (sender_id)    REFERENCES users(id)  ON DELETE CASCADE,
  CONSTRAINT fk_m_recipient FOREIGN KEY (recipient_id) REFERENCES users(id)  ON DELETE CASCADE,
  INDEX idx_m_recipient_read (recipient_id, read_at),
  INDEX idx_m_event (event_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- ANNOUNCEMENTS — admin posts to the whole family (or one event).
-- ------------------------------------------------------------
CREATE TABLE announcements (
  id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  family_id   BIGINT UNSIGNED NOT NULL,
  event_id    BIGINT UNSIGNED NULL,            -- NULL = family-wide
  author_id   BIGINT UNSIGNED NOT NULL,
  title       VARCHAR(200) NOT NULL,
  body        TEXT NOT NULL,
  is_pinned   TINYINT(1) NOT NULL DEFAULT 0,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_an_family FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE,
  CONSTRAINT fk_an_event  FOREIGN KEY (event_id)  REFERENCES events(id)   ON DELETE CASCADE,
  CONSTRAINT fk_an_author FOREIGN KEY (author_id) REFERENCES users(id)    ON DELETE CASCADE,
  INDEX idx_an_family_created (family_id, created_at DESC)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- NOTIFICATIONS — in-app now; push-ready via `channel` + `push_sent_at`.
-- ------------------------------------------------------------
CREATE TABLE notifications (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id       BIGINT UNSIGNED NOT NULL,
  type          ENUM('assignment','message','announcement','wishlist',
                     'event','reminder','system') NOT NULL,
  title         VARCHAR(200) NOT NULL,
  body          VARCHAR(500) NULL,
  link_path     VARCHAR(255) NULL,             -- in-app deep link, e.g. /events/12
  channel       ENUM('in_app','push','email') NOT NULL DEFAULT 'in_app',
  is_read       TINYINT(1) NOT NULL DEFAULT 0,
  push_sent_at  DATETIME NULL,                 -- future-ready for web push
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_n_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_n_user_unread (user_id, is_read, created_at DESC)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- PUSH_SUBSCRIPTIONS — future-ready for Web Push (PWA).
-- Stores the browser subscription objects; unused until push ships.
-- ------------------------------------------------------------
CREATE TABLE push_subscriptions (
  id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id      BIGINT UNSIGNED NOT NULL,
  endpoint     VARCHAR(500) NOT NULL,
  p256dh_key   VARCHAR(255) NOT NULL,
  auth_key     VARCHAR(255) NOT NULL,
  user_agent   VARCHAR(255) NULL,
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_ps_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_endpoint (endpoint(191))
) ENGINE=InnoDB;
