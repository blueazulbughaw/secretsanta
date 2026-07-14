from flask import Flask, render_template
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
