from flask import Flask, render_template, make_response
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
    from .api.dishes import bp as dishes_bp

    for bp in (auth_bp, families_bp, households_bp, events_bp, assignments_bp,
               wishlists_bp, messages_bp, announcements_bp, notifications_bp, dishes_bp):
        app.register_blueprint(bp, url_prefix="/api")

    # Real pages (not the JS app shell) so anyone - including a texting-provider reviewer -
    # can open them without signing in or running JavaScript.
    @app.route("/privacy")
    def privacy():
        return render_template("privacy.html")

    @app.route("/terms")
    def terms():
        return render_template("terms.html")

    @app.route("/sms-optin")
    def sms_optin():
        # A stable, plain reference page for SMS compliance review: the same real opt-in
        # form (phone field, unchecked consent checkbox, "Text Me a Sign-In Code") shown in
        # isolation, deliberately NOT styled like the main app (see the long comment at the
        # top of sms_optin.html for why). Fully functional, not a mockup.
        return render_template("sms_optin.html")

    @app.route("/")
    def landing():
        # The root URL specifically also renders a server-side copy of the sign-in form (see
        # _login_fallback.html) so the SMS opt-in CTA is visible to anything that fetches this
        # page without running JavaScript - e.g. a texting-provider compliance reviewer. Once
        # app.js boots it overwrites this with the identical live version.
        #
        # This is hash-routed (#/dashboard, #/admin/members, ...), so EVERY page in the app
        # requests this exact "/" on a full reload, not just first-time sign-in. A visitor who
        # already has a valid session cookie gets the plain empty shell instead - same as every
        # other route - so JS boots straight into their real page with no flash of the sign-in
        # form they're not actually looking at. Anyone without a session (which includes a
        # compliance reviewer, who never has one) still always gets the real form.
        from .middleware.auth import is_signed_in
        if is_signed_in():
            resp = make_response(render_template("index.html"))
        else:
            resp = make_response(render_template("index.html", initial_html=render_template("_login_fallback.html")))
        # This response's content depends on the request's cookie, so it must never be cached
        # and reused for a different visitor (would either leak the fallback's absence to an
        # anonymous visitor, or - worse - could theoretically serve a cached authenticated-empty
        # shell to someone else; neither should happen with Flask's defaults, but belt and braces).
        resp.headers["Cache-Control"] = "no-store"
        return resp

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
