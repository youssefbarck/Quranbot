"""
الإعدادات والثوابت
==================
كل الأرقام الجوهرية للمنهجية موجودة هنا — يمكن تعديلها لاحقًا دون البحث في الكود.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ====== بيانات الاعتماد ======
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip().replace("postgres://", "postgresql://")
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0") or "0")
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Africa/Algiers")

# ====== الخادم ======
PORT = int(os.getenv("PORT", "10000"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
KEEPALIVE_ENABLED = os.getenv("KEEPALIVE_ENABLED", "true").lower() == "true"
KEEPALIVE_INTERVAL = int(os.getenv("KEEPALIVE_INTERVAL", "280"))

# ====== ثوابت منهجية الحصون الخمسة ======
# (لا تُغيّر هذه القيم دون فهم تأثيرها على دورات الحفظ والمراجعة)

QURAN_PAGE_COUNT = 604          # عدد أوجه المصحف
QURAN_HIZB_COUNT = 60          # عدد الأحزاب (كل حزب = 10 أوجه)
QURAN_JUZ_COUNT = 30           # عدد الأجزاء (كل جزء = 20 وجهًا)

DAILY_READING_HIZB = 2         # حزبا قراءة يوميًا
DAILY_READING_PAGES = 20       # = 2 حزب × 10 أوجه
READING_CYCLE_DAYS = 30        # 60 حزب ÷ 2 حزب/يوم = 30 يومًا للختمة

DAILY_LISTENING_HIZB = 1       # حزب استماع يوميًا
DAILY_LISTENING_PAGES = 10     # = 1 حزب × 10 أوجه
LISTENING_CYCLE_DAYS = 60      # 60 حزب ÷ 1 حزب/يوم = 60 يومًا للختمة

NEAR_REVISION_SIZE = 20        # نافذة المراجعة القريبة (آخر 20 وجهًا)
FAR_REVISION_SIZE = 40        # نطاق كل دورة مراجعة بعيدة (40 وجهًا)
PRE_SESSION_MINUTES = 15       # مدة التحضير القبلي

DEFAULT_DAILY_HIFZ_AMOUNT = 1  # الوجه الافتراضي اليومي للمبتدئ
DEFAULT_WEEKLY_HIFZ_AMOUNT = 7 # الأوجه الأسبوعية الافتراضية

# ====== أوقات التذكيرات الافتراضية (24 ساعة) ======
DEFAULT_REMINDER_TIMES = {
    "memorize":      "06:00",
    "reading":       "08:00",
    "weekly_prep":   "09:00",
    "pre_session":   "10:00",
    "listening":     "13:00",
    "near_review":   "16:00",
    "far_review":    "20:00",
    "nightly_prep":  "21:00",
}

REMINDER_TYPES = list(DEFAULT_REMINDER_TIMES.keys())
REMINDER_LABELS_AR = {
    "memorize":      "📚 الحفظ",
    "reading":       "📖 القراءة",
    "weekly_prep":   "📅 التحضير الأسبوعي",
    "pre_session":   "⏱️ التحضير القبلي",
    "listening":     "🎧 الاستماع",
    "near_review":   "🔄 مراجعة القريب",
    "far_review":    "🔁 مراجعة البعيد",
    "nightly_prep":  "🌙 التحضير الليلي",
}


def get_db_url_async() -> str:
    """يُعيد رابط PostgreSQL بصيغة asyncpg، أو SQLite بصيغة aiosqlite."""
    if not DATABASE_URL:
        # وضع الاختبار: قاعدة بيانات في الذاكرة
        return "sqlite+aiosqlite://"
    if DATABASE_URL.startswith("postgresql://"):
        return DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    if DATABASE_URL.startswith("file:"):
        return DATABASE_URL.replace("file:", "sqlite+aiosqlite:///", 1)
    if DATABASE_URL.startswith("sqlite://"):
        return DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return DATABASE_URL


def is_postgres() -> bool:
    return DATABASE_URL.startswith("postgresql://")
