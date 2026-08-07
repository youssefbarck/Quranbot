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
    if DATABASE_URL and "sslmode" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"

    ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0") or "0")

    # الأوقات الثلاثة
    MORNING_TIME = os.getenv("MORNING_TIME", "08:00")    # قراءة حزبين
    MIDDAY_TIME = os.getenv("MIDDAY_TIME", "13:00")      # استماع حزب
    EVENING_TIME = os.getenv("EVENING_TIME", "20:00")    # سؤال تفاعلي

    DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Africa/Algiers")

    PORT = int(os.getenv("PORT", "10000"))
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")

    @classmethod
    def is_ready(cls) -> bool:
        return bool(cls.BOT_TOKEN and cls.DATABASE_URL)


config = Config()
