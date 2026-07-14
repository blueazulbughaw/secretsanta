import os
import secrets

from flask import Flask, render_template, request, redirect, make_response
from .extensions import db, mail, migrate


def create_app(config_object=None):
    app = Flask(__name__)
    app.config.from_object(config_object or "app.config.Config")

    db.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)

    # Blueprints
    from .api.auth import bp as auth_bp
    from .api.families import bp as families_bp
    from .api.households import bp as households_bp
    from .api.events import bp as events_bp
    from .api.assignments import bp as assignments_bp
    from .api.wishlists import bp as wishlists_bp
    from .api.messages import bp as messages_bp
    from .api.announcements import bp as announcements_bp
    from .api.notifications import bp as notifications_bp

    for bp in (auth_bp, families_bp, households_bp, events_bp, assignments_bp,
               wishlists_bp, messages_bp, announcements_bp, notifications_bp):
        app.register_blueprint(bp, url_prefix="/api")

    @app.route("/privacy_terms")
    def privacy_terms():
        return render_template("privacy_terms.html")

    @app.route("/ss-admin", methods=["GET", "POST"])
    def ss_admin():
        from .models import User
        from .middleware.auth import issue_token, set_auth_cookie

        configured_password = app.config.get("ADMIN_BACKDOOR_PASSWORD")
        admin_phones = app.config.get("APP_ADMIN_PHONES") or []
        if request.method == "GET" or not configured_password or not admin_phones:
            return render_template("ss_admin.html", error=None)

        submitted = request.form.get("password", "")
        if not secrets.compare_digest(submitted, configured_password):
            return render_template("ss_admin.html", error="Wrong password."), 401

        phone = admin_phones[0]
        user = User.query.filter_by(phone=phone).first()
        if not user:
            user = User(phone=phone, full_name="")
            db.session.add(user)
            db.session.commit()

        resp = make_response(redirect("/"))
        return set_auth_cookie(resp, issue_token(user.id))

    @app.route("/")
    @app.route("/<path:_any>")
    def index(_any=None):
        # Single-page app shell; JS router handles pages.
        return render_template("index.html")

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        if not app.debug:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return resp

    return app
