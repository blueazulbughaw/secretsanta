"""Local development entry point: python run.py"""
from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    db.create_all()   # convenience for local dev; use Flask-Migrate for production

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
