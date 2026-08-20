"""
╔══════════════════════════════════════════════════════════════════╗
║                    بوت الحصون الخمسة — الإصدار 4.1.0                    ║
║                  Quran Fortresses Bot — Single File Edition                ║
╠══════════════════════════════════════════════════════════════════╣
║  مرافقك الشخصي لحفظ القرآن الكريم وفق منهج الحصون الخمسة.               ║
║                                                                    ║
║  المنهجية:                                                         ║
║    1. التهيئة    — قراءة (30 يوم) + استماع (60 يوم)                 ║
║    2. التحضير    — أسبوعي + ليلي + قبلي (15 دقيقة)                   ║
║    3. الحفظ      — الوجه القادم بناءً على التقدّم                     ║
║    4. القريب     — آخر 20 وجه محفوظ                                 ║
║    5. البعيد     — 40 وجه/دورة (دورات مستقلة)                       ║
║                                                                    ║
║  المعمارية: ملف واحد شامل — كل المنطق في هذا الملف.                  ║
║  التشغيل: python bot.py                                             ║
║  المتطلبات: python-telegram-bot, SQLAlchemy, APScheduler, aiohttp   ║
╚══════════════════════════════════════════════════════════════════╝
"""

# ═══════════════════════════════════════════
# ═══ الاستيرادات الخارجية الموحدة ═══
# ═══════════════════════════════════════════

# --- مكتبة Python القياسية ---
import os
import logging
import html
import re
import re as _re
import traceback
import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import date, date as date_cls, datetime, timedelta
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import sys

# --- مكتبات خارجية ---
import sqlalchemy
import aiohttp
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    delete,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.pool import StaticPool
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import (
    BadRequest,
    Conflict,
    Forbidden,
    NetworkError,
    TimedOut,
)
from telegram.ext import ContextTypes
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)



# ══════════════════════════════════════════════════════════════════════
# ═══ 1. الإعدادات والثوابت ═══
# المصدر: config.py
# ══════════════════════════════════════════════════════════════════════

"""
الإعدادات والثوابت
==================
كل الأرقام الجوهرية للمنهجية موجودة هنا — يمكن تعديلها لاحقًا دون البحث في الكود.
"""

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
    """يتحقق إذا كان رابط قاعدة البيانات هو PostgreSQL."""
    return DATABASE_URL.startswith(("postgresql://", "postgres://"))

# --- إنشاء كائن config كـ namespace ---
# كل الثوابت معرّفة مباشرة أعلاه، لكن بقية الكود يستخدم config.XXX
# فننشئ كائنًا بسيطًا يحتوي عليها كلها للتوافقية
import types as _types
config = _types.SimpleNamespace(
    BOT_TOKEN=BOT_TOKEN, DATABASE_URL=DATABASE_URL, ADMIN_ID=ADMIN_ID,
    DEFAULT_TIMEZONE=DEFAULT_TIMEZONE, PORT=PORT,
    RENDER_EXTERNAL_URL=RENDER_EXTERNAL_URL,
    KEEPALIVE_ENABLED=KEEPALIVE_ENABLED, KEEPALIVE_INTERVAL=KEEPALIVE_INTERVAL,
    QURAN_PAGE_COUNT=QURAN_PAGE_COUNT, QURAN_HIZB_COUNT=QURAN_HIZB_COUNT,
    QURAN_JUZ_COUNT=QURAN_JUZ_COUNT,
    DAILY_READING_HIZB=DAILY_READING_HIZB, DAILY_READING_PAGES=DAILY_READING_PAGES,
    READING_CYCLE_DAYS=READING_CYCLE_DAYS,
    DAILY_LISTENING_HIZB=DAILY_LISTENING_HIZB, DAILY_LISTENING_PAGES=DAILY_LISTENING_PAGES,
    LISTENING_CYCLE_DAYS=LISTENING_CYCLE_DAYS,
    NEAR_REVISION_SIZE=NEAR_REVISION_SIZE, FAR_REVISION_SIZE=FAR_REVISION_SIZE,
    PRE_SESSION_MINUTES=PRE_SESSION_MINUTES,
    DEFAULT_DAILY_HIFZ_AMOUNT=DEFAULT_DAILY_HIFZ_AMOUNT,
    DEFAULT_WEEKLY_HIFZ_AMOUNT=DEFAULT_WEEKLY_HIFZ_AMOUNT,
    DEFAULT_REMINDER_TIMES=DEFAULT_REMINDER_TIMES,
    REMINDER_TYPES=REMINDER_TYPES, REMINDER_LABELS_AR=REMINDER_LABELS_AR,
    get_db_url_async=get_db_url_async, is_postgres=is_postgres,
)
# cfg alias (بعض الملفات تستخدم import config as cfg)
cfg = config


# ══════════════════════════════════════════════════════════════════════
# ═══ 2. بيانات القرآن الكريم ═══
# المصدر: quran_data.py
# ══════════════════════════════════════════════════════════════════════

"""
بيانات القرآن الكريم
====================
- 604 صفحة (مصحف المدينة المنورة)
- 30 جزء (كل جزء = 20 صفحة)
- 60 حزب (كل حزب = 10 صفحات)
- روابط الاستماع (mp3quran.net)
"""


@dataclass(frozen=True)
class SurahInfo:
    number: int
    name_ar: str
    name_en: str
    page_start: int
    ayah_count: int


SURAHS: list[SurahInfo] = [
    SurahInfo(1, "الفاتحة", "Al-Fatihah", 1, 7),
    SurahInfo(2, "البقرة", "Al-Baqarah", 2, 286),
    SurahInfo(3, "آل عمران", "Aal-Imran", 50, 200),
    SurahInfo(4, "النساء", "An-Nisa", 77, 176),
    SurahInfo(5, "المائدة", "Al-Maidah", 106, 120),
    SurahInfo(6, "الأنعام", "Al-Anam", 128, 165),
    SurahInfo(7, "الأعراف", "Al-Araf", 151, 206),
    SurahInfo(8, "الأنفال", "Al-Anfal", 177, 75),
    SurahInfo(9, "التوبة", "At-Tawbah", 187, 129),
    SurahInfo(10, "يونس", "Yunus", 208, 109),
    SurahInfo(11, "هود", "Hud", 221, 123),
    SurahInfo(12, "يوسف", "Yusuf", 235, 111),
    SurahInfo(13, "الرعد", "Ar-Rad", 249, 43),
    SurahInfo(14, "إبراهيم", "Ibrahim", 255, 52),
    SurahInfo(15, "الحجر", "Al-Hijr", 262, 99),
    SurahInfo(16, "النحل", "An-Nahl", 267, 128),
    SurahInfo(17, "الإسراء", "Al-Isra", 282, 111),
    SurahInfo(18, "الكهف", "Al-Kahf", 293, 110),
    SurahInfo(19, "مريم", "Maryam", 305, 98),
    SurahInfo(20, "طه", "Taha", 312, 135),
    SurahInfo(21, "الأنبياء", "Al-Anbiya", 322, 112),
    SurahInfo(22, "الحج", "Al-Hajj", 332, 78),
    SurahInfo(23, "المؤمنون", "Al-Muminun", 342, 118),
    SurahInfo(24, "النور", "An-Nur", 350, 64),
    SurahInfo(25, "الفرقان", "Al-Furqan", 359, 77),
    SurahInfo(26, "الشعراء", "Ash-Shuara", 367, 227),
    SurahInfo(27, "النمل", "An-Naml", 377, 93),
    SurahInfo(28, "القصص", "Al-Qasas", 385, 88),
    SurahInfo(29, "العنكبوت", "Al-Ankabut", 396, 69),
    SurahInfo(30, "الروم", "Ar-Rum", 404, 60),
    SurahInfo(31, "لقمان", "Luqman", 411, 34),
    SurahInfo(32, "السجدة", "As-Sajdah", 415, 30),
    SurahInfo(33, "الأحزاب", "Al-Ahzab", 418, 73),
    SurahInfo(34, "سبأ", "Saba", 428, 54),
    SurahInfo(35, "فاطر", "Fatir", 434, 45),
    SurahInfo(36, "يس", "Ya-Sin", 440, 83),
    SurahInfo(37, "الصافات", "As-Saffat", 446, 182),
    SurahInfo(38, "ص", "Sad", 453, 88),
    SurahInfo(39, "الزمر", "Az-Zumar", 458, 75),
    SurahInfo(40, "غافر", "Ghafir", 467, 85),
    SurahInfo(41, "فصلت", "Fussilat", 477, 54),
    SurahInfo(42, "الشورى", "Ash-Shura", 483, 53),
    SurahInfo(43, "الزخرف", "Az-Zukhruf", 489, 89),
    SurahInfo(44, "الدخان", "Ad-Dukhan", 496, 59),
    SurahInfo(45, "الجاثية", "Al-Jathiyah", 499, 37),
    SurahInfo(46, "الأحقاف", "Al-Ahqaf", 502, 35),
    SurahInfo(47, "محمد", "Muhammad", 507, 38),
    SurahInfo(48, "الفتح", "Al-Fath", 511, 29),
    SurahInfo(49, "الحجرات", "Al-Hujurat", 515, 18),
    SurahInfo(50, "ق", "Qaf", 518, 45),
    SurahInfo(51, "الذاريات", "Adh-Dhariyat", 520, 60),
    SurahInfo(52, "الطور", "At-Tur", 523, 49),
    SurahInfo(53, "النجم", "An-Najm", 526, 62),
    SurahInfo(54, "القمر", "Al-Qamar", 528, 55),
    SurahInfo(55, "الرحمن", "Ar-Rahman", 531, 78),
    SurahInfo(56, "الواقعة", "Al-Waqiah", 534, 96),
    SurahInfo(57, "الحديد", "Al-Hadid", 537, 29),
    SurahInfo(58, "المجادلة", "Al-Mujadila", 542, 22),
    SurahInfo(59, "الحشر", "Al-Hashr", 545, 24),
    SurahInfo(60, "الممتحنة", "Al-Mumtahanah", 549, 13),
    SurahInfo(61, "الصف", "As-Saff", 551, 14),
    SurahInfo(62, "الجمعة", "Al-Jumuah", 553, 11),
    SurahInfo(63, "المنافقون", "Al-Munafiqun", 554, 11),
    SurahInfo(64, "التغابن", "At-Taghabun", 556, 18),
    SurahInfo(65, "الطلاق", "At-Talaq", 558, 12),
    SurahInfo(66, "التحريم", "At-Tahrim", 560, 12),
    SurahInfo(67, "الملك", "Al-Mulk", 562, 30),
    SurahInfo(68, "القلم", "Al-Qalam", 564, 52),
    SurahInfo(69, "الحاقة", "Al-Haqqah", 566, 52),
    SurahInfo(70, "المعارج", "Al-Maarij", 568, 44),
    SurahInfo(71, "نوح", "Nuh", 570, 28),
    SurahInfo(72, "الجن", "Al-Jinn", 572, 28),
    SurahInfo(73, "المزمل", "Al-Muzzammil", 574, 20),
    SurahInfo(74, "المدثر", "Al-Muddaththir", 575, 56),
    SurahInfo(75, "القيامة", "Al-Qiyamah", 577, 40),
    SurahInfo(76, "الإنسان", "Al-Insan", 578, 31),
    SurahInfo(77, "المرسلات", "Al-Mursalat", 580, 50),
    SurahInfo(78, "النبأ", "An-Naba", 582, 40),
    SurahInfo(79, "النازعات", "An-Naziat", 583, 46),
    SurahInfo(80, "عبس", "Abasa", 585, 42),
    SurahInfo(81, "التكوير", "At-Takwir", 586, 29),
    SurahInfo(82, "الانفطار", "Al-Infitar", 587, 19),
    SurahInfo(83, "المطففين", "Al-Mutaffifin", 587, 36),
    SurahInfo(84, "الانشقاق", "Al-Inshiqaq", 589, 25),
    SurahInfo(85, "البروج", "Al-Buruj", 590, 22),
    SurahInfo(86, "الطارق", "At-Tariq", 591, 17),
    SurahInfo(87, "الأعلى", "Al-Ala", 591, 19),
    SurahInfo(88, "الغاشية", "Al-Ghashiyah", 592, 26),
    SurahInfo(89, "الفجر", "Al-Fajr", 593, 30),
    SurahInfo(90, "البلد", "Al-Balad", 594, 20),
    SurahInfo(91, "الشمس", "Ash-Shams", 595, 15),
    SurahInfo(92, "الليل", "Al-Layl", 595, 21),
    SurahInfo(93, "الضحى", "Ad-Duha", 596, 11),
    SurahInfo(94, "الشرح", "Ash-Sharh", 596, 8),
    SurahInfo(95, "التين", "At-Tin", 597, 8),
    SurahInfo(96, "العلق", "Al-Alaq", 597, 19),
    SurahInfo(97, "القدر", "Al-Qadr", 598, 5),
    SurahInfo(98, "البينة", "Al-Bayyinah", 598, 8),
    SurahInfo(99, "الزلزلة", "Az-Zalzalah", 599, 8),
    SurahInfo(100, "العاديات", "Al-Adiyat", 599, 11),
    SurahInfo(101, "القارعة", "Al-Qariah", 600, 11),
    SurahInfo(102, "التكاثر", "At-Takathur", 600, 8),
    SurahInfo(103, "العصر", "Al-Asr", 601, 3),
    SurahInfo(104, "الهمزة", "Al-Humazah", 601, 9),
    SurahInfo(105, "الفيل", "Al-Fil", 601, 5),
    SurahInfo(106, "قريش", "Quraysh", 602, 4),
    SurahInfo(107, "الماعون", "Al-Maun", 602, 7),
    SurahInfo(108, "الكوثر", "Al-Kawthar", 602, 3),
    SurahInfo(109, "الكافرون", "Al-Kafirun", 603, 6),
    SurahInfo(110, "النصر", "An-Nasr", 603, 3),
    SurahInfo(111, "المسد", "Al-Masad", 603, 5),
    SurahInfo(112, "الإخلاص", "Al-Ikhlas", 604, 4),
    SurahInfo(113, "الفلق", "Al-Falaq", 604, 5),
    SurahInfo(114, "الناس", "An-Nas", 604, 6),
]

TOTAL_PAGES = 604
TOTAL_JUZ = 30
TOTAL_HIZB = 60


def page_to_juz(page: int) -> int:
    if page < 1:
        return 1
    if page >= TOTAL_PAGES:
        return TOTAL_JUZ
    return ((page - 1) // 20) + 1


def page_to_hizb(page: int) -> int:
    if page < 1:
        return 1
    if page >= TOTAL_PAGES:
        return TOTAL_HIZB
    return ((page - 1) // 10) + 1


def juz_pages(juz: int) -> tuple[int, int]:
    juz = max(1, min(juz, TOTAL_JUZ))
    start = (juz - 1) * 20 + 1
    end = start + 19
    if juz == TOTAL_JUZ:
        end = TOTAL_PAGES
    return start, end


def hizb_pages(hizb: int) -> tuple[int, int]:
    hizb = max(1, min(hizb, TOTAL_HIZB))
    start = (hizb - 1) * 10 + 1
    end = start + 9
    if hizb == TOTAL_HIZB:
        end = TOTAL_PAGES
    return start, end


def page_to_surah(page: int) -> SurahInfo | None:
    if page < 1 or page > TOTAL_PAGES:
        return None
    result = SURAHS[0]
    for s in SURAHS:
        if s.page_start <= page:
            result = s
        else:
            break
    return result


def get_surah_by_name(name: str) -> SurahInfo | None:
    """بحث بالاسم العربي (مطابق جزئي)"""
    name = name.strip()
    for s in SURAHS:
        if s.name_ar == name or name in s.name_ar or s.name_ar in name:
            return s
    return None


def get_surah_by_number(num: int) -> SurahInfo | None:
    for s in SURAHS:
        if s.number == num:
            return s
    return None


# ====== روابط الاستماع ======
RECITERS = {
    "الحصري": "https://server8.mp3quran.net/afs/",
    "العجمي": "https://server7.mp3quran.net/afs/",
    "المعيقلي": "https://server11.mp3quran.net/maher/",
    "عبد الباسط": "https://server7.mp3quran.net/basit/",
    "السديس": "https://server13.mp3quran.net/sds/",
    "الحذيفي": "https://server7.mp3quran.net/hthfi/",
}


def get_surah_audio_url(surah_number: int, reciter: str = "الحصري") -> str | None:
    base = RECITERS.get(reciter, RECITERS["الحصري"])
    return f"{base}{surah_number:03d}.mp3"


def get_page_audio_url(page: int) -> str | None:
    surah = page_to_surah(page)
    if surah:
        return get_surah_audio_url(surah.number)
    return None


def get_quran_text_url(page: int) -> str:
    return f"https://quran.com/page/{page}"

# --- إنشاء كائن quran_data كـ namespace ---
# كل الدوال والثوابت معرّفة مباشرة أعلاه، لكن بقية الكود يستخدم quran_data.XXX
quran_data = _types.SimpleNamespace(
    SURAHS=SURAHS, TOTAL_PAGES=TOTAL_PAGES, TOTAL_JUZ=TOTAL_JUZ, TOTAL_HIZB=TOTAL_HIZB,
    RECITERS=RECITERS,
    page_to_juz=page_to_juz, page_to_hizb=page_to_hizb,
    juz_pages=juz_pages, hizb_pages=hizb_pages,
    page_to_surah=page_to_surah, get_surah_by_name=get_surah_by_name,
    get_surah_by_number=get_surah_by_number,
    get_surah_audio_url=get_surah_audio_url, get_page_audio_url=get_page_audio_url,
    get_quran_text_url=get_quran_text_url,
)


# ══════════════════════════════════════════════════════════════════════
# ═══ 3. نماذج قاعدة البيانات ═══
# المصدر: models.py
# ══════════════════════════════════════════════════════════════════════

"""
نماذج قاعدة البيانات (SQLAlchemy 2.0 — DeclarativeBase)
=====================================================

الجداول:
    User                — المستخدم + الإعدادات + حالة الحفظ
    UserSettings        — أوقات التذكيرات الـ 8 (منفصلة لقابلية التوسع)
    DailyProgress       — حالة إنجاز المهام لكل يوم
    MemorizationLog     — سجل دائم لكل وجه حُفظ (مع التاريخ والمراجعات)
    ActivityLog         — سجل أحداث يومي مختصر
    FarReviewCycle      — حالة دورة المراجعة البعيدة (مستقلة عن الحفظ)
"""




class Base(DeclarativeBase):
    pass


class User(Base):
    """المستخدم الرئيسي — يحمل كل الحالة المركزية للحفظ."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default=config.DEFAULT_TIMEZONE)

    # ====== حالة الحفظ ======
    last_hifz_page: Mapped[int] = mapped_column(Integer, default=0)  # آخر وجه محفوظ
    next_hifz_page: Mapped[int] = mapped_column(Integer, default=1)  # الوجه القادم للحفظ
    daily_hifz_amount: Mapped[int] = mapped_column(Integer, default=config.DEFAULT_DAILY_HIFZ_AMOUNT)
    weekly_hifz_amount: Mapped[int] = mapped_column(Integer, default=config.DEFAULT_WEEKLY_HIFZ_AMOUNT)
    plan_start_date: Mapped[date] = mapped_column(Date, default=date.today)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False)

    # ====== دورة القراءة (الحصن الأول) ======
    reading_hizb_current: Mapped[int] = mapped_column(Integer, default=1)  # الحزب الحالي للقراءة
    reading_khatmah_count: Mapped[int] = mapped_column(Integer, default=0)  # عدد الختمات المنجزة

    # ====== دورة الاستماع (الحصن الأول) ======
    listening_hizb_current: Mapped[int] = mapped_column(Integer, default=1)
    listening_khatmah_count: Mapped[int] = mapped_column(Integer, default=0)

    # ====== الالتزام ======
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_active_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # ====== التحضير الأسبوعي (محسوب ديناميكيًا، يُخزَّن فقط للتسريع) ======
    weekly_prep_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    weekly_prep_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ====== التحضير القبلي ======
    pre_session_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ====== الطوابع الزمنية ======
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # العلاقات
    settings_rel: Mapped[list["UserSettings"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    daily_progress: Mapped[list["DailyProgress"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    far_review_state: Mapped[Optional["FarReviewCycle"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserSettings(Base):
    """أوقات التذكيرات الـ 8 — قابلة للتخصيص لكل مستخدم."""
    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", "reminder_type", name="uq_user_reminder"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reminder_type: Mapped[str] = mapped_column(String(32))  # memorize / reading / ...
    reminder_time: Mapped[str] = mapped_column(String(5))   # HH:MM
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="settings_rel")


class DailyProgress(Base):
    """حالة المهام لكل يوم — يجيب عن: ماذا أنجزت اليوم؟"""
    __tablename__ = "daily_progress"
    __table_args__ = (UniqueConstraint("user_id", "progress_date", name="uq_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    progress_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)

    # المهام الـ 8
    reading_done: Mapped[bool] = mapped_column(Boolean, default=False)
    listening_done: Mapped[bool] = mapped_column(Boolean, default=False)
    weekly_prep_done: Mapped[bool] = mapped_column(Boolean, default=False)
    nightly_prep_done: Mapped[bool] = mapped_column(Boolean, default=False)
    pre_session_prep_done: Mapped[bool] = mapped_column(Boolean, default=False)
    memorize_done: Mapped[bool] = mapped_column(Boolean, default=False)
    near_review_done: Mapped[bool] = mapped_column(Boolean, default=False)
    far_review_done: Mapped[bool] = mapped_column(Boolean, default=False)

    # مدة التحضير القبلي
    pre_session_duration_min: Mapped[int] = mapped_column(Integer, default=0)

    # الحالة الإجمالية: pending / partial / completed / postponed / missed
    task_status: Mapped[str] = mapped_column(String(16), default="pending")

    user: Mapped["User"] = relationship(back_populates="daily_progress")


class MemorizationLog(Base):
    """سجل دائم لكل وجه حُفظ — يُستخدم لحساب المراجعات والاحصائيات."""
    __tablename__ = "memorization_log"
    __table_args__ = (UniqueConstraint("user_id", "page_number", name="uq_user_page"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, index=True)
    date_memorized: Mapped[date] = mapped_column(Date, default=date.today)
    review_count: Mapped[int] = mapped_column(Integer, default=0)


class ActivityLog(Base):
    """سجل مختصر لكل حدث مهم — للعرض التاريخي واكتشاف الأنماط."""
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    log_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    log_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    event_type: Mapped[str] = mapped_column(String(32))  # memorize / reading_done / setting_change / ...
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class FarReviewCycle(Base):
    """حالة دورة المراجعة البعيدة — مستقلة عن الحفظ.
    
    لماذا جدول مستقل؟
    لأن المستخدم قد يواصل الحفظ (يتقدّم last_hifz_page) بينما لا يزال يراجع
    دورة قديمة. لا يمكن اشتقاق هذا من الحفظ فقط.
    """
    __tablename__ = "far_review_cycle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    current_cycle: Mapped[int] = mapped_column(Integer, default=1)
    cycle_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cycle_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_completed_cycle: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="far_review_state")


# ====== Migration statements (آمنة — IF NOT EXISTS) ======
MIGRATION_STATEMENTS = [
    # users
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_hifz_page INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS next_hifz_page INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_hifz_amount INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_hifz_amount INTEGER DEFAULT 7",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_start_date DATE DEFAULT CURRENT_DATE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_done BOOLEAN DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS reading_hizb_current INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS reading_khatmah_count INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS listening_hizb_current INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS listening_khatmah_count INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS streak_days INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_date DATE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS notifications_enabled BOOLEAN DEFAULT TRUE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_prep_start INTEGER",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_prep_end INTEGER",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS pre_session_started_at TIMESTAMP",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) DEFAULT 'Africa/Algiers'",
    # daily_progress
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS weekly_prep_done BOOLEAN DEFAULT FALSE",
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS nightly_prep_done BOOLEAN DEFAULT FALSE",
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS pre_session_prep_done BOOLEAN DEFAULT FALSE",
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS pre_session_duration_min INTEGER DEFAULT 0",
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS near_review_done BOOLEAN DEFAULT FALSE",
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS far_review_done BOOLEAN DEFAULT FALSE",
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS task_status VARCHAR(16) DEFAULT 'pending'",
]

# ══════════════════════════════════════════════════════════════════════
# ═══ 4. طبقة قاعدة البيانات ═══
# المصدر: database.py
# ══════════════════════════════════════════════════════════════════════

"""
طبقة قاعدة البيانات: إنشاء المحرك، الجلسات، التهيئة الآمنة.
"""



logger = logging.getLogger(__name__)

# إزالة المعلمات غير المتوافقة مع asyncpg
_FORBIDDEN_PARAMS = {"sslmode", "channel_binding", "sslrootcert", "sslcert", "sslkey"}


def _strip_forbidden_params(url: str) -> str:
    if not url.startswith("postgresql://"):
        return url
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    for key in _FORBIDDEN_PARAMS:
        query.pop(key, None)
    new_query = urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


def _build_async_url() -> str:
    url = config.DATABASE_URL
    if not url:
        return "sqlite+aiosqlite:///:memory:"  # in-memory
    if url.startswith("postgresql://"):
        url = _strip_forbidden_params(url)
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("file:"):
        return url.replace("file:", "sqlite+aiosqlite:///", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


DB_ASYNC_URL = _build_async_url()

# محرك قاعدة البيانات
# ملاحظة: SQLite (سواء في الذاكرة أو ملف) لا يدعم pool_size/max_overflow —
# نستخدم StaticPool للذاكرة، ونُلغي pool_size للملف.
_is_sqlite = DB_ASYNC_URL.startswith("sqlite+aiosqlite")
_is_sqlite_mem = _is_sqlite and (":memory:" in DB_ASYNC_URL or DB_ASYNC_URL.endswith("sqlite+aiosqlite://"))


def _create_engine():
    """يُنشئ محرك قاعدة بيانات جديد — يُستدعى عند التهيئة وإعادة التهيئة للاختبارات."""
    if _is_sqlite_mem:
        return create_async_engine(
            DB_ASYNC_URL,
            echo=False,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    if _is_sqlite:
        # SQLite قائم على ملف — لا حاجة لـ pool_size/max_overflow
        return create_async_engine(
            DB_ASYNC_URL,
            echo=False,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )
    # PostgreSQL (asyncpg)
    return create_async_engine(
        DB_ASYNC_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


# المحرك الافتراضي (يُعاد إنشاؤه عند الطلب في init_db إذا كان مُغلَّلاً)
engine = _create_engine()
_disposed = False

# AsyncSessionLocal المُعاد تصديره — نستخدم دالة بديلة لإعادة التقييم ديناميكيًا
# (لأن الاختبارات تستورده مرة واحدة، ثم تستدعي close_db/init_db بين الاختبارات)
_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class _SessionLocalProxy:
    """وسيط ديناميكي يُعيد توجيه الاستدعاءات إلى أحدث AsyncSessionLocal."""
    def __call__(self, *args, **kwargs):
        return _session_maker(*args, **kwargs)
    def __getattr__(self, name):
        return getattr(_session_maker, name)


# الواجهة العامة (تُحدَّث عند إعادة التهيئة)
AsyncSessionLocal = _SessionLocalProxy()


async def init_db():
    """تهيئة قاعدة البيانات — migrations و create_all في معاملات منفصلة.

    نقطة حرجة: في PostgreSQL، إذا فشل أي statement في معاملة، تصبح المعاملة
    "aborted" وكل التغييرات تُتراجع عند الـ commit. لذا يجب فصل migrations
    عن create_all في معاملات منفصلة، وإلا فقد تُتراجع migrations إذا فشل create_all.

    الترتيب:
    1. معاملة منفصلة: MIGRATION_STATEMENTS (ALTER TABLE ADD COLUMN IF NOT EXISTS)
    2. معاملة منفصلة: Base.metadata.create_all (ينشئ الجداول الجديدة فقط)
    """
    global engine, _session_maker, _disposed
    if _disposed:
        engine = _create_engine()
        _session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        _disposed = False


    # تسجيل تشخيصي: نوع قاعدة البيانات
    is_pg = config.is_postgres()
    logger.info(f"📋 نوع قاعدة البيانات: {'PostgreSQL' if is_pg else 'SQLite'}")
    logger.info(f"📋 رابط قاعدة البيانات: {config.DATABASE_URL[:30]}...")

    # ── المعاملة 1: migrations ──
    # كل ALTER TABLE ADD COLUMN IF NOT EXISTS في معاملته الخاصة
    # (إذا فشلت واحدة، لا تؤثر على الباقي)
    if is_pg:
        logger.info(f"📋 تنفيذ {len(MIGRATION_STATEMENTS)} جملة migration...")
        success_count = 0
        for stmt in MIGRATION_STATEMENTS:
            try:
                async with engine.begin() as conn:
                    await conn.execute(sqlalchemy.text(stmt))
                success_count += 1
            except Exception as e:
                logger.debug(f"migration skip: {stmt[:60]}... → {e}")
        logger.info(f"✅ migrations: {success_count}/{len(MIGRATION_STATEMENTS)} نجحت")

    # ── المعاملة 2: create_all ──
    # ينشئ الجداول الجديدة فقط (checkfirst=True). في معاملة منفصلة تمامًا.
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ create_all اكتمل")
    except Exception as e:
        logger.warning(f"⚠️ create_all تخطّى بعض العناصر: {e}")

    # ── التحقق: هل الأعمدة موجودة فعلاً؟ ──
    if is_pg:
        try:
            async with engine.begin() as conn:
                result = await conn.execute(sqlalchemy.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='users' AND column_name='last_hifz_page'"
                ))
                row = result.first()
                if row:
                    logger.info("✅ التحقق: عمود last_hifz_page موجود في جدول users")
                else:
                    logger.error("❌ التحقق: عمود last_hifz_page غير موجود بعد!")
        except Exception as e:
            logger.warning(f"⚠️ تعذّر التحقق من الأعمدة: {e}")

    logger.info("✅ تم تهيئة قاعدة البيانات")


async def close_db():
    global _disposed
    await engine.dispose()
    _disposed = True
    logger.info("✅ تم إغلاق قاعدة البيانات")


async def ensure_default_reminders(user_id: int):
    """تأكد من وجود 8 تذكيرات افتراضية لكل مستخدم."""

    async with AsyncSessionLocal() as session:
        # هل توجد تذكيرات أصلاً؟
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        existing = result.scalars().all()
        if existing:
            return  # تذكيرات موجودة بالفعل

        # إنشاء التذكيرات الافتراضية
        for reminder_type, default_time in cfg.DEFAULT_REMINDER_TIMES.items():
            session.add(UserSettings(
                user_id=user_id,
                reminder_type=reminder_type,
                reminder_time=default_time,
                enabled=True,
            ))
        await session.commit()

# ══════════════════════════════════════════════════════════════════════
# ═══ 5. محرك الحفظ (الحصن الثالث) ═══
# المصدر: hifz_engine.py
# ══════════════════════════════════════════════════════════════════════

"""
محرك الحفظ — الحصن الثالث
========================
القواعد الديترمية:
    next_hifz_page = last_hifz_page + 1  (أو 1 إذا لم يسبق الحفظ)
    إذا daily_hifz_amount = 1: نحفظ الوجه next_hifz_page
    إذا daily_hifz_amount = 2: نحفظ الوجهين next_hifz_page و next_hifz_page+1

بعد تأكيد الحفظ:
    last_hifz_page += daily_hifz_amount
    next_hifz_page = last_hifz_page + 1

لا يتم تحريك الحفظ تلقائيًا إذا فات المستخدم يومًا — يبقى نفس الوجه مطلوبًا.
"""


def get_today_hifz_assignment(user: User) -> dict:
    """المطلوب حفظه اليوم بناءً على حالة المستخدم."""
    last = user.last_hifz_page or 0
    amount = max(1, user.daily_hifz_amount or 1)
    next_page = last + 1

    if last >= config.QURAN_PAGE_COUNT:
        return {
            "pages": [],
            "start": None,
            "end": None,
            "completed_quran": True,
            "last_hifz_page": last,
            "next_hifz_page": None,
        }

    pages = list(range(next_page, min(next_page + amount, config.QURAN_PAGE_COUNT + 1)))
    end_page = pages[-1] if pages else None

    return {
        "pages": pages,
        "start": pages[0] if pages else None,
        "end": end_page,
        "completed_quran": False,
        "last_hifz_page": last,
        "next_hifz_page": next_page,
    }


def confirm_memorization(user: User) -> dict:
    """تأكيد الحفظ — يحرّك last_hifz_page للأمام بمقدار daily_hifz_amount.
    
    ملاحظة: لا نحذف last_hifz_page أبدًا — فقط نتقدّم للأمام.
    إذا أراد المستخدم التراجع، يُعدّل يدويًا من لوحة "تعديل التقدم".
    """
    assignment = get_today_hifz_assignment(user)
    if assignment["completed_quran"]:
        return {"success": False, "reason": "completed_quran", "message": "أكملتِ القرآن كله 🎉"}

    amount = len(assignment["pages"])
    if amount == 0:
        return {"success": False, "reason": "no_pages", "message": "لا توجد أوجه للحفظ"}

    new_last = assignment["end"]
    user.last_hifz_page = new_last
    user.next_hifz_page = new_last + 1
    # تحديث نطاق التحضير الأسبوعي = الأسبوع القادم (بعد تجاوز مقدار الأسبوع الحالي)
    weekly_amount = user.weekly_hifz_amount or config.DEFAULT_WEEKLY_HIFZ_AMOUNT
    this_week_start = new_last + 1  # بداية الأسبوع الحالي الجديد بعد التقدّم
    user.weekly_prep_start = this_week_start + weekly_amount
    user.weekly_prep_end = min(
        config.QURAN_PAGE_COUNT,
        user.weekly_prep_start + weekly_amount - 1,
    )

    return {
        "success": True,
        "memorized_pages": assignment["pages"],
        "new_last_page": new_last,
        "next_hifz_page": new_last + 1,
    }


def set_last_hifz_page(user: User, page: int) -> dict:
    """تعديل يدوي لآخر وجه محفوظ — يُعيد حساب كل المهام المعتمدة عليه."""
    page = max(0, min(int(page), config.QURAN_PAGE_COUNT))
    user.last_hifz_page = page
    user.next_hifz_page = page + 1 if page < config.QURAN_PAGE_COUNT else page
    # التحضير الأسبوعي = الأسبوع القادم (بعد تجاوز مقدار الأسبوع الحالي)
    weekly_amount = user.weekly_hifz_amount or config.DEFAULT_WEEKLY_HIFZ_AMOUNT
    this_week_start = page + 1 if page < config.QURAN_PAGE_COUNT else page
    user.weekly_prep_start = this_week_start + weekly_amount
    user.weekly_prep_end = min(
        config.QURAN_PAGE_COUNT,
        user.weekly_prep_start + weekly_amount - 1,
    )
    return {
        "last_hifz_page": user.last_hifz_page,
        "next_hifz_page": user.next_hifz_page,
        "weekly_prep_start": user.weekly_prep_start,
        "weekly_prep_end": user.weekly_prep_end,
    }

# ══════════════════════════════════════════════════════════════════════
# ═══ 6. محرك القراءة (الحصن الأول) ═══
# المصدر: reading_engine.py
# ══════════════════════════════════════════════════════════════════════

"""
محرك القراءة — الحصن الأول (أ. ختمة القراءة)
==========================================
دورة 30 يومًا، حزبان/يوم = 60 حزبًا = ختمة كاملة.
يبدأ من الحزب 1، بعد الحزب 60 يعود للحزب 1.
يحفظ موضع القراءة الحالي بشكل دائم في user.reading_hizb_current.
"""


def hizb_to_pages(hizb: int) -> tuple[int, int]:
    """حوّل رقم الحزب (1-60) إلى نطاق الأوجه (10 أوجه لكل حزب)."""
    hizb = max(1, min(hizb, config.QURAN_HIZB_COUNT))
    start = (hizb - 1) * config.DAILY_LISTENING_PAGES + 1
    end = start + config.DAILY_LISTENING_PAGES - 1
    return start, end


def get_reading_assignment(user: User) -> dict:
    """الورد اليومي للقراءة: حزبان متتاليان (مع لفّ دائري)."""
    start_hizb = user.reading_hizb_current or 1
    h1 = max(1, min(start_hizb, config.QURAN_HIZB_COUNT))
    h2 = (h1 % config.QURAN_HIZB_COUNT) + 1  # حزب اليوم التالي (مع لفّ)

    p1_start, p1_end = hizb_to_pages(h1)
    p2_start, p2_end = hizb_to_pages(h2)

    return {
        "hizb_list": [h1, h2],
        "pages_start": p1_start,
        "pages_end": p2_end,
        "current_hizb": h1,
        "next_hizb": (h2 % config.QURAN_HIZB_COUNT) + 1,
    }


def advance_reading(user: User) -> bool:
    """تأكيد إنجاز القراءة — ينتقل للحزب التالي (مع لفّ بعد 60).
    
    قراءة اليوم = current_hizb و second_hizb (الذي قد يلتف).
    إذا تضمّنت قراءة اليوم الحزب 60، تُحسب ختمة كاملة.
    """
    current = user.reading_hizb_current or 1
    # الحزبان اللذان قُرئا اليوم: current و (current % 60) + 1
    second_hizb = (current % config.QURAN_HIZB_COUNT) + 1
    # إذا ضمّت القراءة الحزب 60 → ختمة كاملة
    completed_khatmah = (current == config.QURAN_HIZB_COUNT) or (second_hizb == config.QURAN_HIZB_COUNT)

    # الحزب التالي = current + 2 (مع لفّ)
    next_hizb = ((current + config.DAILY_READING_HIZB - 1) % config.QURAN_HIZB_COUNT) + 1
    user.reading_hizb_current = next_hizb

    if completed_khatmah:
        user.reading_khatmah_count = (user.reading_khatmah_count or 0) + 1
        return True
    return False


def get_reading_cycle_info(user: User) -> dict:
    """معلومات الدورة: أي حزب نحن فيه، نسبة الإنجاز في الختمة الحالية."""
    current = user.reading_hizb_current or 1
    completed_hizb = current - 1
    total_hizb = config.QURAN_HIZB_COUNT
    percent = (completed_hizb / total_hizb) * 100
    khatmah_count = user.reading_khatmah_count or 0
    return {
        "current_hizb": current,
        "completed_in_cycle": completed_hizb,
        "total_in_cycle": total_hizb,
        "percent": round(percent, 1),
        "khatmah_count": khatmah_count,
        "current_khatmah_number": khatmah_count + 1,
    }

# ══════════════════════════════════════════════════════════════════════
# ═══ 7. محرك الاستماع (الحصن الأول) ═══
# المصدر: listening_engine.py
# ══════════════════════════════════════════════════════════════════════

"""
محرك الاستماع — الحصن الأول (ب. ختمة الاستماع)
=============================================
دورة 60 يومًا، حزب/يوم = 60 حزبًا = ختمة كاملة.
مستقلة تمامًا عن القراءة.
"""


def get_listening_assignment(user: User) -> dict:
    """الاستماع اليومي: حزب واحد (مع لفّ دائري)."""
    hizb = user.listening_hizb_current or 1
    h = max(1, min(hizb, config.QURAN_HIZB_COUNT))
    p_start, p_end = hizb_to_pages(h)

    return {
        "hizb": h,
        "pages_start": p_start,
        "pages_end": p_end,
        "next_hizb": (h % config.QURAN_HIZB_COUNT) + 1,
    }


def advance_listening(user: User) -> bool:
    """تأكيد إنجاز الاستماع — ينتقل للحزب التالي."""
    next_hizb = ((user.listening_hizb_current or 1) % config.QURAN_HIZB_COUNT) + 1
    user.listening_hizb_current = next_hizb

    if next_hizb == 1:
        user.listening_khatmah_count = (user.listening_khatmah_count or 0) + 1
        return True
    return False


def get_listening_cycle_info(user: User) -> dict:
    """معلومات دورة الاستماع."""
    current = user.listening_hizb_current or 1
    completed = current - 1
    total = config.QURAN_HIZB_COUNT
    percent = (completed / total) * 100
    khatmah = user.listening_khatmah_count or 0
    return {
        "current_hizb": current,
        "completed_in_cycle": completed,
        "total_in_cycle": total,
        "percent": round(percent, 1),
        "khatmah_count": khatmah,
        "current_khatmah_number": khatmah + 1,
    }

# ══════════════════════════════════════════════════════════════════════
# ═══ 8. محرك المراجعات (الحصن الرابع+الخامس) ═══
# المصدر: revision_engine.py
# ══════════════════════════════════════════════════════════════════════

"""
محرك المراجعات — الحصن الرابع (القريب) + الحصن الخامس (البعيد)
=============================================================

الحصن الرابع: نافذة متحركة آخر 20 وجهًا من المحفوظ.
    near_start = max(1, last_hifz_page - 19)
    near_end   = last_hifz_page

الحصن الخامس: 40 وجهًا لكل دورة، مستقلة عن الحفظ.
    نحفظ حالة الدورة في جدول FarReviewCycle.
    عند الإنتهاء، ننتقل للدورة التالية (ننزل في الأرقام).
"""



# ====== الحصن الرابع: مراجعة القريب ======

def get_near_review_range(user: User) -> dict:
    """نطاق مراجعة القريب = آخر 20 وجهًا من المحفوظ.
    
    إذا كان المحفوظ أقل من 20 وجه، يبدأ من 1.
    إذا لم يحفظ المستخدم شيئًا، يعود None.
    """
    last = user.last_hifz_page or 0
    if last == 0:
        return {"applicable": False, "start": None, "end": None, "count": 0}

    near_start = max(1, last - (config.NEAR_REVISION_SIZE - 1))
    near_end = last
    count = near_end - near_start + 1
    return {
        "applicable": True,
        "start": near_start,
        "end": near_end,
        "count": count,
    }


# ====== الحصن الخامس: مراجعة البعيد ======

def _compute_total_far_cycles(last_hifz_page: int) -> int:
    """عدد دورات المراجعة البعيدة الكلية.
    
    القاعدة: كل دورة = 40 وجه. الدورة 1 = الأحدث (آخر 40 محفوظ).
    دورات البعيد تبدأ من آخر وجه محفوظ وتنزل للوراء.
    مثال: last=120 → 3 دورات (81→120, 41→80, 1→40)
    مثال: last=40 → 1 دورة (1→40)
    مثال: last=25 → 1 دورة (1→25)
    """
    if last_hifz_page <= 0:
        return 0
    cycles = (last_hifz_page + config.FAR_REVISION_SIZE - 1) // config.FAR_REVISION_SIZE
    return cycles


def _compute_cycle_range(last_hifz_page: int, cycle_number: int) -> tuple[int, int]:
    """احسب نطاق دورة بعيدة معيّنة.
    
    الترتيب: الدورة 1 = الأحدث (تنتهي عند last_hifz_page)، الدورة N = الأقدم (تبدأ من 1).
    
    مثال: last=120، FAR_SIZE=40
      الدورة 1 = 81→120  (الأحدث)
      الدورة 2 = 41→80
      الدورة 3 = 1→40    (الأقدم)
    """
    if last_hifz_page <= 0:
        return (None, None)

    # نهاية الدورة N = last - (N-1) * 40
    end_of_cycle = last_hifz_page - (cycle_number - 1) * config.FAR_REVISION_SIZE
    start_of_cycle = end_of_cycle - config.FAR_REVISION_SIZE + 1

    # قص على الحدود
    start_of_cycle = max(1, start_of_cycle)
    end_of_cycle = max(start_of_cycle, end_of_cycle)

    return (start_of_cycle, end_of_cycle)


async def get_far_review_state(session: AsyncSession, user: User) -> dict:
    """يُعيد حالة دورة المراجعة البعيدة كاملة.
    
    إذا لم يكن للمستخدم حالة بعد، نُنشئها تلقائيًا.
    """
    last = user.last_hifz_page or 0
    if last == 0:
        return {
            "applicable": False,
            "current_cycle": 0,
            "total_cycles": 0,
            "cycle_start": None,
            "cycle_end": None,
            "last_completed_cycle": 0,
        }

    result = await session.execute(
        select(FarReviewCycle).where(FarReviewCycle.user_id == user.id)
    )
    state = result.scalar_one_or_none()

    total_cycles = _compute_total_far_cycles(last)
    if total_cycles == 0:
        return {
            "applicable": False,
            "current_cycle": 0,
            "total_cycles": 0,
            "cycle_start": None,
            "cycle_end": None,
            "last_completed_cycle": 0,
        }

    if state is None:
        # إنشاء الحالة الافتراضية: الدورة 1 (الأحدث)
        state = FarReviewCycle(
            user_id=user.id,
            current_cycle=1,
            last_completed_cycle=0,
        )
        session.add(state)
        await session.commit()
        await session.refresh(state)

    # التحقق من صحة current_cycle ضمن النطاق
    if state.current_cycle > total_cycles:
        state.current_cycle = 1  # إعادة الضبط للدورة الأولى
        await session.commit()

    cycle_start, cycle_end = _compute_cycle_range(last, state.current_cycle)

    return {
        "applicable": True,
        "current_cycle": state.current_cycle,
        "total_cycles": total_cycles,
        "cycle_start": cycle_start,
        "cycle_end": cycle_end,
        "last_completed_cycle": state.last_completed_cycle,
    }


async def advance_far_review_cycle(session: AsyncSession, user: User) -> dict:
    """إتمام دورة المراجعة البعيدة الحالية — الانتقال للدورة التالية.
    
    الترتيب: 1 → 2 → ... → N → 1 (دائري).
    """
    state_info = await get_far_review_state(session, user)
    if not state_info["applicable"]:
        return {"success": False, "reason": "not_applicable"}

    total = state_info["total_cycles"]
    current = state_info["current_cycle"]

    result = await session.execute(
        select(FarReviewCycle).where(FarReviewCycle.user_id == user.id)
    )
    state = result.scalar_one_or_none()
    if state is None:
        return {"success": False, "reason": "no_state"}

    state.last_completed_cycle = current
    state.current_cycle = (current % total) + 1  # دوري
    new_start, new_end = _compute_cycle_range(user.last_hifz_page or 0, state.current_cycle)
    state.cycle_start = new_start
    state.cycle_end = new_end
    await session.commit()
    await session.refresh(state)

    return {
        "success": True,
        "new_cycle": state.current_cycle,
        "new_cycle_start": new_start,
        "new_cycle_end": new_end,
    }

# ══════════════════════════════════════════════════════════════════════
# ═══ 9. محرك التحضير (الحصن الثاني) ═══
# المصدر: prep_engine.py
# ══════════════════════════════════════════════════════════════════════

"""
محرك التحضير — الحصن الثاني (أسبوعي + ليلي + قبلي)
==================================================

التحضير الأسبوعي:
    - نطاق الأوجه التي سيحفظها المستخدم خلال الأسبوع القادم (وليس الأسبوع الحالي)
    - محسوب ديناميكيًا من next_hifz_page + weekly_hifz_amount
    - يُحدَّث تلقائيًا عند تغيير weekly_hifz_amount أو تأكيد الحفظ

    القاعدة الحسابية:
        this_week_start = last_hifz_page + 1        (= next_hifz_page)
        this_week_end   = this_week_start + weekly_hifz_amount - 1
        weekly_prep_start = this_week_start + weekly_hifz_amount
        weekly_prep_end   = weekly_prep_start + weekly_hifz_amount - 1

    مثال: last_hifz=127, weekly=5
        → هذا الأسبوع: 128 → 132
        → تحضير الأسبوع القادم: 133 → 137

التحضير الليلي:
    - الأوجه المطلوب حفظها غدًا (= مهمة الحفظ القادمة)
    - "قبل النوم، اقرأ الوجه X"

التحضير القبلي:
    - قبل جلسة الحفظ مباشرة
    - مؤقت 15 دقيقة، ثم "ابدأ الحفظ"
"""



def get_weekly_prep_range(user: User) -> dict:
    """نطاق التحضير الأسبوعي = أوجه الأسبوع القادم المتوقَّع حفظها.

    مهم: التحضير دائمًا للأسبوع القادم، وليس للأسبوع الحالي.
    الأسبوع الحالي يبدأ من next_hifz_page، والأسبوع القادم يبدأ من
    next_hifz_page + weekly_hifz_amount.

    مثال: last_hifz=40, weekly=7
        → هذا الأسبوع: 41 → 47
        → تحضير الأسبوع القادم: 48 → 54

    مثال: last_hifz=127, weekly=5  (حالة المستخدم)
        → هذا الأسبوع: 128 → 132
        → تحضير الأسبوع القادم: 133 → 137  ✅
    """
    last = user.last_hifz_page or 0
    weekly_amount = user.weekly_hifz_amount or config.DEFAULT_WEEKLY_HIFZ_AMOUNT

    if last >= config.QURAN_PAGE_COUNT:
        return {"start": None, "end": None, "amount": 0, "completed_quran": True}

    # بداية الأسبوع الحالي = الوجه القادم للحفظ
    this_week_start = last + 1
    # بداية الأسبوع القادم = بعد تجاوز كامل مقدار الحفظ الأسبوعي الحالي
    start = this_week_start + weekly_amount

    # إذا تجاوز البدء نهاية القرآن، فلا تحضير متبقٍّ
    if start > config.QURAN_PAGE_COUNT:
        return {
            "start": None,
            "end": None,
            "amount": 0,
            "completed_quran": False,
            "note": "no_next_week_pages",
        }

    end = min(config.QURAN_PAGE_COUNT, start + weekly_amount - 1)
    amount = end - start + 1
    return {
        "start": start,
        "end": end,
        "amount": amount,
        "completed_quran": False,
    }


def get_nightly_prep_pages(user: User) -> dict:
    """أوجه الغد = مهمة الحفظ القادمة.
    
    "قبل النوم: اقرأ الوجه X (أو الوجهين X و Y) استعدادًا لحفظه غدًا."
    """
    last = user.last_hifz_page or 0
    amount = max(1, user.daily_hifz_amount or 1)

    if last >= config.QURAN_PAGE_COUNT:
        return {"pages": [], "start": None, "end": None, "completed_quran": True}

    next_page = last + 1
    pages = list(range(next_page, min(next_page + amount, config.QURAN_PAGE_COUNT + 1)))
    return {
        "pages": pages,
        "start": pages[0] if pages else None,
        "end": pages[-1] if pages else None,
        "amount": len(pages),
        "completed_quran": False,
    }


def get_pre_session_prep_page(user: User) -> dict:
    """وجه التحضير القبلي = نفس وجه الحفظ القادم.
    
    يبدأ المستخدم المؤقّت (15 دقيقة)، ثم يبدأ الحفظ.
    """
    nightly = get_nightly_prep_pages(user)
    return nightly  # نفس الأوجه


def start_pre_session_timer(user: User) -> datetime:
    """بدء مؤقّت التحضير القبلي."""
    user.pre_session_started_at = datetime.utcnow()
    return user.pre_session_started_at


def end_pre_session_timer(user: User) -> int:
    """إنهاء المؤقّت — يُعيد عدد الدقائق المنقضية."""
    if not user.pre_session_started_at:
        return 0
    duration = (datetime.utcnow() - user.pre_session_started_at).total_seconds() / 60.0
    minutes = int(duration)
    user.pre_session_started_at = None
    return minutes


def get_pre_session_elapsed_minutes(user: User) -> int:
    """الوقت المنقضي منذ بدء المؤقّت (دقائق)."""
    if not user.pre_session_started_at:
        return 0
    duration = (datetime.utcnow() - user.pre_session_started_at).total_seconds() / 60.0
    return int(duration)


def is_pre_session_active(user: User) -> bool:
    """هل المؤقّت قيد التشغيل؟"""
    return user.pre_session_started_at is not None

# ══════════════════════════════════════════════════════════════════════
# ═══ 10. المحرك الموحَّد — خطة اليوم ═══
# المصدر: today_plan.py
# ══════════════════════════════════════════════════════════════════════

"""
المحرك الموحَّد — يجمع كل الحصون الخمسة في واجهة واحدة.
كل التابع يقبل user ويُعيد "خطة اليوم" الكاملة.
"""



async def compute_today_plan(session: AsyncSession, user: User, progress: DailyProgress) -> dict:
    """الحساب الكامل لخطة اليوم بناءً على حالة المستخدم.
    
    هذه هي الواجهة المركزية:
        USER STATE → Hifz Engine → TODAY'S PLAN → Telegram UI
    """
    reading = get_reading_assignment(user)
    reading_info = get_reading_cycle_info(user)
    listening = get_listening_assignment(user)
    listening_info = get_listening_cycle_info(user)

    weekly_prep = get_weekly_prep_range(user)
    nightly_prep = get_nightly_prep_pages(user)
    pre_session = get_pre_session_prep_page(user)
    pre_session_active = is_pre_session_active(user)
    pre_session_elapsed = get_pre_session_elapsed_minutes(user)

    hifz = get_today_hifz_assignment(user)
    near = get_near_review_range(user)
    far = await get_far_review_state(session, user)

    # عدّاد الإنجاز
    completed_count = sum([
        bool(progress.reading_done), bool(progress.listening_done),
        bool(progress.weekly_prep_done), bool(progress.nightly_prep_done),
        bool(progress.pre_session_prep_done), bool(progress.memorize_done),
        bool(progress.near_review_done), bool(progress.far_review_done),
    ])

    return {
        "user": user,
        "progress": progress,
        "reading": reading,
        "reading_info": reading_info,
        "listening": listening,
        "listening_info": listening_info,
        "weekly_prep": weekly_prep,
        "nightly_prep": nightly_prep,
        "pre_session": pre_session,
        "pre_session_active": pre_session_active,
        "pre_session_elapsed": pre_session_elapsed,
        "hifz": hifz,
        "near_review": near,
        "far_review": far,
        "completed_count": completed_count,
        "total_tasks": 8,
    }

# ══════════════════════════════════════════════════════════════════════
# ═══ 11. خدمات المستخدم ═══
# المصدر: user_service.py
# ══════════════════════════════════════════════════════════════════════

"""
خدمات المستخدم: إنشاء، استرجاع، تحديث، onboarding.
"""




async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
) -> User:
    """استرجاع أو إنشاء مستخدم جديد."""
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        today = date.today()
        user = User(
            telegram_id=telegram_id, username=username, full_name=full_name,
            plan_start_date=today, last_active_date=today,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        # إنشاء التذكيرات الافتراضية
        await ensure_default_reminders(user.id)
    elif (username != user.username) or (full_name != user.full_name):
        user.username = username
        user.full_name = full_name
        await session.commit()
    return user


async def update_user_activity(session: AsyncSession, user: User) -> None:
    """تحديث آخر نشاط للمستخدم."""
    today = date.today()
    if user.last_active_date != today:
        user.last_active_date = today
        await session.commit()


async def set_initial_hifz(session: AsyncSession, user: User, last_page: int) -> None:
    """ضبط نقطة البداية للحفظ عند الـ onboarding.
    
    هذه الدالة تُسجّل كل الأوجه من 1 إلى last_page كمحفوظة (للاستخدام في الإحصائيات).
    """
    last_page = max(0, min(int(last_page), config.QURAN_PAGE_COUNT))
    user.last_hifz_page = last_page
    user.next_hifz_page = last_page + 1 if last_page < config.QURAN_PAGE_COUNT else last_page
    # التحضير الأسبوعي = الأسبوع القادم (بعد تجاوز مقدار الأسبوع الحالي)
    weekly_amount = user.weekly_hifz_amount or config.DEFAULT_WEEKLY_HIFZ_AMOUNT
    this_week_start = last_page + 1 if last_page < config.QURAN_PAGE_COUNT else last_page
    user.weekly_prep_start = this_week_start + weekly_amount
    user.weekly_prep_end = min(
        config.QURAN_PAGE_COUNT,
        user.weekly_prep_start + weekly_amount - 1,
    )
    # حذف أي سجل سابق للمحفوظ (إذا أعاد المستخدم الضبط)
    await session.execute(
        MemorizationLog.__table__.delete().where(MemorizationLog.user_id == user.id)
    )
    today = date.today()
    if last_page > 0:
        # تسجيل الأوجه المحفوظة دفعة واحدة (تحسين: bulk insert)
        for p in range(1, last_page + 1):
            session.add(MemorizationLog(
                user_id=user.id, page_number=p, date_memorized=today, review_count=5
            ))
    await session.commit()


async def update_settings(
    session: AsyncSession,
    user: User,
    *,
    daily_amount: Optional[int] = None,
    weekly_amount: Optional[int] = None,
    timezone: Optional[str] = None,
    plan_start_date: Optional[date] = None,
    notifications: Optional[bool] = None,
) -> User:
    """تحديث إعدادات المستخدم — يُعيد حساب الاشتقاقات (مثل weekly_prep)."""
    if daily_amount is not None:
        user.daily_hifz_amount = max(1, min(int(daily_amount), config.QURAN_PAGE_COUNT))
        # لا يتأثر التحضير الأسبوعي بالمقدار اليومي مباشرةً — يعتمد على المقدار الأسبوعي فقط
        # (يُعاد حسابه عند تغيير weekly_amount أو تأكيد الحفظ)
    if weekly_amount is not None:
        user.weekly_hifz_amount = max(1, min(int(weekly_amount), config.QURAN_PAGE_COUNT))
        last = user.last_hifz_page or 0
        if last < config.QURAN_PAGE_COUNT:
            # التحضير الأسبوعي = الأسبوع القادم (بعد تجاوز مقدار الأسبوع الحالي)
            this_week_start = last + 1
            user.weekly_prep_start = this_week_start + user.weekly_hifz_amount
            user.weekly_prep_end = min(
                config.QURAN_PAGE_COUNT,
                user.weekly_prep_start + user.weekly_hifz_amount - 1,
            )
    if timezone is not None:
        user.timezone = timezone
    if plan_start_date is not None:
        user.plan_start_date = plan_start_date
    if notifications is not None:
        user.notifications_enabled = notifications
    await session.commit()
    return user

# ══════════════════════════════════════════════════════════════════════
# ═══ 12. خدمات المهام ═══
# المصدر: task_service.py
# ══════════════════════════════════════════════════════════════════════

"""
خدمات المهام: تسجيل/إلغاء/تأجيل إنجاز المهام اليومية الـ 8.
"""




# خريطة أنواع المهام ← أسماء الحقول في DailyProgress
TASK_FIELD_MAP = {
    "reading":          "reading_done",
    "listening":        "listening_done",
    "weekly_prep":      "weekly_prep_done",
    "nightly_prep":     "nightly_prep_done",
    "pre_session_prep": "pre_session_prep_done",
    "memorize":         "memorize_done",
    "near_review":      "near_review_done",
    "far_review":       "far_review_done",
}


async def get_or_create_progress(
    session: AsyncSession,
    user_id: int,
    progress_date: Optional[date] = None,
) -> DailyProgress:
    """استرجاع أو إنشاء سجل اليوم."""
    progress_date = progress_date or date.today()
    result = await session.execute(
        select(DailyProgress).where(
            DailyProgress.user_id == user_id,
            DailyProgress.progress_date == progress_date,
        )
    )
    progress = result.scalar_one_or_none()
    if progress is None:
        progress = DailyProgress(user_id=user_id, progress_date=progress_date)
        session.add(progress)
        await session.commit()
        await session.refresh(progress)
    return progress


def _compute_task_status(progress: DailyProgress) -> str:
    """احسب الحالة الإجمالية لليوم."""
    tasks = [
        progress.reading_done, progress.listening_done,
        progress.weekly_prep_done, progress.nightly_prep_done,
        progress.pre_session_prep_done, progress.memorize_done,
        progress.near_review_done, progress.far_review_done,
    ]
    completed = sum(1 for t in tasks if t)
    if completed == 8:
        return "completed"
    elif completed >= 1:
        return "partial"
    else:
        return "pending"


async def toggle_task(
    session: AsyncSession,
    user: User,
    progress: DailyProgress,
    task_type: str,
) -> dict:
    """تبديل حالة مهمة (مكتملة ↔ غير مكتملة).
    
    هذا يُمكّن التراجع عن أي ضغطة خاطئة.
    """
    if task_type not in TASK_FIELD_MAP:
        return {"success": False, "reason": "invalid_task_type"}

    field = TASK_FIELD_MAP[task_type]
    currently_done = bool(getattr(progress, field, False))

    if currently_done:
        # === التراجع عن المهمة ===
        if task_type == "pre_session_prep":
            progress.pre_session_duration_min = 0
            user.pre_session_started_at = None
        setattr(progress, field, False)
        await session.commit()
        progress.task_status = _compute_task_status(progress)
        await session.commit()
        await log_activity(session, user.id, f"undo_{task_type}", "تراجع عن المهمة")
        return {"success": True, "action": "undone", "task_type": task_type}
    else:
        # === تسجيل المهمة كمنجزة ===
        if task_type == "memorize":
            result = confirm_memorization(user)
            if not result.get("success"):
                return {"success": False, "reason": result.get("reason"), "message": result.get("message")}
            # تسجيل الأوجه المحفوظة في MemorizationLog
            for p in result["memorized_pages"]:
                existing = await session.execute(
                    select(MemorizationLog).where(
                        MemorizationLog.user_id == user.id,
                        MemorizationLog.page_number == p,
                    )
                )
                log = existing.scalar_one_or_none()
                if log is None:
                    session.add(MemorizationLog(
                        user_id=user.id, page_number=p, date_memorized=date.today()
                    ))
                else:
                    log.date_memorized = date.today()
                    log.review_count = 0
            progress.memorize_done = True
            await session.commit()
        elif task_type == "reading":
            advance_reading(user)
            progress.reading_done = True
            await session.commit()
        elif task_type == "listening":
            advance_listening(user)
            progress.listening_done = True
            await session.commit()
        elif task_type == "far_review":
            await advance_far_review_cycle(session, user)
            progress.far_review_done = True
            await session.commit()
        elif task_type == "pre_session_prep":
            # إنهاء المؤقّت وتسجيل المدة
            minutes = end_pre_session_timer(user)
            progress.pre_session_duration_min = minutes or config.PRE_SESSION_MINUTES
            progress.pre_session_prep_done = True
            await session.commit()
        else:
            setattr(progress, field, True)
            await session.commit()

        progress.task_status = _compute_task_status(progress)
        await session.commit()

        # تحديث streak
        await update_streak_on_activity(session, user)
        await log_activity(session, user.id, f"done_{task_type}", f"أنجزت {task_type}")
        return {"success": True, "action": "done", "task_type": task_type}


async def start_pre_session(session: AsyncSession, user: User, progress: DailyProgress) -> dict:
    """بدء مؤقّت التحضير القبلي (15 دقيقة)."""
    start_pre_session_timer(user)
    progress.pre_session_prep_done = False  # لم يكتمل بعد
    await session.commit()
    await log_activity(session, user.id, "pre_session_start", "بدأ التحضير القبلي")
    return {"success": True, "started_at": user.pre_session_started_at}


async def update_streak_on_activity(session: AsyncSession, user: User) -> None:
    """تحديث عدّاد أيام الالتزام المتتالية (streak).
    
    القاعدة: يوم واحد على الأقل مع مهمة مكتملة = يوم التزام.
    إذا انقطع يوم، يُعاد الضبط إلى 0.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    if user.last_active_date == today:
        # نفس اليوم — لا تغيير في الـ streak
        return
    if user.last_active_date == yesterday:
        # استمرارية
        user.streak_days = (user.streak_days or 0) + 1
    else:
        # انقطاع أو أول مرة
        user.streak_days = 1
    user.last_active_date = today
    await session.commit()


async def log_activity(
    session: AsyncSession,
    user_id: int,
    event_type: str,
    description: Optional[str] = None,
) -> None:
    """تسجيل حدث في Activity Log."""
    log = ActivityLog(
        user_id=user_id,
        event_type=event_type,
        description=description,
    )
    session.add(log)
    await session.commit()


async def get_recent_activity(session: AsyncSession, user_id: int, days: int = 14) -> list:
    """آخر سجل النشاط."""
    cutoff = date.today() - timedelta(days=days)
    result = await session.execute(
        select(ActivityLog)
        .where(ActivityLog.user_id == user_id, ActivityLog.log_date >= cutoff)
        .order_by(ActivityLog.log_date.desc(), ActivityLog.log_time.desc())
        .limit(100)
    )
    return list(result.scalars().all())

# ══════════════════════════════════════════════════════════════════════
# ═══ 13. الاقتراحات الذكية ═══
# المصدر: smart_suggestions.py
# ══════════════════════════════════════════════════════════════════════

"""
خدمات ذكية — تحليل سلوك المستخدم واقتراح تحسينات (لا تغيير تلقائي!).
"""



async def analyze_user_patterns(session: AsyncSession, user_id: int) -> dict:
    """تحليل أنماط سلوك المستخدم:
    - أوقات النشاط المعتادة (الساعة الأكثر إنجازًا)
    - كثرة التأجيل
    - أكثر الأيام التزامًا
    - المهام الفائتة باستمرار
    """
    cutoff = date.today() - timedelta(days=30)
    result = await session.execute(
        select(ActivityLog).where(
            ActivityLog.user_id == user_id,
            ActivityLog.log_date >= cutoff,
        ).order_by(ActivityLog.log_date.desc())
    )
    logs = list(result.scalars().all())

    # الساعات الأكثر إنجازًا
    hours = [log.log_time.hour for log in logs if log.event_type.startswith("done_")]
    hour_counts = Counter(hours)
    most_active_hour = hour_counts.most_common(1)[0][0] if hour_counts else None

    # المهام الأكثر إنجازًا
    done_tasks = [log.event_type.replace("done_", "") for log in logs if log.event_type.startswith("done_")]
    done_counts = Counter(done_tasks)

    # المهام الأكثر تراجعًا
    undone = [log.event_type.replace("undo_", "") for log in logs if log.event_type.startswith("undo_")]
    undone_counts = Counter(undone)

    # عدد أيام الالتزام
    active_days = set(log.log_date for log in logs if log.event_type.startswith("done_"))

    return {
        "most_active_hour": most_active_hour,
        "most_done_task": done_counts.most_common(1)[0][0] if done_counts else None,
        "most_undone_task": undone_counts.most_common(1)[0][0] if undone_counts else None,
        "active_days_count": len(active_days),
        "total_done": len(done_tasks),
        "total_undone": len(undone),
    }


async def generate_suggestions(session: AsyncSession, user: User) -> list[str]:
    """توليد اقتراحات ذكية بناءً على السلوك (لا تُطبَّق تلقائيًا)."""
    patterns = await analyze_user_patterns(session, user.id)
    suggestions = []

    if patterns["most_active_hour"] is not None:
        # نُحدِّد أيّ تذكير يقترح تغيير وقته
        hour = patterns["most_active_hour"]
        # الحفظ غالبًا يتم في هذه الساعة
        suggestions.append(
            f"💡 لاحظتُ أنك غالبًا تنجز مهامك الساعة {hour:02d}:00. "
            f"هل تريد جعل هذا وقت تذكير الحفظ الافتراضي؟"
        )

    if patterns["most_undone_task"]:
        task_label = config.REMINDER_LABELS_AR.get(patterns["most_undone_task"], patterns["most_undone_task"])
        suggestions.append(
            f"📊 لاحظتُ أنك غالبًا تتراجع عن '{task_label}'. "
            f"هل تريد تعديل وقتها أو مراجعة الهدف منها؟"
        )

    if patterns["active_days_count"] < 10 and patterns["total_done"] > 0:
        suggestions.append(
            "🔥 الالتزام الحالي أقل من 10 أيام في الشهر الماضي. "
            "جرّبي تقليل مقدار الحفظ اليومي قليلاً حتى تترسخ العادة."
        )

    return suggestions

# ══════════════════════════════════════════════════════════════════════
# ═══ 14. مساعدات الواجهة (safe_edit/send) ═══
# المصدر: utils.py
# ══════════════════════════════════════════════════════════════════════

"""
معالجات مساعدة مشتركة بين المعالجات الأخرى.
"""

logger = logging.getLogger(__name__)


async def safe_edit_message(query, text, reply_markup=None) -> bool:
    """تحرير رسالة inline بسلامة — يتجاهل 'الرسالة لم تتغيّر'."""
    try:
        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=reply_markup, disable_web_page_preview=True,
        )
        return True
    except BadRequest as e:
        msg = str(e).lower()
        if "not modified" in msg or "message is not modified" in msg:
            return True
        if "message can't be edited" in msg or "too old" in msg:
            logger.warning(f"لا يمكن تحرير الرسالة: {e}")
            return False
        logger.warning(f"BadRequest في edit_message_text: {e}")
        return False
    except Exception as e:
        logger.warning(f"تعذّر تعديل الرسالة: {e}")
        return False


async def safe_send_message(bot, chat_id, text, reply_markup=None) -> bool:
    """إرسال آمن."""
    try:
        await bot.send_message(
            chat_id=chat_id, text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
        return True
    except Exception as e:
        logger.warning(f"تعذّر إرسال الرسالة: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════
# ═══ 15. لوحات المفاتيح ═══
# المصدر: keyboards.py
# ══════════════════════════════════════════════════════════════════════

"""
لوحات المفاتيح — ReplyKeyboard ثابتة + Inline لكل شاشة.
"""


# ====== Reply Keyboard الثابتة ======

def main_keyboard() -> ReplyKeyboardMarkup:
    """اللوحة الرئيسية الثابتة — تظهر دائمًا في الأسفل."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🏠 لوحة التحكم"), KeyboardButton("📋 ورد اليوم")],
            [KeyboardButton("📊 تقدمي"), KeyboardButton("⚙️ الإعدادات")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="اضغط أحد الأزرار بالأسفل ✨",
    )


# خريطة نصوص الـ ReplyKeyboard ← أوامر داخلية
KEYBOARD_TEXT_MAP = {
    "🏠 لوحة التحكم": "main_panel",
    "📋 ورد اليوم": "today",
    "📊 تقدمي": "progress",
    "🏰 الحصون الخمسة": "fortresses",
    "⚙️ الإعدادات": "settings",
}


# ====== Inline Keyboards ======

def today_dashboard_inline() -> InlineKeyboardMarkup:
    """أزرار المهام الـ 8 (Toggleable) + إغلاق."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 قراءة", callback_data="task_reading"),
            InlineKeyboardButton("🎧 استماع", callback_data="task_listening"),
        ],
        [
            InlineKeyboardButton("📚 تحضير أسبوعي", callback_data="task_weekly_prep"),
            InlineKeyboardButton("🌙 تحضير ليلي", callback_data="task_nightly_prep"),
        ],
        [
            InlineKeyboardButton("⏱️ تحضير قبلي", callback_data="task_pre_session_prep"),
            InlineKeyboardButton("🆕 حفظ", callback_data="task_memorize"),
        ],
        [
            InlineKeyboardButton("🔄 مراجعة قريب", callback_data="task_near_review"),
            InlineKeyboardButton("🔁 مراجعة بعيد", callback_data="task_far_review"),
        ],
        [
            InlineKeyboardButton("🏰 تفاصيل الحصون", callback_data="fortresses_menu"),
            InlineKeyboardButton("❌ إغلاق", callback_data="close_inline"),
        ],
    ])


def today_dashboard_with_status(plan: dict) -> InlineKeyboardMarkup:
    """أزرار المهام مع علامات ✅/⬜ تعكس الحالة الفعلية."""
    progress = plan["progress"]

    def btn(label: str, task_type: str) -> InlineKeyboardButton:
        done = bool(getattr(progress, f"{task_type}_done", False))
        icon = "✅" if done else "⬜"
        return InlineKeyboardButton(f"{icon} {label}", callback_data=f"task_{task_type}")

    return InlineKeyboardMarkup([
        [
            btn("📖 قراءة", "reading"),
            btn("🎧 استماع", "listening"),
        ],
        [
            btn("📚 تحضير أسبوعي", "weekly_prep"),
            btn("🌙 تحضير ليلي", "nightly_prep"),
        ],
        [
            btn("⏱️ تحضير قبلي", "pre_session_prep"),
            btn("🆕 حفظ", "memorize"),
        ],
        [
            btn("🔄 مراجعة قريب", "near_review"),
            btn("🔁 مراجعة بعيد", "far_review"),
        ],
        [
            InlineKeyboardButton("🏠 لوحة التحكم", callback_data="main_panel"),
            InlineKeyboardButton("🏰 تفاصيل الحصون", callback_data="fortresses_menu"),
        ],
    ])


# ====== لوحة التحكم الشاملة (Main Panel) ======
# تجمع معظم الأساسيات في شاشة واحدة منظّمة بأقسام — مستوحاة من بوتات المخزن الاحترافية.

def main_panel_inline(plan: dict = None) -> InlineKeyboardMarkup:
    """لوحة تحكم شاملة بأقسام منظّمة:
    
    - الإحصائيات السريعة (التقدّم / الالتزام)
    - مهام اليوم (8 أزرار toggleable)
    - الحصون الخمسة (5 أزرار)
    - الإعدادات والتذكيرات (4 أزرار)
    - إجراءات سريعة (3 أزرار)
    """
    rows = []

    # ── القسم 1: المهام السريعة (4 أزرار toggleable في صف واحد مضغوط) ──
    if plan is not None:
        progress = plan["progress"]

        def mini(label: str, task_type: str) -> InlineKeyboardButton:
            done = bool(getattr(progress, f"{task_type}_done", False))
            icon = "✅" if done else "⬜"
            return InlineKeyboardButton(f"{icon} {label}", callback_data=f"task_{task_type}")

        rows.append([
            mini("قراءة", "reading"),
            mini("استماع", "listening"),
            mini("حفظ", "memorize"),
        ])
        rows.append([
            mini("تحضير أ.", "weekly_prep"),
            mini("تحضير ل.", "nightly_prep"),
            mini("تحضير ق.", "pre_session_prep"),
        ])
        rows.append([
            mini("مراجعة ق.", "near_review"),
            mini("مراجعة ب.", "far_review"),
        ])

    # ── القسم 2: ورد اليوم + تفاصيل الحصون ──
    rows.append([
        InlineKeyboardButton("📋 ورد اليوم", callback_data="today_dashboard"),
        InlineKeyboardButton("🏰 الحصون الخمسة", callback_data="fortresses_menu"),
    ])

    # ── القسم 3: الحصون الخمسة (وصول سريع لكل حصن) ──
    rows.append([
        InlineKeyboardButton("1️⃣ التهيئة", callback_data="fortress_1"),
        InlineKeyboardButton("2️⃣ التحضير", callback_data="fortress_2"),
    ])
    rows.append([
        InlineKeyboardButton("3️⃣ الحفظ", callback_data="fortress_3"),
        InlineKeyboardButton("4️⃣ القريب", callback_data="fortress_4"),
        InlineKeyboardButton("5️⃣ البعيد", callback_data="fortress_5"),
    ])

    # ── القسم 4: الإعدادات السريعة ──
    rows.append([
        InlineKeyboardButton("📊 تقدّمي", callback_data="show_progress"),
        InlineKeyboardButton("📜 السجل", callback_data="show_activity_log"),
    ])
    rows.append([
        InlineKeyboardButton("📝 آخر محفوظ", callback_data="set_last_page"),
        InlineKeyboardButton("📊 مقدار يومي", callback_data="set_daily_amount"),
    ])
    rows.append([
        InlineKeyboardButton("📚 مقدار أسبوعي", callback_data="set_weekly_amount"),
        InlineKeyboardButton("⏰ التذكيرات", callback_data="set_reminders"),
    ])

    # ── القسم 5: إجراءات سريعة + المساعدة ──
    rows.append([
        InlineKeyboardButton("💡 اقتراحات ذكية", callback_data="set_suggestions"),
        InlineKeyboardButton("🔔 الإشعارات", callback_data="set_notifications"),
    ])
    rows.append([
        InlineKeyboardButton("❓ المساعدة", callback_data="show_help"),
        InlineKeyboardButton("❌ إغلاق", callback_data="close_inline"),
    ])

    return InlineKeyboardMarkup(rows)


def fortresses_menu_inline() -> InlineKeyboardMarkup:
    """قائمة الحصون الخمسة."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 ورد اليوم", callback_data="today_dashboard")],
        [
            InlineKeyboardButton("🏰 1. التهيئة", callback_data="fortress_1"),
            InlineKeyboardButton("📚 2. التحضير", callback_data="fortress_2"),
        ],
        [
            InlineKeyboardButton("🆕 3. الحفظ", callback_data="fortress_3"),
            InlineKeyboardButton("🔄 4. القريب", callback_data="fortress_4"),
        ],
        [
            InlineKeyboardButton("🛡️ 5. البعيد", callback_data="fortress_5"),
            InlineKeyboardButton("🏠 لوحة التحكم", callback_data="main_panel"),
        ],
    ])


def back_to_today_inline() -> InlineKeyboardMarkup:
    """زر الرجوع لورد اليوم + لوحة التحكم."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 ورد اليوم", callback_data="today_dashboard"),
            InlineKeyboardButton("🏠 لوحة التحكم", callback_data="main_panel"),
        ],
    ])


def onboarding_start_inline() -> InlineKeyboardMarkup:
    """اختيار آخر وجه محفوظ (سور سريعة)."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌱 لم أحفظ شيئًا بعد", callback_data="ob_0")],
        [
            InlineKeyboardButton("📖 البقرة", callback_data="ob_surah_2"),
            InlineKeyboardButton("📖 آل عمران", callback_data="ob_surah_3"),
        ],
        [
            InlineKeyboardButton("📖 النساء", callback_data="ob_surah_4"),
            InlineKeyboardButton("📖 المائدة", callback_data="ob_surah_5"),
        ],
        [
            InlineKeyboardButton("📖 الكهف", callback_data="ob_surah_18"),
            InlineKeyboardButton("📖 يس", callback_data="ob_surah_36"),
        ],
        [
            InlineKeyboardButton("📖 تبارك", callback_data="ob_surah_67"),
            InlineKeyboardButton("📖 عمَّ", callback_data="ob_surah_78"),
        ],
        [InlineKeyboardButton("✅ ختمت القرآن كاملًا", callback_data="ob_all")],
        [InlineKeyboardButton("✍️ إدخال يدوي", callback_data="ob_manual")],
    ])


def daily_amount_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 وجه/يوم", callback_data="ob_daily_1"),
            InlineKeyboardButton("2 وجه/يوم (موصى)", callback_data="ob_daily_2"),
        ],
        [InlineKeyboardButton("✍️ مخصص", callback_data="ob_daily_custom")],
    ])


def weekly_amount_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("5 أوجه", callback_data="ob_weekly_5"),
            InlineKeyboardButton("7 أوجه (موصى)", callback_data="ob_weekly_7"),
        ],
        [
            InlineKeyboardButton("10 أوجه", callback_data="ob_weekly_10"),
            InlineKeyboardButton("14 وجهًا", callback_data="ob_weekly_14"),
        ],
    ])


def plan_start_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 اليوم (موصى)", callback_data="ob_plan_today")],
        [InlineKeyboardButton("✍️ إدخال تاريخ", callback_data="ob_plan_manual")],
    ])


def reminders_confirm_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ قبول الأوقات الافتراضية", callback_data="ob_reminders_default")],
        [InlineKeyboardButton("⚙️ تخصيص لاحقًا", callback_data="ob_reminders_customize")],
    ])


def settings_panel_inline() -> InlineKeyboardMarkup:
    """لوحة الإعدادات."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 تعديل آخر محفوظ", callback_data="set_last_page"),
            InlineKeyboardButton("📊 مقدار يومي", callback_data="set_daily_amount"),
        ],
        [
            InlineKeyboardButton("📚 مقدار أسبوعي", callback_data="set_weekly_amount"),
            InlineKeyboardButton("📖 حزب القراءة", callback_data="set_reading_hizb"),
        ],
        [
            InlineKeyboardButton("🎧 حزب الاستماع", callback_data="set_listening_hizb"),
            InlineKeyboardButton("🔁 دورة المراجعة البعيدة", callback_data="set_far_cycle"),
        ],
        [
            InlineKeyboardButton("⏰ التذكيرات", callback_data="set_reminders"),
            InlineKeyboardButton("🔔 الإشعارات", callback_data="set_notifications"),
        ],
        [
            InlineKeyboardButton("🏠 لوحة التحكم", callback_data="main_panel"),
            InlineKeyboardButton("❌ إغلاق", callback_data="close_inline"),
        ],
    ])


def confirm_inline(action: str, label: str) -> InlineKeyboardMarkup:
    """زر تأكيد قبل تعديل مهم."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"✅ نعم، {label}", callback_data=f"confirm_{action}"),
            InlineKeyboardButton("❌ إلغاء", callback_data="cancel_action"),
        ],
    ])


def pre_session_start_inline() -> InlineKeyboardMarkup:
    """زر بدء مؤقّت التحضير القبلي."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ بدء التحضير (15 دقيقة)", callback_data="start_pre_session")],
        [InlineKeyboardButton("🏠 لوحة التحكم", callback_data="main_panel")],
    ])


def pre_session_end_inline() -> InlineKeyboardMarkup:
    """زر إنهاء المؤقّت."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ انتهيت، ابدأ الحفظ", callback_data="task_pre_session_prep")],
        [InlineKeyboardButton("🏠 لوحة التحكم", callback_data="main_panel")],
    ])

# ══════════════════════════════════════════════════════════════════════
# ═══ 16. العارضات النصية (HTML) ═══
# المصدر: renderers.py
# ══════════════════════════════════════════════════════════════════════

"""
العارضات النصية — كل HTML يُبنى هنا بسلامة (HTML escaping تلقائي).
"""



def esc(text) -> str:
    """HTML-escape لأي نص."""
    if text is None:
        return ""
    return html.escape(str(text))


def bold(text) -> str:
    return f"<b>{esc(text)}</b>"


def code(text) -> str:
    return f"<code>{esc(text)}</code>"


def fmt_range(start, end) -> str:
    """تنسيق نطاق أوجه."""
    if start is None or end is None:
        return "—"
    if end < start:
        return f"{start}→{quran_data.TOTAL_PAGES} + 1→{end}"
    if start == end:
        return f"{start}"
    return f"{start}–{end}"


def render_today_dashboard(plan: dict) -> str:
    """عرض ورد اليوم — كل المهام في رسالة واحدة."""
    user: User = plan["user"]
    progress: DailyProgress = plan["progress"]

    today_str = date.today().strftime("%Y-%m-%d")
    days_since = max(0, (date.today() - user.plan_start_date).days) + 1 if user.plan_start_date else 0

    # القراءة
    r = plan["reading"]
    r_info = plan["reading_info"]
    reading_hizb_list = "+".join(str(h) for h in r["hizb_list"])
    reading_done_icon = "✅" if progress.reading_done else "⬜"

    # الاستماع
    l = plan["listening"]
    l_info = plan["listening_info"]
    listening_done_icon = "✅" if progress.listening_done else "⬜"

    # التحضير الأسبوعي
    wp = plan["weekly_prep"]
    wp_done_icon = "✅" if progress.weekly_prep_done else "⬜"

    # التحضير الليلي
    np_ = plan["nightly_prep"]
    np_done_icon = "✅" if progress.nightly_prep_done else "⬜"

    # التحضير القبلي
    ps = plan["pre_session"]
    ps_done_icon = "✅" if progress.pre_session_prep_done else "⬜"
    if plan["pre_session_active"]:
        ps_status = f" ⏱️ <i>قيد التشغيل — {plan['pre_session_elapsed']} دقيقة</i>"
    elif progress.pre_session_duration_min > 0:
        ps_status = f" (<b>{progress.pre_session_duration_min} دقيقة</b>)"
    else:
        ps_status = ""

    # الحفظ
    h = plan["hifz"]
    memo_done_icon = "✅" if progress.memorize_done else "⬜"

    # مراجعة القريب
    nr = plan["near_review"]
    nr_done_icon = "✅" if progress.near_review_done else "⬜"

    # مراجعة البعيد
    fr = plan["far_review"]
    fr_done_icon = "✅" if progress.far_review_done else "⬜"

    text_parts = [
        f"📋 <b>ورد اليوم — {esc(today_str)}</b>",
        f"📅 اليوم رقم <b>{days_since}</b> منذ بدأت الخطة",
        f"🔥 أيام الالتزام: <b>{user.streak_days or 0} يوم</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        f"{reading_done_icon} 📖 <b>القراءة</b> — الحزب {bold(reading_hizb_list)}",
        f"   الأوجه {bold(fmt_range(r['pages_start'], r['pages_end']))}",
        f"   الدورة {r_info['current_hizb']}/{r_info['total_in_cycle']} — ختمة #{r_info['current_khatmah_number']}",
        "",
        f"{listening_done_icon} 🎧 <b>الاستماع</b> — الحزب {bold(l['hizb'])}",
        f"   الأوجه {bold(fmt_range(l['pages_start'], l['pages_end']))}",
        f"   الدورة {l_info['current_hizb']}/{l_info['total_in_cycle']} — ختمة #{l_info['current_khatmah_number']}",
        "",
        "━━━━━━━━━━━━━━━━",
        f"{wp_done_icon} 📚 <b>التحضير الأسبوعي</b>",
    ]

    if wp["start"] is not None:
        text_parts.append(f"   الأوجه {bold(fmt_range(wp['start'], wp['end']))} ({wp['amount']} وجه)")
    else:
        text_parts.append("   <i>أكملتِ القرآن — لا تحضير أسبوعي مطلوب</i>")

    text_parts.extend([
        "",
        f"{np_done_icon} 🌙 <b>التحضير الليلي</b>",
    ])

    if np_["pages"]:
        if len(np_["pages"]) == 1:
            text_parts.append(f"   قبل النوم: اقرأ الوجه {bold(np_['start'])} استعدادًا للغد")
        else:
            text_parts.append(f"   قبل النوم: اقرأ الأوجه {bold(fmt_range(np_['start'], np_['end']))} استعدادًا للغد")
    else:
        text_parts.append("   <i>أكملتِ القرآن كاملًا 🎉</i>")

    text_parts.extend([
        "",
        f"{ps_done_icon} ⏱️ <b>التحضير القبلي</b>",
    ])
    if ps["pages"]:
        text_parts.append(f"   الوجه {bold(ps['start'])}{ps_status}")
    else:
        text_parts.append("   <i>لا يوجد</i>")

    text_parts.extend([
        "",
        "━━━━━━━━━━━━━━━━",
        f"{memo_done_icon} 🆕 <b>الحفظ</b>",
    ])
    if h["pages"]:
        if len(h["pages"]) == 1:
            text_parts.append(f"   اليوم: احفظ الوجه {bold(h['start'])}")
        else:
            text_parts.append(f"   اليوم: احفظ الأوجه {bold(fmt_range(h['start'], h['end']))}")
    else:
        text_parts.append("   <i>أكملتِ القرآن كاملًا 🎉</i>")

    text_parts.extend([
        "",
        "━━━━━━━━━━━━━━━━",
        f"{nr_done_icon} 🔄 <b>مراجعة القريب</b>",
    ])
    if nr["applicable"]:
        text_parts.append(f"   الأوجه {bold(fmt_range(nr['start'], nr['end']))} (آخر 20 وجه محفوظ)")
    else:
        text_parts.append("   <i>لا ينطبق الآن — سيُفعَّل بعد حفظ أول وجه</i>")

    text_parts.extend([
        "",
        f"{fr_done_icon} 🔁 <b>مراجعة البعيد</b>",
    ])
    if fr["applicable"]:
        text_parts.append(
            f"   الأوجه {bold(fmt_range(fr['cycle_start'], fr['cycle_end']))} "
            f"(الدورة {fr['current_cycle']}/{fr['total_cycles']})"
        )
    else:
        text_parts.append("   <i>لا ينطبق الآن — سيُفعَّل بعد حفظ 20+ وجه</i>")

    text_parts.extend([
        "",
        "━━━━━━━━━━━━━━━━",
        f"📊 <b>الإنجاز: {plan['completed_count']}/8 مهام</b>",
        "👇 اضغط أي مهمة بالأسفل لتسجيلها أو التراجع عنها",
    ])

    return "\n".join(text_parts)


def render_progress_dashboard(user: User, plan: dict, total_memorized: int) -> str:
    """عرض شاشة التقدم."""
    h = plan["hifz"]
    r_info = plan["reading_info"]
    l_info = plan["listening_info"]
    nr = plan["near_review"]
    fr = plan["far_review"]

    pages_total = config.QURAN_PAGE_COUNT
    percent = (total_memorized / pages_total * 100) if pages_total > 0 else 0
    bar_filled = int(percent / 5)  # 20 حرف
    bar = "█" * bar_filled + "░" * (20 - bar_filled)

    parts = [
        "📊 <b>تقدّمك في حفظ القرآن</b>",
        "",
        f"<code>{bar}</code>",
        f"📖 المحفوظ: <b>{total_memorized} / {pages_total}</b> وجه ({esc(f'{percent:.1f}')}%)",
        f"📍 آخر وجه محفوظ: <b>{user.last_hifz_page or 0}</b>",
        f"🆕 الوجه القادم: <b>{user.next_hifz_page or 1}</b>",
        f"📊 المقدار اليومي: <b>{user.daily_hifz_amount} وجه</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        "📖 <b>دورة القراءة</b>",
        f"   الحزب {r_info['current_hizb']} / {r_info['total_in_cycle']} ({r_info['percent']}%)",
        f"   ختمة #{r_info['current_khatmah_number']} — منجزة: {r_info['khatmah_count']}",
        "",
        "🎧 <b>دورة الاستماع</b>",
        f"   الحزب {l_info['current_hizb']} / {l_info['total_in_cycle']} ({l_info['percent']}%)",
        f"   ختمة #{l_info['current_khatmah_number']} — منجزة: {l_info['khatmah_count']}",
        "",
        "━━━━━━━━━━━━━━━━",
        "🔄 <b>الحصن الرابع (القريب)</b>",
    ]
    if nr["applicable"]:
        parts.append(f"   {nr['count']} وجه قيد المراجعة ({nr['start']}→{nr['end']})")
    else:
        parts.append("   <i>لا ينطبق بعد</i>")

    parts.append("")
    parts.append("🔁 <b>الحصن الخامس (البعيد)</b>")
    if fr["applicable"]:
        parts.append(f"   الدورة {fr['current_cycle']}/{fr['total_cycles']} ({fr['cycle_start']}→{fr['cycle_end']})")
    else:
        parts.append("   <i>لا ينطبق بعد</i>")

    parts.extend([
        "",
        "━━━━━━━━━━━━━━━━",
        f"🔥 الالتزام: <b>{user.streak_days or 0} يوم متتالي</b>",
        f"✅ مهام اليوم: <b>{plan['completed_count']}/8</b>",
        f"⏳ المتبقي اليوم: <b>{8 - plan['completed_count']} مهام</b>",
    ])

    return "\n".join(parts)


def render_fortress_1(plan: dict) -> str:
    """الحصن الأول — التهيئة."""
    r = plan["reading"]
    r_info = plan["reading_info"]
    l = plan["listening"]
    l_info = plan["listening_info"]
    parts = [
        "📖 <b>الحصن الأول — التهيئة المستمرة</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        "📅 <b>القراءة اليوم</b>",
        f"   حزبا القراءة: <b>{'+'.join(str(h) for h in r['hizb_list'])}</b>",
        f"   الأوجه: <b>{fmt_range(r['pages_start'], r['pages_end'])}</b>",
        f"   الدورة: {r_info['current_hizb']}/{r_info['total_in_cycle']} ({r_info['percent']}%)",
        f"   ختمة رقم: <b>{r_info['current_khatmah_number']}</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        "🎧 <b>الاستماع اليوم</b>",
        f"   حزب اليوم: <b>{l['hizb']}</b>",
        f"   الأوجه: <b>{fmt_range(l['pages_start'], l['pages_end'])}</b>",
        f"   الدورة: {l_info['current_hizb']}/{l_info['total_in_cycle']} ({l_info['percent']}%)",
        f"   ختمة رقم: <b>{l_info['current_khatmah_number']}</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        "💡 <i>دورة القراءة 30 يومًا (حزبان/يوم)، ودورة الاستماع 60 يومًا (حزب/يوم). "
        "كل واحدة مستقلة تمامًا عن الأخرى.</i>",
    ]
    return "\n".join(parts)


def render_fortress_2(plan: dict) -> str:
    """الحصن الثاني — التحضير."""
    wp = plan["weekly_prep"]
    np_ = plan["nightly_prep"]
    ps = plan["pre_session"]
    user = plan["user"]
    progress = plan["progress"]
    parts = [
        "📚 <b>الحصن الثاني — التحضير</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        "📅 <b>التحضير الأسبوعي</b>",
    ]
    if wp["start"] is not None:
        parts.append(f"   الأوجه: <b>{fmt_range(wp['start'], wp['end'])}</b>")
        parts.append(f"   المقدار: <b>{user.weekly_hifz_amount} وجه/أسبوع</b>")
    else:
        parts.append("   <i>أكملتِ القرآن</i>")

    parts.extend(["", "━━━━━━━━━━━━━━━━", "🌙 <b>التحضير الليلي</b>"])
    if np_["pages"]:
        if len(np_["pages"]) == 1:
            parts.append(f"   اقرأ الوجه <b>{np_['start']}</b> قبل النوم")
        else:
            parts.append(f"   اقرأ الأوجه <b>{fmt_range(np_['start'], np_['end'])}</b> قبل النوم")
    else:
        parts.append("   <i>لا يوجد</i>")

    parts.extend(["", "━━━━━━━━━━━━━━━━", "⏱️ <b>التحضير القبلي</b>"])
    if ps["pages"]:
        parts.append(f"   الوجه <b>{ps['start']}</b>")
        parts.append(f"   المدة: <b>{config.PRE_SESSION_MINUTES} دقيقة</b>")
        if plan["pre_session_active"]:
            parts.append(f"   <i>⏱️ قيد التشغيل — {plan['pre_session_elapsed']} دقيقة مرّت</i>")
        elif progress.pre_session_duration_min > 0:
            parts.append(f"   <i>آخر مدة: {progress.pre_session_duration_min} دقيقة</i>")
    else:
        parts.append("   <i>لا يوجد</i>")

    parts.extend([
        "",
        "━━━━━━━━━━━━━━━━",
        "💡 <i>اضغطي زر ⏱️ التحضير القبلي في ورد اليوم لبدء المؤقّت، ثم اضغطيه مرة أخرى عند الانتهاء.</i>",
    ])
    return "\n".join(parts)


def render_fortress_3(plan: dict) -> str:
    """الحصن الثالث — الحفظ الجديد."""
    h = plan["hifz"]
    user = plan["user"]
    parts = [
        "🆕 <b>الحصن الثالث — الحفظ الجديد</b>",
        "",
        "━━━━━━━━━━━━━━━━",
    ]
    if h["pages"]:
        parts.append(f"📍 الأوجه المطلوبة: <b>{fmt_range(h['start'], h['end'])}</b>")
        surah = quran_data.page_to_surah(h["start"])
        juz = quran_data.page_to_juz(h["start"])
        parts.append(f"📖 السورة: <b>{esc(surah.name_ar)}</b>")
        parts.append(f"📚 الجزء: <b>{juz}</b>")
        parts.append(f"📊 المقدار: <b>{user.daily_hifz_amount} وجه/يوم</b>")
    else:
        parts.append("🎉 <b>أكملتِ القرآن كاملًا!</b>")

    parts.extend([
        "",
        "━━━━━━━━━━━━━━━━",
        "💡 <b>طريقة الحفظ:</b>",
        "• اقرئي كل آية 10 مرات",
        "• اربطي الآيات حتى تُحفظ الصفحة كاملة",
        "• لا تنتقلي لوجه جديد حتى تُتقني الحالي",
        "• بعد الحفظ، اضغطي 🆕 حفظ في ورد اليوم",
        "",
        "🤲 <i>اللهم اجعل القرآن ربيع قلوبنا</i>",
    ])
    return "\n".join(parts)


def render_fortress_4(plan: dict) -> str:
    """الحصن الرابع — مراجعة القريب."""
    nr = plan["near_review"]
    parts = [
        "🔄 <b>الحصن الرابع — مراجعة القريب</b>",
        "",
        "━━━━━━━━━━━━━━━━",
    ]
    if nr["applicable"]:
        parts.append(f"📍 الأوجه <b>{fmt_range(nr['start'], nr['end'])}</b> (آخر 20 وجه محفوظ)")
        start_surah = quran_data.page_to_surah(nr["start"])
        end_surah = quran_data.page_to_surah(nr["end"])
        parts.append(f"📖 السور: {esc(start_surah.name_ar)} ← {esc(end_surah.name_ar)}")
        parts.append(f"📊 العدد: <b>{nr['count']} وجه</b>")
        parts.extend([
            "",
            "💡 <i>تُراجع يومياً كاملة. هذا أقوى الحصون ضد النسيان.</i>",
            "🤲 <i>اقرئيها من المصحف ثم من ذاكرتك</i>",
        ])
    else:
        parts.append("⏸️ <i>لا ينطبق الآن — سيُفعَّل بعد حفظ أول وجه</i>")
    return "\n".join(parts)


def render_fortress_5(plan: dict) -> str:
    """الحصن الخامس — مراجعة البعيد."""
    fr = plan["far_review"]
    parts = [
        "🛡️ <b>الحصن الخامس — مراجعة البعيد</b>",
        "",
        "━━━━━━━━━━━━━━━━",
    ]
    if fr["applicable"]:
        parts.append(f"📍 الأوجه <b>{fmt_range(fr['cycle_start'], fr['cycle_end'])}</b>")
        start_surah = quran_data.page_to_surah(fr["cycle_start"])
        end_surah = quran_data.page_to_surah(fr["cycle_end"])
        parts.append(f"📖 السور: {esc(start_surah.name_ar)} ← {esc(end_surah.name_ar)}")
        parts.append(f"🔄 الدورة: <b>{fr['current_cycle']}/{fr['total_cycles']}</b>")
        parts.extend([
            "",
            "💡 <i>تُقسَّم على أيام الأسبوع. الهدف التذكير لا الإتقان التام.</i>",
            "✅ عند إتمام الدورة، اضغطي زر 🔁 مراجعة بعيد لانتقال للدورة التالية.",
        ])
    else:
        parts.append("⏸️ <i>لا ينطبق الآن — سيُفعَّل بعد حفظ 20+ وجه</i>")
    return "\n".join(parts)


def render_settings_panel(user: User, settings_list: list) -> str:
    """عرض لوحة الإعدادات."""
    parts = [
        "⚙️ <b>الإعدادات</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        f"📍 آخر وجه محفوظ: <b>{user.last_hifz_page or 0}</b>",
        f"📊 المقدار اليومي: <b>{user.daily_hifz_amount} وجه</b>",
        f"📚 المقدار الأسبوعي: <b>{user.weekly_hifz_amount} وجه</b>",
        f"📖 حزب القراءة الحالي: <b>{user.reading_hizb_current}</b>",
        f"🎧 حزب الاستماع الحالي: <b>{user.listening_hizb_current}</b>",
        f"🔔 الإشعارات: <b>{'مفعّلة' if user.notifications_enabled else 'معطّلة'}</b>",
        f"🌍 المنطقة الزمنية: <b>{esc(user.timezone)}</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        "⏰ <b>أوقات التذكيرات:</b>",
    ]
    labels = config.REMINDER_LABELS_AR
    settings_by_type = {s.reminder_type: s for s in settings_list}
    for rtype in config.REMINDER_TYPES:
        s = settings_by_type.get(rtype)
        time_str = s.reminder_time if s else config.DEFAULT_REMINDER_TIMES[rtype]
        enabled = "✅" if (s and s.enabled) else "❌"
        parts.append(f"   {enabled} {labels[rtype]}: <code>{esc(time_str)}</code>")
    parts.extend(["", "👇 اختر ما تريد تعديله:"])
    return "\n".join(parts)


def render_activity_log(logs: list) -> str:
    """عرض سجل النشاط."""
    if not logs:
        return "📅 <b>سجل النشاط</b>\n\n<i>لا يوجد نشاط مسجَّل بعد.</i>"
    parts = ["📅 <b>سجل النشاط (آخر 14 يومًا)</b>", ""]
    current_date = None
    for log in logs:
        if log.log_date != current_date:
            current_date = log.log_date
            parts.append(f"\n━━ <b>{esc(log.log_date.strftime('%Y-%m-%d'))}</b> ━━")
        time_str = log.log_time.strftime("%H:%M") if log.log_time else ""
        parts.append(f"  {time_str} — {esc(log.event_type)} {esc(log.description or '')}")
    return "\n".join(parts)


def render_suggestions(suggestions: list) -> str:
    """عرض الاقتراحات الذكية."""
    if not suggestions:
        return "💡 <b>اقتراحات ذكية</b>\n\n<i>لا توجد اقتراحات حالياً — استمر في الالتزام! 🌟</i>"
    parts = ["💡 <b>اقتراحات ذكية بناءً على سلوكك</b>", ""]
    for s in suggestions:
        parts.append(f"• {esc(s)}")
    parts.extend(["", "<i>لن تُطبَّق هذه الاقتراحات تلقائيًا — القرار لك.</i>"])
    return "\n".join(parts)


def render_main_panel(user: User, plan: dict, total_memorized: int) -> str:
    """لوحة التحكم الشاملة — تجمع الإحصائيات الأساسية في شاشة واحدة منظّمة.

    مستوحاة من بوتات المخزن الاحترافية: لا حاجة للتنقّل بين عدة شاشات.
    كل ما يحتاجه المستخدم في الغالب موجود هنا.
    """
    h = plan["hifz"]
    r_info = plan["reading_info"]
    l_info = plan["listening_info"]
    nr = plan["near_review"]
    fr = plan["far_review"]
    wp = plan["weekly_prep"]

    pages_total = config.QURAN_PAGE_COUNT
    percent = (total_memorized / pages_total * 100) if pages_total > 0 else 0
    bar_filled = int(percent / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)

    today_str = date.today().strftime("%Y-%m-%d")
    completed = plan.get("completed_count", 0)
    remaining = 8 - completed

    parts = [
        "🏠 <b>لوحة التحكم</b>",
        f"📅 {esc(today_str)}",
        "",
        "━━━━━━━━━━━━━━━━",
        "📊 <b>تقدّمك في الحفظ</b>",
        f"<code>{bar}</code>",
        f"📖 {bold(f'{total_memorized} / {pages_total}')} وجه ({esc(f'{percent:.1f}%')})",
        f"📍 آخر محفوظ: {bold(str(user.last_hifz_page or 0))}  "
        f"🆕 التالي: {bold(str(user.next_hifz_page or 1))}",
        "",
        "━━━━━━━━━━━━━━━━",
        "🔥 <b>الالتزام والإنجاز</b>",
        f"   🔥 streak: {bold(f'{user.streak_days or 0} يوم')}",
        f"   ✅ مهام اليوم: {bold(f'{completed}/8')}  ⏳ متبقٍّ: {bold(str(remaining))}",
        f"   📚 مقدار يومي: {bold(f'{user.daily_hifz_amount} وجه')}  "
        f"أسبوعي: {bold(f'{user.weekly_hifz_amount} وجه')}",
        "",
        "━━━━━━━━━━━━━━━━",
        "📖 <b>الحصن الأول — التهيئة</b>",
        f"   القراءة: حزب {bold(str(r_info['current_hizb']))}/{r_info['total_in_cycle']}  "
        f"ختمة #{r_info['current_khatmah_number']}",
        f"   الاستماع: حزب {bold(str(l_info['current_hizb']))}/{l_info['total_in_cycle']}  "
        f"ختمة #{l_info['current_khatmah_number']}",
    ]

    parts.extend(["", "━━━━━━━━━━━━━━━━", "📚 <b>الحصن الثاني — التحضير</b>"])
    if wp["start"] is not None:
        parts.append(
            f"   التحضير الأسبوعي (الأسبوع القادم): {bold(fmt_range(wp['start'], wp['end']))}"
        )
    else:
        parts.append("   <i>أكملتِ القرآن — لا تحضير متبقٍّ</i>")
    if h["pages"]:
        if len(h["pages"]) == 1:
            parts.append(f"   🌙 تحضير ليلي: اقرأ الوجه {bold(str(h['start']))}")
        else:
            parts.append(f"   🌙 تحضير ليلي: اقرأ {bold(fmt_range(h['start'], h['end']))}")

    parts.extend(["", "━━━━━━━━━━━━━━━━", "🆕 <b>الحصن الثالث — الحفظ الجديد</b>"])
    if h["pages"]:
        if len(h["pages"]) == 1:
            parts.append(f"   اليوم: احفظ الوجه {bold(str(h['start']))}")
        else:
            parts.append(f"   اليوم: احفظ {bold(fmt_range(h['start'], h['end']))}")
    else:
        parts.append("   <i>أكملتِ القرآن كاملًا 🎉</i>")

    parts.extend(["", "━━━━━━━━━━━━━━━━", "🔄 <b>الحصن الرابع — مراجعة القريب</b>"])
    if nr["applicable"]:
        parts.append(
            f"   {bold(str(nr['count']))} وجه قيد المراجعة ({nr['start']}→{nr['end']})"
        )
    else:
        parts.append("   <i>سيُفعَّل بعد حفظ أول وجه</i>")

    parts.extend(["", "━━━━━━━━━━━━━━━━", "🛡️ <b>الحصن الخامس — مراجعة البعيد</b>"])
    if fr["applicable"]:
        cycle_str = f"{fr['current_cycle']}/{fr['total_cycles']}"
        parts.append(
            f"   الدورة {bold(cycle_str)} "
            f"({fr['cycle_start']}→{fr['cycle_end']})"
        )
    else:
        parts.append("   <i>سيُفعَّل بعد حفظ 20+ وجه</i>")

    parts.extend([
        "",
        "━━━━━━━━━━━━━━━━",
        "👇 <b>الأزرار بالأسفل منظّمة بأقسام:</b>",
        "   ✅/⬜ = مهام سريعة (اضغط للتسجيل/التراجع)",
        "   🏰 = الحصون  • 📊 = التقدّم  • ⚙️ = الإعدادات",
    ])
    return "\n".join(parts)


def render_help() -> str:
    """شاشة المساعدة المختصرة."""
    return (
        "❓ <b>المساعدة — بوت الحصون الخمسة</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📋 <b>الأوامر الأساسية:</b>\n"
        "   /start — بدء / إعادة ضبط\n"
        "   /today — ورد اليوم\n"
        "   /progress — لوحة التقدّم\n"
        "   /help — هذه الشاشة\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <b>أوامر طبيعية (مجرد كتابة نص):</b>\n"
        "   • «وش نحفظ اليوم؟» → ورد اليوم\n"
        "   • «وين وصلت؟» → التقدّم\n"
        "   • «حفظت الوجه 41» → تسجيل الحفظ\n"
        "   • «قريت الورد» → تأكيد القراءة\n"
        "   • «أريد نغيّر الحفظ إلى 2» → تعديل المقدار\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🏰 <b>الحصون الخمسة:</b>\n"
        "   1️⃣ التهيئة — قراءة (30 يوم) + استماع (60 يوم)\n"
        "   2️⃣ التحضير — أسبوعي + ليلي + قبلي (15 د)\n"
        "   3️⃣ الحفظ — الوجه القادم بناءً على التقدّم\n"
        "   4️⃣ القريب — آخر 20 وجه محفوظ\n"
        "   5️⃣ البعيد — 40 وجه/دورة (دورات مستقلة)\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💡 <b>قواعد ذهبية:</b>\n"
        "   • التحضير الأسبوعي دائمًا للأسبوع <b>القادم</b>\n"
        "   • لا يتقدّم الحفظ تلقائيًا — يجب التأكيد\n"
        "   • أزرار المهام قابلة للتراجع (toggle)\n"
        "   • لا تُفقد البيانات بين الجلسات\n\n"
        "<i>🤲 اللهم اجعل القرآن ربيع قلوبنا.</i>"
    )

# ══════════════════════════════════════════════════════════════════════
# ═══ 17. معالج الـ Onboarding ═══
# المصدر: onboarding.py
# ══════════════════════════════════════════════════════════════════════

"""
معالج الـ Onboarding — Setup Wizard من 5 خطوات.
"""



logger = logging.getLogger(__name__)

# حالة الـ onboarding لكل مستخدم (مؤقتة في الذاكرة)
ONBOARDING_STATE = {}  # user_id -> "step_name"


async def start_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE, welcome: bool = True):
    """يبدأ Setup Wizard — الخطوة 1: آخر وجه محفوظ."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "ob_step_1_memorization"

    welcome_text = ""
    if welcome:
        welcome_text = (
            "🌟 <b>أهلًا بكِ في بوت الحصون الخمسة</b>\n\n"
            "مرافقك الشخصي لحفظ القرآن الكريم وفق منهج الحصون الخمسة.\n"
            "سنُهيّئ خطتك في 5 خطوات سريعة. 🚀\n\n"
        )

    text = (
        f"{welcome_text}"
        "━━━━━━━━━━━━━━━━\n"
        "❓ <b>الخطوة 1/5: أين وصلتِ في الحفظ؟</b>\n\n"
        "اختر آخر سورة حفظتِها كاملة، أو أدخلي يدويًا.\n"
        "إذا لم تحفظي شيئًا بعد، اختر 'لم أحفظ شيئًا'.\n"
        "━━━━━━━━━━━━━━━━"
    )
    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=onboarding_start_inline(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await safe_edit_message(update.callback_query, text, onboarding_start_inline())


async def process_onboarding_memorization(update: Update, context: ContextTypes.DEFAULT_TYPE, text_input: str):
    """معالجة إدخال الخطوة 1 ثم الانتقال للخطوة 2."""
    user_id = update.effective_user.id
    parsed = await parse_memorization_input(text_input)

    if parsed["page"] is None and "0" not in text_input and "لا" not in text_input.lower():
        # لم نفهم — نُعيد السؤال
        text = (
            "❌ <b>لم أفهم الإجابة</b> 😅\n\n"
            "جرّبي:\n"
            "• <code>صفحة 50</code>\n"
            "• <code>سورة المائدة</code>\n"
            "• <code>جزء 3</code>\n"
            "• <code>0</code> (لم أحفظ)"
        )
        if update.message:
            await update.message.reply_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=onboarding_start_inline(),
                disable_web_page_preview=True,
            )
        return

    page = parsed["page"] or 0
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=user_id)
        await set_initial_hifz(session, user, page)

    # الانتقال للخطوة 2
    await ask_daily_amount(update, context)


async def ask_daily_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 2: مقدار الحفظ اليومي."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "ob_step_2_daily_amount"
    text = (
        "✅ <b>تمّ تسجيل محفوظك السابق!</b> 🎉\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "❓ <b>الخطوة 2/5: كم تريدين أن تحفظي يوميًا؟</b>\n\n"
        "💡 <i>التوصية: وجهان لمن تملك الوقت. لكن حتى وجه واحد يومياً "
        "يكفي لإتمام القرآن خلال سنتين.</i>\n"
        "━━━━━━━━━━━━━━━━"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, daily_amount_inline())
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=daily_amount_inline(),
            disable_web_page_preview=True,
        )


async def ask_weekly_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 3: مقدار الحفظ الأسبوعي."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "ob_step_3_weekly_amount"
    text = (
        "✅ <b>تمّ ضبط الحفظ اليومي!</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "❓ <b>الخطوة 3/5: كم تريدين أن تحفظي أسبوعيًا؟</b>\n\n"
        "💡 <i>هذا يُحدّد نطاق التحضير الأسبوعي (الحصن الثاني).</i>\n"
        "━━━━━━━━━━━━━━━━"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, weekly_amount_inline())


async def ask_plan_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 4: تاريخ بداية الخطة."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "ob_step_4_plan_start"
    today_str = date.today().strftime("%Y-%m-%d")
    text = (
        "✅ <b>تمّ ضبط المقدار الأسبوعي!</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"❓ <b>الخطوة 4/5: متى تبدأ خطتك؟</b>\n\n"
        f"📅 اليوم: <code>{esc(today_str)}</code>\n\n"
        "💡 <i>يُحدّد بداية دورة القراءة (30 يومًا) ودورة الاستماع (60 يومًا).</i>\n"
        "━━━━━━━━━━━━━━━━"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, plan_start_inline())


async def ask_reminder_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 5: تأكيد أوقات التذكيرات."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "ob_step_5_reminders"
    text = (
        "✅ <b>تمّ ضبط تاريخ البداية!</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "❓ <b>الخطوة 5/5: أوقات التذكيرات الـ 8</b>\n\n"
        "🕒 <b>الأوقات الافتراضية:</b>\n"
    )
    labels = config.REMINDER_LABELS_AR
    for rtype in config.REMINDER_TYPES:
        text += f"• <code>{config.DEFAULT_REMINDER_TIMES[rtype]}</code> — {labels[rtype]}\n"
    text += "\n💡 <i>يمكنك تخصيصها لاحقًا من ⚙️ الإعدادات</i>\n"
    text += "━━━━━━━━━━━━━━━━"
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reminders_confirm_inline())


async def finalize_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنهاء الـ onboarding وعرض ملخّص الخطة."""
    user_id = update.effective_user.id
    ONBOARDING_STATE.pop(user_id, None)

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=user_id)
        user.onboarding_done = True
        if user.plan_start_date is None:
            user.plan_start_date = user.created_at or date.today()
        await session.commit()

    text = (
        "🎉 <b>ما شاء الله! اكتملت تهيئتك</b> 🌟\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📊 <b>ملخّص خطتك:</b>\n\n"
        f"📖 آخر وجه محفوظ: <b>{user.last_hifz_page or 0}</b>\n"
        f"🆕 الوجه القادم: <b>{user.next_hifz_page or 1}</b>\n"
        f"📅 تاريخ بداية الخطة: <code>{esc(user.plan_start_date)}</code>\n"
        f"📚 المقدار اليومي: <b>{user.daily_hifz_amount} وجه</b>\n"
        f"📚 المقدار الأسبوعي: <b>{user.weekly_hifz_amount} وجه</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "👇 اضغط <b>📋 ورد اليوم</b> في الأسفل لعرض برنامجك الكامل"
    )

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
                disable_web_page_preview=True,
            )
        except Exception:
            await update.effective_chat.send_message(
                text, parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
                disable_web_page_preview=True,
            )
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )


async def parse_memorization_input(text: str) -> dict:
    """تحليل إدخال المستخدم حول آخر صفحة محفوظة.
    
    الصيغ المدعومة:
        "ختمت القرآن" / "كامل"  → page = 604
        "جزء 7"                → آخر وجه في الجزء 7
        "سورة المائدة"          → آخر وجه في سورة المائدة
        "صفحة 100-110"         → نطاق
        "صفحة 100"             → وجه واحد
        "100"                  → رقم مباشر
        "0" / "لا"             → لم يحفظ
    """
    text = text.strip()
    result = {"type": None, "page": None, "raw": text}

    # ختم القرآن
    if any(k in text for k in ["كل القرآن", "كامل القرآن", "ختمت", "كله"]):
        result.update({"type": "all", "page": quran_data.TOTAL_PAGES})
        return result

    # "لم أحفظ" — نطابق فقط الكلمة الكاملة "لم" أو "لا" ككلمة مستقلة
    # (لا نطابق "لم" داخل "المائدة" أو "لا" داخل "الله" مثلًا)
    _has_no = bool(_re.search(r"\b(لم|لا)\b", text)) or "0" in text or "ما حفظت" in text
    if _has_no:
        if not any(c.isdigit() and int(c) > 0 for c in text.split()):
            result.update({"type": "none", "page": 0})
            return result

    # جزء N
    m = re.search(r"جزء\s*(\d+)", text)
    if m:
        juz = int(m.group(1))
        if 1 <= juz <= 30:
            start, end = quran_data.juz_pages(juz)
            result.update({"type": "juz", "page": end})
            return result

    # سورة X
    m = re.search(r"سورة\s+(.+)", text)
    if m:
        surah = quran_data.get_surah_by_name(m.group(1).strip())
        if surah:
            if surah.number < 114:
                last_page = quran_data.get_surah_by_number(surah.number + 1).page_start - 1
            else:
                last_page = quran_data.TOTAL_PAGES
            result.update({"type": "surah", "page": last_page})
            return result

    # نطاق صفحات
    m = re.search(r"صفحة\s*(\d+)\s*[-–]\s*(\d+)", text)
    if m:
        end_p = int(m.group(2))
        if 1 <= end_p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page_range", "page": end_p})
            return result

    # صفحة N
    m = re.search(r"صفحة\s*(\d+)", text)
    if m:
        p = int(m.group(1))
        if 1 <= p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page", "page": p})
            return result

    # رقم مباشر
    m = re.match(r"^\s*(\d+)\s*$", text)
    if m:
        p = int(m.group(1))
        if 1 <= p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page", "page": p})
            return result

    return result

# ══════════════════════════════════════════════════════════════════════
# ═══ 18. معالج ورد اليوم + لوحة التحكم ═══
# المصدر: today_dashboard.py
# ══════════════════════════════════════════════════════════════════════

"""
معالج ورد اليوم — يعرض المهام الـ 8 + يستقبل الضغطات (toggleable).
"""



logger = logging.getLogger(__name__)


async def _count_memorized(user_id: int) -> int:
    """يُعيد عدد الأوجه المحفوظة للمستخدم."""
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count(MemorizationLog.id)).where(MemorizationLog.user_id == user_id)
        )
        return count or 0


async def show_today_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعرض ورد اليوم مع أزرار المهام الـ 8."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            await start_onboarding(update, context, welcome=False)
            return
        await update_user_activity(session, user)
        progress = await get_or_create_progress(session, user.id)
        plan = await compute_today_plan(session, user, progress)

    text = render_today_dashboard(plan)
    reply_markup = today_dashboard_with_status(plan)

    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup)


async def show_main_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعرض لوحة التحكم الشاملة — تجمع معظم الأساسيات في شاشة واحدة."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            await start_onboarding(update, context, welcome=False)
            return
        await update_user_activity(session, user)
        progress = await get_or_create_progress(session, user.id)
        plan = await compute_today_plan(session, user, progress)

    total_memorized = await _count_memorized(user.id)
    text = render_main_panel(user, plan, total_memorized)
    reply_markup = main_panel_inline(plan)

    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup)


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعرض شاشة المساعدة."""
    text = render_help()
    if update.callback_query:
        await safe_edit_message(
            update.callback_query, text,
            _btk(),
        )
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=_btk(),
            disable_web_page_preview=True,
        )


async def handle_task_button(update: Update, context: ContextTypes.DEFAULT_TYPE, task_type: str):
    """معالجة ضغط زر مهمة — تبديل الحالة + إعادة عرض الواجهة.

    ملاحظة: تعيد العرض في نفس الواجهة التي جاء منها الضغط (ورد اليوم أو لوحة التحكم).
    نكتشف الواجهة الحالية من نص الرسالة الأصلي.
    """
    query = update.callback_query
    toast_text = None

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=update.effective_user.id)
        if not user.onboarding_done:
            await start_onboarding(update, context, welcome=False)
            return
        progress = await get_or_create_progress(session, user.id)

        # استثناء: التحضير القبلي له زرّان منفصلان
        if task_type == "pre_session_prep" and not progress.pre_session_prep_done:
            if not user.pre_session_started_at:
                await start_pre_session(session, user, progress)
                toast_text = "⏱️ بدأ المؤقّت (15 دقيقة)"
            else:
                result = await toggle_task(session, user, progress, task_type)
                if result.get("success"):
                    toast_text = "✅ تم الإنهاء"
        else:
            result = await toggle_task(session, user, progress, task_type)
            if result.get("success"):
                toast_text = "✅ تم الإنجاز" if result.get("action") == "done" else "↩️ تم التراجع"

        plan = await compute_today_plan(session, user, progress)

    if toast_text:
        try:
            await query.answer(text=toast_text, show_alert=False)
        except Exception:
            pass

    # اكتشاف الواجهة الحالية من نص الرسالة
    current_text = ""
    try:
        if query.message and query.message.text:
            current_text = query.message.text or ""
    except Exception:
        pass

    if "لوحة التحكم" in current_text:
        # عُد إلى لوحة التحكم
        total_memorized = await _count_memorized(user.id)
        text = render_main_panel(user, plan, total_memorized)
        reply_markup = main_panel_inline(plan)
    else:
        # الافتراضي: ورد اليوم
        text = render_today_dashboard(plan)
        reply_markup = today_dashboard_with_status(plan)
    await safe_edit_message(query, text, reply_markup)


async def show_pre_session_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعرض زر بدء مؤقّت التحضير القبلي."""
    text = (
        "⏱️ <b>التحضير القبلي</b>\n\n"
        "اقرأ الوجه المطلوب بتركيز لمدة 15 دقيقة قبل بدء الحفظ.\n\n"
        "👇 اضغطي الزر بالأسفل لبدء المؤقّت"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, pre_session_start_inline())

# ══════════════════════════════════════════════════════════════════════
# ═══ 19. معالجات الحصون الخمسة ═══
# المصدر: fortress_views.py
# ══════════════════════════════════════════════════════════════════════

"""
معالجات الحصون الخمسة — عرض تفصيلي لكل حصن.
"""



logger = logging.getLogger(__name__)


async def _get_plan(update: Update):
    """يجلب المستخدم + الخطة — مُساعَد داخلي."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            return None
        progress = await get_or_create_progress(session, user.id)
        plan = await compute_today_plan(session, user, progress)
    return plan


async def show_fortresses_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعرض قائمة الحصون الخمسة."""
    text = (
        "🏰 <b>الحصون الخمسة</b>\n\n"
        "اختر حصنًا لعرض تفاصيله:\n\n"
        "• <b>1. التهيئة</b> — القراءة والاستماع اليومي\n"
        "• <b>2. التحضير</b> — أسبوعي + ليلي + قبلي\n"
        "• <b>3. الحفظ الجديد</b> — الوجه القادم\n"
        "• <b>4. مراجعة القريب</b> — آخر 20 وجه\n"
        "• <b>5. مراجعة البعيد</b> — 40 وجه (دورات)\n\n"
        "أو اضغط <b>📋 ورد اليوم</b> لعرض كل المهام."
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, fortresses_menu_inline())
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=fortresses_menu_inline(),
            disable_web_page_preview=True,
        )


async def show_fortress_1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan = await _get_plan(update)
    if plan is None:
        await start_onboarding(update, context, welcome=False)
        return
    text = render_fortress_1(plan)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())


async def show_fortress_2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan = await _get_plan(update)
    if plan is None:
        await start_onboarding(update, context, welcome=False)
        return
    text = render_fortress_2(plan)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())


async def show_fortress_3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan = await _get_plan(update)
    if plan is None:
        await start_onboarding(update, context, welcome=False)
        return
    text = render_fortress_3(plan)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())


async def show_fortress_4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan = await _get_plan(update)
    if plan is None:
        await start_onboarding(update, context, welcome=False)
        return
    text = render_fortress_4(plan)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())


async def show_fortress_5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan = await _get_plan(update)
    if plan is None:
        await start_onboarding(update, context, welcome=False)
        return
    text = render_fortress_5(plan)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())

# ══════════════════════════════════════════════════════════════════════
# ═══ 20. معالج شاشة التقدم ═══
# المصدر: progress.py
# ══════════════════════════════════════════════════════════════════════

"""
معالج شاشة التقدم.
"""



logger = logging.getLogger(__name__)


async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض شاشة التقدم."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            await start_onboarding(update, context, welcome=False)
            return
        progress = await get_or_create_progress(session, user.id)
        plan = await compute_today_plan(session, user, progress)

        # عدد الأوجه المحفوظة فعليًا
        result = await session.execute(
            select(func.count(MemorizationLog.id)).where(MemorizationLog.user_id == user.id)
        )
        total_memorized = result.scalar() or 0

    text = render_progress_dashboard(user, plan, total_memorized)
    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=back_to_today_inline(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())


async def show_activity_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض سجل النشاط."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        result = await session.execute(
            select(ActivityLog)
            .where(ActivityLog.user_id == user.id)
            .order_by(ActivityLog.log_date.desc(), ActivityLog.log_time.desc())
            .limit(50)
        )
        logs = list(result.scalars().all())

    text = render_activity_log(logs)
    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=back_to_today_inline(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())

# ══════════════════════════════════════════════════════════════════════
# ═══ 21. معالج لوحة الإعدادات ═══
# المصدر: settings_panel.py
# ══════════════════════════════════════════════════════════════════════

"""
معالج لوحة الإعدادات — تعديل يدوي لكل القيم.
"""



logger = logging.getLogger(__name__)

# حالة الإدخال اليدوي لكل مستخدم
INPUT_STATE = {}  # user_id -> ("waiting_for_X", ...)


async def show_settings_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعرض لوحة الإعدادات."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        settings_list = list(result.scalars().all())

    text = render_settings_panel(user, settings_list)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, settings_panel_inline())
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=settings_panel_inline(),
            disable_web_page_preview=True,
        )


async def ask_last_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب آخر وجه محفوظ."""
    user_id = update.effective_user.id
    INPUT_STATE[user_id] = "waiting_for_last_page"
    text = (
        "📝 <b>تعديل آخر وجه محفوظ</b>\n\n"
        "أرسلي الآن رقم آخر وجه حفظتِه:\n\n"
        "مثال: <code>40</code>\n\n"
        "<i>سيُعاد حساب جميع المهام تلقائيًا بناءً على هذا الرقم.</i>"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())


async def ask_daily_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل المقدار اليومي."""
    if update.callback_query:
        text = (
            "📊 <b>تعديل المقدار اليومي</b>\n\n"
            "اختر المقدار الجديد:"
        )
        await safe_edit_message(update.callback_query, text, daily_amount_inline())


async def ask_weekly_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل المقدار الأسبوعي."""
    if update.callback_query:
        text = (
            "📚 <b>تعديل المقدار الأسبوعي</b>\n\n"
            "اختر المقدار الجديد:"
        )
        await safe_edit_message(update.callback_query, text, weekly_amount_inline())


async def ask_reading_hizb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل حزب القراءة."""
    user_id = update.effective_user.id
    INPUT_STATE[user_id] = "waiting_for_reading_hizb"
    text = (
        "📖 <b>تعديل حزب القراءة</b>\n\n"
        "أرسلي رقم الحزب (1-60):\n\n"
        "مثال: <code>21</code>"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())


async def ask_listening_hizb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل حزب الاستماع."""
    user_id = update.effective_user.id
    INPUT_STATE[user_id] = "waiting_for_listening_hizb"
    text = (
        "🎧 <b>تعديل حزب الاستماع</b>\n\n"
        "أرسلي رقم الحزب (1-60):\n\n"
        "مثال: <code>15</code>"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())


async def ask_far_cycle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل دورة المراجعة البعيدة."""
    user_id = update.effective_user.id
    INPUT_STATE[user_id] = "waiting_for_far_cycle"
    text = (
        "🔁 <b>تعديل دورة المراجعة البعيدة</b>\n\n"
        "أرسلي رقم الدورة الجديدة (1 أو أكثر):\n\n"
        "مثال: <code>1</code>"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())


async def ask_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تفعيل/تعطيل الإشعارات."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        new_state = not user.notifications_enabled
        await update_settings(session, user, notifications=new_state)
        state_str = "مفعّلة ✅" if new_state else "معطّلة ❌"
    text = f"🔔 <b>تم تعديل الإشعارات</b>\n\nالحالة الحالية: <b>{state_str}</b>"
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, settings_panel_inline())


async def show_reminders_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إعدادات التذكيرات."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        settings_list = list(result.scalars().all())

    text = "⏰ <b>أوقات التذكيرات</b>\n\n"
    text += "يمكنك تعديل كل وقت باستخدام الأمر:\n"
    text += "<code>/settime نوع HH:MM</code>\n\n"
    text += "مثال: <code>/settime memorize 06:00</code>\n\n"
    text += "الأنواع المتاحة:\n"
    labels = config.REMINDER_LABELS_AR
    settings_by_type = {s.reminder_type: s for s in settings_list}
    for rtype in config.REMINDER_TYPES:
        s = settings_by_type.get(rtype)
        time_str = s.reminder_time if s else config.DEFAULT_REMINDER_TIMES[rtype]
        enabled = "✅" if (s and s.enabled) else "❌"
        text += f"{enabled} <code>{rtype}</code> — {labels[rtype]}: <code>{esc(time_str)}</code>\n"
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, settings_panel_inline())


async def show_suggestions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الاقتراحات الذكية."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        suggestions = await generate_suggestions(session, user)
    text = render_suggestions(suggestions)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=back_to_today_inline(),
            disable_web_page_preview=True,
        )


async def process_free_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة الإدخال اليدوي أثناء تعديل الإعدادات."""
    user_id = update.effective_user.id
    state = INPUT_STATE.get(user_id)
    if not state:
        return False  # ليس في وضع إدخال

    text = text.strip()

    try:
        if state == "waiting_for_last_page":
            page = int(text)
            if not (1 <= page <= quran_data.TOTAL_PAGES):
                raise ValueError("خارج النطاق")
            async with AsyncSessionLocal() as session:
                user = await get_or_create_user(session, telegram_id=user_id)
                await set_initial_hifz(session, user, page)
            INPUT_STATE.pop(user_id, None)
            await update.message.reply_text(
                f"✅ تم ضبط آخر وجه محفوظ على <b>{page}</b>\n"
                "تم إعادة حساب جميع المهام تلقائيًا.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_today_inline(),
                disable_web_page_preview=True,
            )
            return True

        if state == "waiting_for_reading_hizb":
            hizb = int(text)
            if not (1 <= hizb <= config.QURAN_HIZB_COUNT):
                raise ValueError("خارج النطاق")
            async with AsyncSessionLocal() as session:
                user = await get_or_create_user(session, telegram_id=user_id)
                user.reading_hizb_current = hizb
                await session.commit()
            INPUT_STATE.pop(user_id, None)
            await update.message.reply_text(
                f"✅ تم ضبط حزب القراءة على <b>{hizb}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_today_inline(),
                disable_web_page_preview=True,
            )
            return True

        if state == "waiting_for_listening_hizb":
            hizb = int(text)
            if not (1 <= hizb <= config.QURAN_HIZB_COUNT):
                raise ValueError("خارج النطاق")
            async with AsyncSessionLocal() as session:
                user = await get_or_create_user(session, telegram_id=user_id)
                user.listening_hizb_current = hizb
                await session.commit()
            INPUT_STATE.pop(user_id, None)
            await update.message.reply_text(
                f"✅ تم ضبط حزب الاستماع على <b>{hizb}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_today_inline(),
                disable_web_page_preview=True,
            )
            return True

        if state == "waiting_for_far_cycle":
            cycle = int(text)
            if cycle < 1:
                raise ValueError("خارج النطاق")
            async with AsyncSessionLocal() as session:
                user = await get_or_create_user(session, telegram_id=user_id)
                result = await session.execute(
                    select(FarReviewCycle).where(FarReviewCycle.user_id == user.id)
                )
                fr_state = result.scalar_one_or_none()
                if fr_state is None:
                    fr_state = FarReviewCycle(user_id=user.id, current_cycle=cycle)
                    session.add(fr_state)
                else:
                    fr_state.current_cycle = cycle
                await session.commit()
            INPUT_STATE.pop(user_id, None)
            await update.message.reply_text(
                f"✅ تم ضبط دورة المراجعة البعيدة على <b>{cycle}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_today_inline(),
                disable_web_page_preview=True,
            )
            return True
    except ValueError:
        await update.message.reply_text(
            "❌ <b>إدخال غير صحيح</b>\n\n"
            "أرسلي رقمًا صحيحًا ضمن النطاق المطلوب.",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return True

    return False

# ══════════════════════════════════════════════════════════════════════
# ═══ 22. معالج النص الحر (NLP) ═══
# المصدر: free_text.py
# ══════════════════════════════════════════════════════════════════════

"""
معالج النص الحر — NLP بسيط لفهم أوامر المستخدم بالعربية.
"""



logger = logging.getLogger(__name__)


# خريطة نصوص ReplyKeyboard


async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج النص الحر — NLP بسيط + توجيه للأوامر."""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # 1. لو النص يطابق أحد أزرار الـ ReplyKeyboard
    if text in KEYBOARD_TEXT_MAP:
        cmd = KEYBOARD_TEXT_MAP[text]
        if cmd == "main_panel":
            await show_main_panel(update, context)
        elif cmd == "today":
            await show_today_dashboard(update, context)
        elif cmd == "progress":
            await show_progress(update, context)
        elif cmd == "fortresses":
            await show_fortresses_menu(update, context)
        elif cmd == "settings":
            await show_settings_panel(update, context)
        return

    # 2. لو المستخدم في وضع الإدخال اليدوي (إعدادات)
    if user_id in INPUT_STATE:
        handled = await process_free_input(update, context, text)
        if handled:
            return

    # 3. لو المستخدم في وضع الـ onboarding
    state = ONBOARDING_STATE.get(user_id)
    if state == "ob_step_1_memorization":
        await process_onboarding_memorization(update, context, text)
        return

    # 4. NLP بسيط لفهم أوامر عربية طبيعية
    handled = await try_natural_language(update, context, text)
    if handled:
        return

    # 5. نص حر غير مفهوم
    await update.message.reply_text(
        "💡 <b>اضغط أحد أزرار القائمة بالأسفل</b>\n\n"
        "أو جرّب:\n"
        "• <code>صفحة 50</code> — تعديل آخر محفوظ\n"
        "• <code>وش نحفظ اليوم؟</code> — عرض ورد اليوم\n"
        "• <code>وين وصلت؟</code> — عرض التقدم\n"
        "• <code>حفظت الوجه 41</code> — تسجيل الحفظ",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


async def try_natural_language(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """محاولة فهم اللغة الطبيعية العربية.
    
    يدعم:
        "وش نحفظ اليوم؟" / "شنو نحفظ" → ورد اليوم
        "وين وصلت؟" → التقدم
        "وش نراجع؟" → الحصون الرابع والخامس
        "حفظت الوجه X" / "حفظت X" → تسجيل الحفظ
        "قريت الورد" / "ختمت القراءة" → تأكيد القراءة
        "اليوم ما قدرت" → تسجيل كغير مكتمل (دون تحريك الحفظ)
        "نسيت وين وصلت" → عرض التقدم
        "أريد نغيّر الحفظ إلى X" → تعديل المقدار
    """
    text_lower = text.lower()

    # === "وش نحفظ اليوم؟" ===
    if any(k in text_lower for k in ["شنو نحفظ", "وش نحفظ", "ايش نحفظ", "ماذا أحفظ", "ماذا احفظ", "وش نقرا", "وش نراجع"]):
        if "راجع" in text_lower:
            await show_fortresses_menu(update, context)
        else:
            await show_today_dashboard(update, context)
        return True

    # === "وين وصلت؟" ===
    if any(k in text_lower for k in ["وين وصلت", "وين وصل", "وش المحفوظ", "وصلت ل", "وين انا", "نسيت وين"]):
        await show_progress(update, context)
        return True

    # === "حفظت الوجه X" / "حفظت X" ===
    m = re.search(r"حفظت\s*(?:الوجه\s*)?(\d+)", text)
    if m:
        page = int(m.group(1))
        if 1 <= page <= quran_data.TOTAL_PAGES:
            # تعديل آخر محفوظ
            async with AsyncSessionLocal() as session:
                user = await get_or_create_user(session, telegram_id=update.effective_user.id)
                # إذا الصفحة أكبر من last_hifz_page، نحدّث
                if page > (user.last_hifz_page or 0):
                    await set_initial_hifz(session, user, page)
                    await update.message.reply_text(
                        f"✅ تم تسجيل حفظ الوجه <b>{page}</b> 🎉",
                        parse_mode=ParseMode.HTML,
                        reply_markup=back_to_today_inline(),
                        disable_web_page_preview=True,
                    )
                else:
                    await update.message.reply_text(
                        f"⚠️ الوجه {page} محفوظ سابقًا.\nآخر محفوظ: <b>{user.last_hifz_page}</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=back_to_today_inline(),
                        disable_web_page_preview=True,
                    )
            return True

    # === "قريت الورد" / "ختمت القراءة" ===
    if any(k in text_lower for k in ["قريت الورد", "قريت ورد", "ختمت القراءة", "خلصت القراءة", "قرأت الورد"]):
        async with AsyncSessionLocal() as session:
            user = await get_or_create_user(session, telegram_id=update.effective_user.id)
            progress = await get_or_create_progress(session, user.id)
            if not progress.reading_done:
                await toggle_task(session, user, progress, "reading")
                await update.message.reply_text(
                    "✅ تم تسجيل إنجاز القراءة 📖",
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_to_today_inline(),
                    disable_web_page_preview=True,
                )
            else:
                await update.message.reply_text(
                    "✅ القراءة مكتملة بالفعل اليوم",
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_to_today_inline(),
                    disable_web_page_preview=True,
                )
        return True

    # === "سمعت الاستماع" / "خلصت الاستماع" ===
    if any(k in text_lower for k in ["سمعت", "خلصت الاستماع", "قريت الاستماع", "أنهيت الاستماع"]):
        async with AsyncSessionLocal() as session:
            user = await get_or_create_user(session, telegram_id=update.effective_user.id)
            progress = await get_or_create_progress(session, user.id)
            if not progress.listening_done:
                await toggle_task(session, user, progress, "listening")
                await update.message.reply_text(
                    "✅ تم تسجيل إنجاز الاستماع 🎧",
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_to_today_inline(),
                    disable_web_page_preview=True,
                )
        return True

    # === "اليوم ما قدرت" ===
    if any(k in text_lower for k in ["ما قدرت", "ما قديت", "اليوم ما", "نسيت اليوم", "تأجيل", "أجّل"]):
        async with AsyncSessionLocal() as session:
            user = await get_or_create_user(session, telegram_id=update.effective_user.id)
            await log_activity(session, user.id, "postponed", "أجّل المستخدم مهام اليوم")
        await update.message.reply_text(
            "📝 <b>سُجِّل اليوم كغير مكتمل</b>\n\n"
            "<i>لا تقلق — لم يتحرك الحفظ للأمام. الوجه المطلوب غدًا هو نفسه.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_today_inline(),
            disable_web_page_preview=True,
        )
        return True

    # === "أريد نغيّر الحفظ إلى X" ===
    m = re.search(r"(?:الحفظ|المقدار).{0,15}(\d+)", text)
    if m and ("غيّر" in text_lower or "تغيير" in text_lower or "نولي" in text_lower or "بدّل" in text_lower):
        amount = int(m.group(1))
        if 1 <= amount <= 10:
            async with AsyncSessionLocal() as session:
                user = await get_or_create_user(session, telegram_id=update.effective_user.id)
                await update_settings(session, user, daily_amount=amount)
            await update.message.reply_text(
                f"✅ تم تغيير المقدار اليومي إلى <b>{amount} وجه</b>\n"
                "<i>تم إعادة حساب التحضير الأسبوعي تلقائيًا.</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_today_inline(),
                disable_web_page_preview=True,
            )
            return True

    # === "صفحة X" / "سورة Y" — تعديل آخر محفوظ ===
    if any(k in text_lower for k in ["صفحة", "سورة", "جزء", "ختمت"]):
        parsed = await parse_memorization_input(text)
        if parsed["page"] is not None:
            async with AsyncSessionLocal() as session:
                user = await get_or_create_user(session, telegram_id=update.effective_user.id)
                await set_initial_hifz(session, user, parsed["page"])
            await update.message.reply_text(
                f"✅ تم ضبط آخر وجه محفوظ على <b>{parsed['page']}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_today_inline(),
                disable_web_page_preview=True,
            )
            return True

    return False

# ══════════════════════════════════════════════════════════════════════
# ═══ 23. موجّه أزرار Inline ═══
# المصدر: callback_router.py
# ══════════════════════════════════════════════════════════════════════

"""
الموجّه الرئيسي لكل أزرار Inline — يربط callback_data بالمعالجات.
"""



logger = logging.getLogger(__name__)

# خريطة أنواع المهام


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """المعالج الموحَّد لكل أزرار Inline."""
    query = update.callback_query
    data = query.data or ""

    # لأزرار المهام: نُجيب لاحقًا مع toast مخصَّص
    is_task_button = data.startswith("task_") and data[5:] in TASK_FIELD_MAP
    if not is_task_button:
        try:
            await query.answer()
        except Exception as e:
            logger.warning(f"تعذّر answer_callback_query: {e}")

    # ====== Onboarding: الخطوة 1 ======
    if data == "ob_0":
        await process_onboarding_memorization(update, context, "0")
        return
    if data == "ob_all":
        await process_onboarding_memorization(update, context, "ختمت القرآن")
        return
    if data == "ob_manual":
        ONBOARDING_STATE[update.effective_user.id] = "ob_step_1_memorization"
        text = (
            "✍️ <b>اكتبي إجابتك الآن</b>\n\n"
            "أمثلة:\n"
            "• <code>صفحة 127</code>\n"
            "• <code>سورة المائدة</code>\n"
            "• <code>جزء 7</code>\n"
            "• <code>0</code> (لم أحفظ)"
        )
        await safe_edit_message(query, text, None)
        return
    m = re.match(r"^ob_surah_(\d+)$", data)
    if m:
        surah_num = int(m.group(1))
        surah = quran_data.get_surah_by_number(surah_num)
        if surah:
            await process_onboarding_memorization(update, context, f"سورة {surah.name_ar}")
        return

    # ====== Onboarding: الخطوة 2 (مقدار يومي) ======
    m = re.match(r"^ob_daily_(\d+|custom)$", data)
    if m:
        val = m.group(1)
        if val == "custom":
            ONBOARDING_STATE[update.effective_user.id] = "ob_step_2_daily_amount_custom"
            text = "✍️ أرسلي رقمًا (1-10):"
            await safe_edit_message(query, text, None)
            return
        amount = int(val)
        if amount in (1, 2):
            async with AsyncSessionLocal() as session:
                user = await get_or_create_user(session, telegram_id=update.effective_user.id)
                await update_settings(session, user, daily_amount=amount)
            await ask_weekly_amount(update, context)
        return

    # ====== Onboarding: الخطوة 3 (مقدار أسبوعي) ======
    m = re.match(r"^ob_weekly_(\d+)$", data)
    if m:
        amount = int(m.group(1))
        if amount in (5, 7, 10, 14):
            async with AsyncSessionLocal() as session:
                user = await get_or_create_user(session, telegram_id=update.effective_user.id)
                await update_settings(session, user, weekly_amount=amount)
            await ask_plan_start_date(update, context)
        return

    # ====== Onboarding: الخطوة 4 (تاريخ البداية) ======
    if data == "ob_plan_today":
        async with AsyncSessionLocal() as session:
            user = await get_or_create_user(session, telegram_id=update.effective_user.id)
            await update_settings(session, user, plan_start_date=date_cls.today())
        await ask_reminder_times(update, context)
        return
    if data == "ob_plan_manual":
        ONBOARDING_STATE[update.effective_user.id] = "ob_step_4_plan_start_manual"
        text = "✍️ أرسلي التاريخ بصيغة <code>YYYY-MM-DD</code>:"
        await safe_edit_message(query, text, None)
        return

    # ====== Onboarding: الخطوة 5 (التذكيرات) ======
    if data in ("ob_reminders_default", "ob_reminders_customize"):
        await finalize_onboarding(update, context)
        return

    # ====== التنقّل العام ======
    if data == "main_panel":
        await show_main_panel(update, context)
        return
    if data == "today_dashboard":
        await show_today_dashboard(update, context)
        return
    if data == "fortresses_menu":
        await show_fortresses_menu(update, context)
        return
    if data == "show_progress":
        await show_progress(update, context)
        return
    if data == "show_activity_log":
        await show_activity_log(update, context)
        return
    if data == "show_help":
        await show_help(update, context)
        return
    if data == "close_inline":
        await safe_edit_message(query, "👇 اختَر من القائمة بالأسفل", None)
        return
    if data == "start_pre_session":
        await show_pre_session_start(update, context)
        return

    # ====== الحصون الخمسة ======
    if data == "fortress_1":
        await show_fortress_1(update, context)
        return
    if data == "fortress_2":
        await show_fortress_2(update, context)
        return
    if data == "fortress_3":
        await show_fortress_3(update, context)
        return
    if data == "fortress_4":
        await show_fortress_4(update, context)
        return
    if data == "fortress_5":
        await show_fortress_5(update, context)
        return

    # ====== أزرار المهام (Toggleable) ======
    m = re.match(r"^task_(.+)$", data)
    if m:
        task_type = m.group(1)
        if task_type in TASK_FIELD_MAP:
            await handle_task_button(update, context, task_type)
            return

    # ====== لوحة الإعدادات ======
    if data == "set_last_page":
        await ask_last_page(update, context)
        return
    if data == "set_daily_amount":
        await settings_ask_daily(update, context)
        return
    if data == "set_weekly_amount":
        await settings_ask_weekly(update, context)
        return
    if data == "set_reading_hizb":
        await ask_reading_hizb(update, context)
        return
    if data == "set_listening_hizb":
        await ask_listening_hizb(update, context)
        return
    if data == "set_far_cycle":
        await ask_far_cycle(update, context)
        return
    if data == "set_reminders":
        await show_reminders_settings(update, context)
        return
    if data == "set_notifications":
        await ask_notifications(update, context)
        return
    if data == "set_suggestions":
        await show_suggestions(update, context)
        return
    # إعدادات سريعة (من لوحة الإعدادات)
    m = re.match(r"^ob_daily_(\d+)$", data)  # يطابق أيضًا أزرار الإعدادات السريعة
    if m:
        amount = int(m.group(1))
        if amount in (1, 2, 5, 7, 10, 14):
            async with AsyncSessionLocal() as session:
                user = await get_or_create_user(session, telegram_id=update.effective_user.id)
                # نحدد إذا كان يومي أم أسبوعي حسب القيمة
                if amount in (1, 2):
                    await update_settings(session, user, daily_amount=amount)
                else:
                    await update_settings(session, user, weekly_amount=amount)
            await show_settings_panel(update, context)
            return

    # ====== تأكيد/إلغاء (للتعديلات اليدوية) ======
    if data == "cancel_action":
        await show_settings_panel(update, context)
        return

    logger.warning(f"callback_data غير معروف: {data}")

# ══════════════════════════════════════════════════════════════════════
# ═══ 24. معالجات الأوامر النصية ═══
# المصدر: commands.py
# ══════════════════════════════════════════════════════════════════════

"""
معالجات الأوامر النصية: /start /help /today /progress /settings /update /settime ...
"""



logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /start — يبدأ الـ onboarding أو يعرض لوحة التحكم الشاملة."""
    user_info = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, user_info.id, user_info.username, user_info.full_name)
        needs_onboarding = not user.onboarding_done

    if needs_onboarding:
        await start_onboarding(update, context, welcome=True)
        return

    await update.message.reply_text(
        f"👋 <b>أهلًا بعودتك!</b> 🌟\nإليكِ <b>لوحة التحكم</b> 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )
    await show_main_panel(update, context)


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_today_dashboard(update, context)


async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /panel — يعرض لوحة التحكم الشاملة."""
    await show_main_panel(update, context)


async def progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_progress(update, context)


async def fortresses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_fortresses_menu(update, context)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_settings_panel(update, context)


async def activity_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_activity_log(update, context)


async def suggestions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_suggestions(update, context)


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /update <value> — تحديث آخر وجه محفوظ.
    
    صيغ مدعومة:
        /update 50
        /update سورة المائدة
        /update جزء 7
        /update صفحة 100
    """
    if not context.args:
        await update.message.reply_text(
            "📝 <b>تحديث آخر وجه محفوظ</b>\n\n"
            "استخدم:\n"
            "• <code>/update 50</code>\n"
            "• <code>/update سورة المائدة</code>\n"
            "• <code>/update جزء 7</code>\n"
            "• <code>/update 0</code> (لم أحفظ)",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
        return

    text = " ".join(context.args)
    parsed = await parse_memorization_input(text)
    if parsed["page"] is None:
        await update.message.reply_text(
            "❌ <b>لم أفهم الإدخال</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
        return

    page = parsed["page"]
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        await set_initial_hifz(session, user, page)

    await update.message.reply_text(
        f"✅ تم ضبط آخر وجه محفوظ على <b>{page}</b>\n"
        "<i>تم إعادة حساب جميع المهام تلقائيًا.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )
    await show_today_dashboard(update, context)


async def settime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /settime <type> <HH:MM> — تعديل وقت تذكير.
    
    مثال: /settime memorize 06:00
    """
    if len(context.args) < 2:
        labels = config.REMINDER_LABELS_AR
        types_list = "\n".join(f"• <code>{t}</code> — {labels[t]}" for t in config.REMINDER_TYPES)
        await update.message.reply_text(
            "⏰ <b>تعديل وقت تذكير</b>\n\n"
            "الصيغة: <code>/settime نوع HH:MM</code>\n\n"
            "الأنواع:\n" + types_list,
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
        return

    rtype = context.args[0].lower()
    time_str = context.args[1]
    if rtype not in config.REMINDER_TYPES:
        await update.message.reply_text(
            f"❌ نوع غير صحيح: <code>{rtype}</code>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    try:
        hour, minute = time_str.split(":")
        int(hour); int(minute)
        if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
            raise ValueError
    except (ValueError, IndexError):
        await update.message.reply_text(
            f"❌ صيغة وقت غير صحيحة: <code>{time_str}</code>\n"
            "مثال صحيح: <code>06:30</code>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        result = await session.execute(
            select(UserSettings).where(
                UserSettings.user_id == user.id,
                UserSettings.reminder_type == rtype,
            )
        )
        s = result.scalar_one_or_none()
        if s is None:
            s = UserSettings(user_id=user.id, reminder_type=rtype, reminder_time=time_str, enabled=True)
            session.add(s)
        else:
            s.reminder_time = time_str
        await session.commit()

    # إعادة جدولة هذا التذكير
    await schedule_user_jobs(context.bot, user)

    await update.message.reply_text(
        f"✅ تم ضبط تذكير <b>{config.REMINDER_LABELS_AR[rtype]}</b> على <code>{time_str}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


async def setamount_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /setamount <daily|weekly> <N> — تعديل المقدار."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "📊 <b>تعديل المقدار</b>\n\n"
            "الصيغة: <code>/setamount daily 2</code> أو <code>/setamount weekly 7</code>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    kind = context.args[0].lower()
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ المقدار يجب أن يكون رقمًا", parse_mode=ParseMode.HTML)
        return

    if kind not in ("daily", "weekly"):
        await update.message.reply_text("❌ النوع يجب أن يكون <code>daily</code> أو <code>weekly</code>", parse_mode=ParseMode.HTML)
        return

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if kind == "daily":
            await update_settings(session, user, daily_amount=amount)
        else:
            await update_settings(session, user, weekly_amount=amount)

    label = "اليومي" if kind == "daily" else "الأسبوعي"
    await update.message.reply_text(
        f"✅ تم تعديل المقدار {label} إلى <b>{amount} وجه</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


async def notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /notifications on|off."""
    if not context.args:
        await update.message.reply_text(
            "🔔 <b>الإشعارات</b>\n\nاستخدم: <code>/notifications on</code> أو <code>/notifications off</code>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    state = context.args[0].lower() in ("on", "true", "1", "نعم")
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        await update_settings(session, user, notifications=state)
    await update.message.reply_text(
        f"✅ الإشعارات الآن: <b>{'مفعّلة' if state else 'معطّلة'}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض دليل الاستخدام."""
    text = (
        "📚 <b>دليل بوت الحصون الخمسة</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🏰 <b>المنهجية:</b>\n"
        "• <b>الحصن 1:</b> التهيئة (قراءة 30 يومًا + استماع 60 يومًا)\n"
        "• <b>الحصن 2:</b> التحضير (أسبوعي + ليلي + قبلي 15 دقيقة)\n"
        "• <b>الحصن 3:</b> الحفظ الجديد (الوجه القادم)\n"
        "• <b>الحصن 4:</b> مراجعة القريب (آخر 20 وجه)\n"
        "• <b>الحصن 5:</b> مراجعة البعيد (40 وجه/دورة)\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🎮 <b>الأزرار:</b>\n"
        "• <b>📋 ورد اليوم</b> — كل المهام + أزرار تسجيل\n"
        "• <b>📊 تقدمي</b> — لوحة الإحصائيات\n"
        "• <b>🏰 الحصون الخمسة</b> — تفاصيل كل حصن\n"
        "• <b>⚙️ الإعدادات</b> — تعديل كل شيء\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <b>أوامر نصية:</b>\n"
        "• <code>/today</code> — ورد اليوم\n"
        "• <code>/progress</code> — التقدم\n"
        "• <code>/update 50</code> — تعديل آخر محفوظ\n"
        "• <code>/settime memorize 06:00</code> — وقت التذكير\n"
        "• <code>/setamount daily 2</code> — المقدار\n"
        "• <code>/notifications off</code> — تعطيل الإشعارات\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🗣️ <b>أوامر طبيعية:</b>\n"
        "• «وش نحفظ اليوم؟»\n"
        "• «وين وصلت؟»\n"
        "• «حفظت الوجه 41»\n"
        "• «قريت الورد»\n"
        "• «اليوم ما قدرت»\n\n"
        "🤲 <i>اللهم اجعل القرآن ربيع قلوبنا</i>"
    )
    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )

# ══════════════════════════════════════════════════════════════════════
# ═══ 25. معالج الأخطاء ═══
# المصدر: error_handler.py
# ══════════════════════════════════════════════════════════════════════

"""
معالج الأخطاء الموحَّد.
"""



logger = logging.getLogger(__name__)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج موحَّد للأخطاء."""
    error = context.error

    if isinstance(error, Conflict):
        logger.warning(f"⚠️ Conflict (تجاهل): {error}")
        if update and getattr(update, "callback_query", None):
            try: await update.callback_query.answer()
            except Exception: pass
        return

    if isinstance(error, TimedOut):
        logger.warning(f"⚠️ TimedOut (تجاهل): {error}")
        return

    if isinstance(error, Forbidden):
        logger.warning(f"⚠️ المستخدم حظر البوت: {error}")
        return

    if isinstance(error, BadRequest):
        msg = str(error).lower()
        if "not modified" in msg:
            return  # لا خطأ
        logger.error(f"❌ BadRequest: {error}", exc_info=False)
        if update and getattr(update, "effective_chat", None):
            try:
                if getattr(update, "callback_query", None):
                    try: await update.callback_query.answer()
                    except Exception: pass
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ حدث خطأ بسيط. جرّب مرة أخرى أو /start",
                    reply_markup=main_keyboard(),
                )
            except Exception:
                pass
        return

    if isinstance(error, NetworkError):
        logger.warning(f"⚠️ خطأ شبكة: {error}")
        return

    logger.error(f"❌ خطأ: {type(error).__name__}: {error}", exc_info=True)
    if update and getattr(update, "effective_chat", None):
        try:
            if getattr(update, "callback_query", None):
                try: await update.callback_query.answer()
                except Exception: pass
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ حدث خطأ غير متوقع. جرّب مرة أخرى أو /start",
                reply_markup=main_keyboard(),
            )
        except Exception:
            pass

# ══════════════════════════════════════════════════════════════════════
# ═══ 26. المجدول — التذكيرات ═══
# المصدر: reminders.py
# ══════════════════════════════════════════════════════════════════════

"""
المجدول — 8 تذكيرات يومية لكل مستخدم.
"""



logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


REMINDER_MESSAGES = {
    "memorize":      "🆕 <b>تذكير الحفظ</b>\n\nحان وقت الحفظ اليومي. ابدأ ببسم الله 🤲",
    "reading":       "📖 <b>تذكير القراءة</b>\n\nوقت ورد القراءة اليومي. حزبان فقط!",
    "weekly_prep":   "📚 <b>تذكير التحضير الأسبوعي</b>\n\nاقرأ أوجه الأسبوع القادم قبل بدء حفظها.",
    "pre_session":   "⏱️ <b>تذكير التحضير القبلي</b>\n\nاقرأ الوجه المطلوب 15 دقيقة قبل الحفظ.",
    "listening":     "🎧 <b>تذكير الاستماع</b>\n\nوقت الاستماع لحزب اليوم.",
    "near_review":   "🔄 <b>تذكير مراجعة القريب</b>\n\nراجع آخر 20 وجه محفوظ اليوم.",
    "far_review":    "🔁 <b>تذكير مراجعة البعيد</b>\n\nحان وقت مراجعة الدورة الحالية (40 وجه).",
    "nightly_prep":  "🌙 <b>تذكير التحضير الليلي</b>\n\nقبل النوم، اقرأ وجه الغد استعدادًا له.",
}


async def send_reminder(bot, user_id: int, reminder_type: str):
    """إرسال تذكير لمستخدم معيّن."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user or not user.onboarding_done or not user.notifications_enabled:
            return

    try:
        await bot.send_message(
            chat_id=user_id,
            text=REMINDER_MESSAGES.get(reminder_type, "📅 تذكير"),
            parse_mode="HTML",
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
        logger.info(f"📧 تذكير {reminder_type} أُرسل للمستخدم {user_id}")
    except Exception as e:
        logger.warning(f"تعذّر إرسال تذكير {reminder_type} لـ {user_id}: {e}")


async def schedule_user_jobs(bot, user: User):
    """جدولة 8 وظائف تذكير لمستخدم معيّن."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        settings_list = list(result.scalars().all())

    settings_by_type = {s.reminder_type: s for s in settings_list}
    tz = user.timezone or config.DEFAULT_TIMEZONE

    for reminder_type in config.REMINDER_TYPES:
        s = settings_by_type.get(reminder_type)
        if not s or not s.enabled:
            continue

        job_id = f"reminder_{user.telegram_id}_{reminder_type}"
        # إزالة أي وظيفة سابقة بنفس الاسم
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass

        try:
            hour, minute = s.reminder_time.split(":")
            trigger = CronTrigger(hour=int(hour), minute=int(minute), timezone=tz)
            scheduler.add_job(
                send_reminder,
                trigger=trigger,
                args=[bot, user.telegram_id, reminder_type],
                id=job_id,
                replace_existing=True,
            )
        except Exception as e:
            logger.warning(f"تعذّر جدولة تذكير {reminder_type} لـ {user.telegram_id}: {e}")


async def schedule_all_users_jobs(bot):
    """جدولة كل المستخدمين عند بدء التشغيل.

    ملاحظة: إذا فشلت الجدولة لأي سبب، لا يمنع ذلك البوت من العمل.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.onboarding_done == True))
            users = list(result.scalars().all())

        for user in users:
            try:
                await schedule_user_jobs(bot, user)
            except Exception as e:
                logger.warning(f"⚠️ تعذّرت جدولة تذكيرات المستخدم {user.telegram_id}: {e}")
        logger.info(f"✅ تمت جدولة التذكيرات لـ {len(users)} مستخدم")
    except Exception as e:
        logger.warning(f"⚠️ تعذّر تحميل المستخدمين للجدولة: {e}")
        logger.warning("   البوت سيعمل بدون تذكيرات حتى تُحل المشكلة")


async def start_scheduler():
    """بدء المجدول."""
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ بدأ المجدول")


async def shutdown_scheduler():
    """إيقاف المجدول."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("✅ أوقف المجدول")

# ══════════════════════════════════════════════════════════════════════
# ═══ 27. خادم Keep-alive ═══
# المصدر: keepalive.py
# ══════════════════════════════════════════════════════════════════════

"""
خادم Keep-alive بسيط — يبقي Render مستيقظًا.
"""

logger = logging.getLogger(__name__)


async def _health(request):
    return web.Response(text="OK — Quran Fortresses Bot is running ✅")


async def start_keepalive_server(port: int):
    """يبدأ خادم HTTP بسيط على المنفذ المحدد."""
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 خادم keep-alive يعمل على المنفذ {port}")
    return runner


async def start_self_ping(interval: int = 280):
    """ينشئ ping دوري لنفسه عبر RENDER_EXTERNAL_URL."""
    public_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not public_url:
        logger.warning("⚠️ RENDER_EXTERNAL_URL غير مضبوط — لن يعمل self-ping")
        return None

    async def _ping_loop():
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(f"{public_url}/health", timeout=10) as resp:
                        if resp.status == 200:
                            logger.debug("🔄 self-ping OK")
                        else:
                            logger.warning(f"⚠️ self-ping status={resp.status}")
                except Exception as e:
                    logger.warning(f"⚠️ self-ping فشل: {e}")
                await asyncio.sleep(interval)

    task = asyncio.create_task(_ping_loop())
    return task

# ═══════════════════════════════════════════
# ═══ 28. التطبيق الرئيسي ونقطة الدخول ═══
# ═══════════════════════════════════════════

try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def post_init(app):
    """يُستدعى بعد بناء التطبيق وقبل بدء التحديثات."""
    await init_db()
    await start_scheduler()
    await schedule_all_users_jobs(app.bot)

    if config.KEEPALIVE_ENABLED:
        try:
            runner = await start_keepalive_server(config.PORT)
            app._keepalive_runner = runner
            app._keepalive_task = await start_self_ping(config.KEEPALIVE_INTERVAL)
            logger.info("✅ keep-alive نشط")
        except Exception as e:
            logger.warning(f"⚠️ تعذّر بدء keep-alive: {e}")


async def post_shutdown(app):
    """يُستدعى عند إيقاف التطبيق."""
    task = getattr(app, "_keepalive_task", None)
    runner = getattr(app, "_keepalive_runner", None)
    if task:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    if runner:
        await runner.cleanup()
    await shutdown_scheduler()
    await close_db()


def build_application():
    """يبني تطبيق Telegram."""
    if not config.BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN غير مضبوط")
        print("❌ TELEGRAM_BOT_TOKEN غير مضبوط — تحقق من متغيرات البيئة", flush=True)
        sys.exit(1)

    app = (
        ApplicationBuilder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .read_timeout(15)
        .write_timeout(15)
        .connect_timeout(10)
        .pool_timeout(10)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("panel", panel_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("fortresses", fortresses_command))
    app.add_handler(CommandHandler("progress", progress_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("activity", activity_command))
    app.add_handler(CommandHandler("suggestions", suggestions_command))
    app.add_handler(CommandHandler("update", update_command))
    app.add_handler(CommandHandler("settime", settime_command))
    app.add_handler(CommandHandler("setamount", setamount_command))
    app.add_handler(CommandHandler("notifications", notifications_command))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)

    return app


def main():
    """نقطة الدخول الرئيسية."""
    try:
        print("📖 بوت الحصون الخمسة — الإصدار 4.1.0 — البدء", flush=True)
        print(f"  - المنطقة الزمنية: {config.DEFAULT_TIMEZONE}", flush=True)
        print(f"  - قاعدة البيانات: {config.DATABASE_URL[:50] if config.DATABASE_URL else 'in-memory'}...", flush=True)
        print(f"  - PostgreSQL: {config.is_postgres()}", flush=True)
        print(f"  - BOT_TOKEN مضبوط: {bool(config.BOT_TOKEN)}", flush=True)
        print(f"  - keep-alive: {'مُفعّل' if config.KEEPALIVE_ENABLED else 'مُعطّل'}", flush=True)
        logger.info("📖 بوت الحصون الخمسة — الإصدار 4.1.0 — البدء")

        app = build_application()
        print("🚀 تشغيل البوت في وضع polling...", flush=True)
        logger.info("🚀 تشغيل البوت في وضع polling...")
        app.run_polling(poll_interval=1, drop_pending_updates=True, close_loop=False)
    except SystemExit:
        print("⚠️ الخروج — يُرجى التحقق من TELEGRAM_BOT_TOKEN في متغيرات البيئة", flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
        raise
    except Exception as e:
        print("❌ خطأ أثناء التشغيل:", flush=True)
        print(traceback.format_exc(), flush=True)
        logger.error("❌ خطأ أثناء التشغيل:")
        logger.error(traceback.format_exc())
        sys.stdout.flush()
        sys.stderr.flush()
        raise


if __name__ == "__main__":
    main()
