from datetime import datetime
from .extensions import db

# BigInteger on MySQL, Integer on SQLite (SQLite only autoincrements INTEGER PKs)
BigIntPK = db.BigInteger().with_variant(db.Integer, "sqlite")


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(BigIntPK, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30), unique=True, nullable=True, index=True)
    email = db.Column(db.String(255), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    is_app_admin = db.Column(db.Boolean, nullable=False, default=False)
    full_name = db.Column(db.String(120), nullable=False, default="")
    display_name = db.Column(db.String(60))
    avatar_color = db.Column(db.String(7), nullable=False, default="#C0392B")
    photo_path = db.Column(db.String(255))  # profile photo, relative to static/
    about_me = db.Column(db.Text)
    likes = db.Column(db.Text)
    favorite_color = db.Column(db.String(80))  # "#rrggbb,#rrggbb" - see favorite_colors
    avoid_gifts = db.Column(db.Text)  # "what not to give me"
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Bumped to end every existing session (see issue_token in middleware/auth.py)
    session_version = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @property
    def favorite_colors(self):
        """Up to MAX_FAVORITE_COLORS "#rrggbb" colors, picked with a color picker."""
        return [c for c in (self.favorite_color or "").split(",") if c]

    @favorite_colors.setter
    def favorite_colors(self, colors):
        self.favorite_color = ",".join(colors) or None

    def public_dict(self):
        """What the rest of the clan may see: no username, phone or email."""
        return {
            "id": self.id,
            "full_name": self.full_name,
            "display_name": self.display_name or self.full_name,
            "avatar_color": self.avatar_color,
            "photo_url": f"/static/{self.photo_path}" if self.photo_path else None,
            "about_me": self.about_me or "",
            "likes": self.likes or "",
            "favorite_colors": self.favorite_colors,
        }

    def clan_dict(self):
        """The full profile card the clan sees (public_dict + "what not to give me"),
        still with no username, phone or email. to_dict() is for the user
        themselves and clan admins only."""
        return {**self.public_dict(), "avoid_gifts": self.avoid_gifts or ""}

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "phone": self.phone,
            "email": self.email,
            "has_password": self.password_hash is not None,
            "is_app_admin": self.is_app_admin,
            "full_name": self.full_name,
            "display_name": self.display_name or self.full_name,
            "avatar_color": self.avatar_color,
            "photo_url": f"/static/{self.photo_path}" if self.photo_path else None,
            "about_me": self.about_me or "",
            "likes": self.likes or "",
            "favorite_colors": self.favorite_colors,
            "avoid_gifts": self.avoid_gifts or "",
        }


class OtpCode(db.Model):
    __tablename__ = "otp_codes"
    id = db.Column(BigIntPK, primary_key=True)
    phone = db.Column(db.String(30), nullable=False, index=True)
    code_hash = db.Column(db.String(64), nullable=False)
    purpose = db.Column(db.String(20), nullable=False, default="login")
    attempts = db.Column(db.SmallInteger, nullable=False, default=0)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class RateLimitHit(db.Model):
    """One counted request for an IP rate limit (otp_service.check_ip_rate_limit). Kept in
    the database, not process memory: production runs several app processes that restart
    often, so an in-memory count was split between them and kept being wiped."""
    __tablename__ = "rate_limit_hits"
    id = db.Column(BigIntPK, primary_key=True)
    bucket = db.Column(db.String(20), nullable=False)
    ip = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (db.Index("ix_rate_limit_lookup", "bucket", "ip", "created_at"),)


class Family(db.Model):
    __tablename__ = "families"
    id = db.Column(BigIntPK, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    join_code = db.Column(db.String(8), unique=True, nullable=False, index=True)
    created_by = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Household(db.Model):
    __tablename__ = "households"
    id = db.Column(BigIntPK, primary_key=True)
    family_id = db.Column(db.BigInteger, db.ForeignKey("families.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("family_id", "name", name="uq_household_name_per_family"),)


class FamilyMember(db.Model):
    __tablename__ = "family_members"
    id = db.Column(BigIntPK, primary_key=True)
    family_id = db.Column(db.BigInteger, db.ForeignKey("families.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    household_id = db.Column(db.BigInteger, db.ForeignKey("households.id", ondelete="SET NULL"))
    role = db.Column(db.String(10), nullable=False, default="member")  # 'admin' | 'member'
    joined_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("family_id", "user_id", name="uq_member_per_family"),)

    user = db.relationship("User")
    household = db.relationship("Household")


class JoinRequest(db.Model):
    """Someone who entered a clan's code and is waiting for a clan admin to let them in.
    Kept apart from family_members on purpose: until approved they aren't a member, so
    every membership check in the app keeps working with nothing to filter out."""
    __tablename__ = "join_requests"
    id = db.Column(BigIntPK, primary_key=True)
    family_id = db.Column(db.BigInteger, db.ForeignKey("families.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("family_id", "user_id", name="uq_join_request"),)

    user = db.relationship("User")


class Event(db.Model):
    __tablename__ = "events"
    id = db.Column(BigIntPK, primary_key=True)
    family_id = db.Column(db.BigInteger, db.ForeignKey("families.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    event_time = db.Column(db.Time)
    location = db.Column(db.String(255))
    theme = db.Column(db.String(120))
    rules = db.Column(db.Text)
    what_to_bring = db.Column(db.Text)
    other_info = db.Column(db.Text)
    game_master_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="SET NULL"))
    budget_amount = db.Column(db.Numeric(10, 2))
    budget_currency = db.Column(db.String(3), nullable=False, default="USD")
    wishlist_limit = db.Column(db.SmallInteger, nullable=False, default=5)
    use_codenames = db.Column(db.Boolean, nullable=False, default=False)
    allow_same_household = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(12), nullable=False, default="open")
    matched_at = db.Column(db.DateTime)
    created_by = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "family_id": self.family_id, "name": self.name,
            "event_date": self.event_date.isoformat(),
            "event_time": self.event_time.strftime("%H:%M") if self.event_time else None,
            "location": self.location or "",
            "theme": self.theme or "",
            "rules": self.rules or "",
            "what_to_bring": self.what_to_bring or "",
            "other_info": self.other_info or "",
            "game_master_id": self.game_master_id,
            "budget_amount": float(self.budget_amount) if self.budget_amount else None,
            "budget_currency": self.budget_currency,
            "wishlist_limit": self.wishlist_limit,
            "use_codenames": self.use_codenames,
            "allow_same_household": self.allow_same_household,
            "status": self.status,
        }


class EventParticipant(db.Model):
    __tablename__ = "event_participants"
    id = db.Column(BigIntPK, primary_key=True)
    event_id = db.Column(db.BigInteger, db.ForeignKey("events.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    codename = db.Column(db.String(60))
    is_participating = db.Column(db.Boolean, nullable=False, default=True)
    opted_out_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("event_id", "user_id", name="uq_participant_per_event"),
        db.UniqueConstraint("event_id", "codename", name="uq_codename_per_event"),
    )

    user = db.relationship("User")


class Assignment(db.Model):
    __tablename__ = "assignments"
    id = db.Column(BigIntPK, primary_key=True)
    event_id = db.Column(db.BigInteger, db.ForeignKey("events.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    giver_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    revealed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("event_id", "giver_id", name="uq_giver_per_event"),
        db.UniqueConstraint("event_id", "receiver_id", name="uq_receiver_per_event"),
        db.CheckConstraint("giver_id <> receiver_id", name="chk_no_self"),
    )


class EventDish(db.Model):
    """One dish someone is bringing to one event. A person's dishes for an event
    (all rows with their user_id) are their single sign-up entry."""
    __tablename__ = "event_dishes"
    id = db.Column(BigIntPK, primary_key=True)
    event_id = db.Column(db.BigInteger, db.ForeignKey("events.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class WishlistItem(db.Model):
    __tablename__ = "wishlists"
    id = db.Column(BigIntPK, primary_key=True)
    event_id = db.Column(db.BigInteger, db.ForeignKey("events.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    item_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    link_url = db.Column(db.String(500))
    price_estimate = db.Column(db.Numeric(10, 2))
    priority = db.Column(db.SmallInteger, nullable=False, default=3)
    photo_path = db.Column(db.String(255))
    is_purchased = db.Column(db.Boolean, nullable=False, default=False)
    purchased_by = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="SET NULL"))
    purchased_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self, include_purchase=False):
        d = {
            "id": self.id, "event_id": self.event_id, "user_id": self.user_id,
            "item_name": self.item_name, "description": self.description,
            "link_url": self.link_url,
            "price_estimate": float(self.price_estimate) if self.price_estimate else None,
            "priority": self.priority,
            "photo_url": f"/static/{self.photo_path}" if self.photo_path else None,
            # Owners never see is_purchased/who/when, but do need to know an item
            # is no longer editable once someone's bought it.
            "locked": self.is_purchased,
        }
        if include_purchase:  # never for the wishlist owner
            d["is_purchased"] = self.is_purchased
        return d


class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(BigIntPK, primary_key=True)
    event_id = db.Column(db.BigInteger, db.ForeignKey("events.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    sender_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recipient_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    is_anonymous = db.Column(db.Boolean, nullable=False, default=True)
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Announcement(db.Model):
    __tablename__ = "announcements"
    id = db.Column(BigIntPK, primary_key=True)
    family_id = db.Column(db.BigInteger, db.ForeignKey("families.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    event_id = db.Column(db.BigInteger, db.ForeignKey("events.id", ondelete="CASCADE"))
    author_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    author = db.relationship("User")


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(BigIntPK, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    type = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.String(500))
    link_path = db.Column(db.String(255))
    # What it's about, so it goes when that does (deleting an announcement, event or clan
    # deletes its notifications). Plain ids, no foreign keys: the live tables are MyISAM.
    family_id = db.Column(db.BigInteger, index=True)
    event_id = db.Column(db.BigInteger, index=True)
    announcement_id = db.Column(db.BigInteger, index=True)
    channel = db.Column(db.String(10), nullable=False, default="in_app")
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    push_sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class PushSubscription(db.Model):
    __tablename__ = "push_subscriptions"
    id = db.Column(BigIntPK, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    endpoint = db.Column(db.String(500), nullable=False, unique=True)
    p256dh_key = db.Column(db.String(255), nullable=False)
    auth_key = db.Column(db.String(255), nullable=False)
    user_agent = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
