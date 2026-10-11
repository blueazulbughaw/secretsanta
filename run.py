"""Local development entry point: python run.py"""
import os

# Dev mode from the start, so create_app() allows config.py's placeholder secrets here
# (they're refused everywhere else - see _refuse_default_secrets in app/__init__.py).
os.environ.setdefault("FLASK_DEBUG", "1")

from app import create_app  # noqa: E402
from app.extensions import db

app = create_app()

with app.app_context():
    db.create_all()   # convenience for local dev; use Flask-Migrate for production

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
