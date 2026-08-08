"""
إعدادات البوت — طريقة الحصون الخمسة
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

    DATABASE_URL = os.getenv("DATABASE_URL", "").replace(
        "postgres://", "postgresql://"
    )
    # نُضيف sslmode=require فقط لقواعد Postgres (وليس SQLite)
    if DATABASE_URL and DATABASE_URL.startswith("postgresql://") and "sslmode" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"

    ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0") or "0")

    # الأوقات الثلاثة
    MORNING_TIME = os.getenv("MORNING_TIME", "08:00")    # قراءة حزبين
    MIDDAY_TIME = os.getenv("MIDDAY_TIME", "13:00")      # استماع حزب
    EVENING_TIME = os.getenv("EVENING_TIME", "20:00")    # سؤال تفاعلي

    DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Africa/Algiers")

    PORT = int(os.getenv("PORT", "10000"))
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")

    # keep-alive مدمج — يجعل الخدمة لا تنام على Render Free
    KEEPALIVE_ENABLED = os.getenv("KEEPALIVE_ENABLED", "true").lower() == "true"
    KEEPALIVE_INTERVAL = int(os.getenv("KEEPALIVE_INTERVAL", "280"))  # ثواني

    @classmethod
    def is_ready(cls) -> bool:
        return bool(cls.BOT_TOKEN and cls.DATABASE_URL)

    @classmethod
    def public_health_url(cls) -> str:
        """يرد URL الـ health الكامل إذا كان RENDER_EXTERNAL_URL مضبوطاً"""
        if cls.RENDER_EXTERNAL_URL:
            return f"{cls.RENDER_EXTERNAL_URL}/health"
        return ""


config = Config()
