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
    is_app_admin = db.Column(db.Boolean, nullable=False, default=False)
    full_name = db.Column(db.String(120), nullable=False, default="")
    display_name = db.Column(db.String(60))
    avatar_color = db.Column(db.String(7), nullable=False, default="#C0392B")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

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


class Event(db.Model):
    __tablename__ = "events"
    id = db.Column(BigIntPK, primary_key=True)
    family_id = db.Column(db.BigInteger, db.ForeignKey("families.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    event_date = db.Column(db.Date, nullable=False)
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
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
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
