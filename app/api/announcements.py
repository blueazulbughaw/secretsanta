from flask import Blueprint, request, jsonify, g

from ..extensions import db
from ..models import Announcement, FamilyMember
from ..middleware.auth import require_auth, require_family_member, require_family_admin
from ..services.notification_service import notify

bp = Blueprint("announcements", __name__)


@bp.get("/families/<int:family_id>/announcements")
@require_auth
def list_announcements(family_id):
    m, err = require_family_member(family_id)
    if err:
        return err
    q = Announcement.query.filter_by(family_id=family_id)
    # Admins managing the list (Manage My Clan > Post Announcement) can see
    # unpublished ones too; every other caller (the member Dashboard, the
    # standalone page) only ever sees what's actually published.
    if not (m.role == "admin" and request.args.get("scope") == "all"):
        q = q.filter_by(is_published=True)
    anns = (q.order_by(Announcement.is_pinned.desc(),
                        Announcement.created_at.desc()).limit(50).all())
    return jsonify([{
        "id": a.id, "title": a.title, "body": a.body,
        "author": a.author.display_name or a.author.full_name,
        "is_pinned": a.is_pinned, "is_published": a.is_published, "at": a.created_at.isoformat(),
    } for a in anns])


@bp.post("/families/<int:family_id>/announcements")
@require_auth
def post_announcement(family_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    data = request.json or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    if not title or not body:
        return jsonify({"error": "Please add a title and a message."}), 400
    is_published = bool(data.get("is_published", True))
    a = Announcement(family_id=family_id, event_id=data.get("event_id"),
                     author_id=g.user.id, title=title[:200], body=body,
                     is_pinned=bool(data.get("is_pinned")), is_published=is_published)
    db.session.add(a)
    db.session.commit()
    if is_published:
        for m in FamilyMember.query.filter_by(family_id=family_id).all():
            if m.user_id != g.user.id:
                notify(m.user_id, "announcement", f"📢 {title}",
                       body[:200], link_path="/announcements")
    return jsonify({"ok": True, "id": a.id}), 201


@bp.patch("/announcements/<int:ann_id>")
@require_auth
def edit_announcement(ann_id):
    a = Announcement.query.get_or_404(ann_id)
    _, err = require_family_admin(a.family_id)
    if err:
        return err
    data = request.json or {}
    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify({"error": "Please add a title."}), 400
        a.title = title[:200]
    if "body" in data:
        body = (data.get("body") or "").strip()
        if not body:
            return jsonify({"error": "Please add a message."}), 400
        a.body = body
    if "is_pinned" in data:
        a.is_pinned = bool(data["is_pinned"])
    if "is_published" in data:
        a.is_published = bool(data["is_published"])
    db.session.commit()
    return jsonify({"ok": True})


@bp.delete("/announcements/<int:ann_id>")
@require_auth
def delete_announcement(ann_id):
    a = Announcement.query.get_or_404(ann_id)
    _, err = require_family_admin(a.family_id)
    if err:
        return err
    db.session.delete(a)
    db.session.commit()
    return jsonify({"ok": True})
