import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    JWT_SECRET = os.getenv("JWT_SECRET", "dev-jwt-change-me")
    OTP_PEPPER = os.getenv("OTP_PEPPER", "dev-pepper-change-me")

    # Falls back to a local SQLite file so you can run instantly;
    # set DATABASE_URL to your MySQL URL for real use.
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///giftcircle_dev.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_SERVER = os.getenv("MAIL_SERVER", "")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "465"))
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "true").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_USERNAME", "no-reply@giftcircle.local")

    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")

    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000")

    # Phone numbers (E.164, comma-separated) allowed to create new families.
    # Everyone else can only join an existing family via its join code.
    APP_ADMIN_PHONES = [p.strip() for p in os.getenv("APP_ADMIN_PHONES", "").split(",") if p.strip()]

    # Hidden password-only login at /ss-admin, bypassing SMS entirely. Logs in as
    # the first APP_ADMIN_PHONES user. Leave empty to disable the route entirely.
    ADMIN_BACKDOOR_PASSWORD = os.getenv("ADMIN_BACKDOOR_PASSWORD", "")

    OTP_TTL_MINUTES = 10
    OTP_MAX_ATTEMPTS = 5
    OTP_REQUESTS_PER_WINDOW = 3       # per phone number
    OTP_WINDOW_MINUTES = 15
    JWT_DAYS = 7
