"""
بوت تلغرام لحفظ القرآن — طريقة الحصون الخمسة (الإصدار الكامل v3)
================================================================

المميزات الجديدة:
- ختمة قراءة كل 30 يومًا (حزبان/يوم) تبدأ من تاريخ بداية الخطة
- ختمة استماع كل 60 يومًا (حزب/يوم) تبدأ من تاريخ بداية الخطة
- تحضير أسبوعي: المستخدمة تحدد المقدار، البوت يحسب النطاق
- تحضير ليلي + تحضير قبلي (مع مؤقّت: زر بدء + زر انتهيت)
- دورة مراجعة بعيدة (40 وجهًا/دورة)، تنتقل تلقائيًا للدورة التالية
- 8 تذكيرات يومية قابلة للضبط
- سجل إنجاز يومي + أيام التزام متتالية (streak)
- مصطلح "وجه" موحَّد في كل النصوص
- Migration آمن لا يُضيع البيانات الموجودة

التشغيل: python bot.py
"""

# ============== 1. الإعدادات ==============
import os
import sys
import asyncio
import logging
import re
import html
from datetime import date, datetime, timedelta
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_raw_db = os.getenv("DATABASE_URL", "").strip()
DATABASE_URL = _raw_db.replace("postgres://", "postgresql://")
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0") or "0")

DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Africa/Algiers")

PORT = int(os.getenv("PORT", "10000"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
KEEPALIVE_ENABLED = os.getenv("KEEPALIVE_ENABLED", "true").lower() == "true"
KEEPALIVE_INTERVAL = int(os.getenv("KEEPALIVE_INTERVAL", "280"))

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ============== 2. قاعدة البيانات ==============
from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer, String, Boolean, Text,
    func, UniqueConstraint, select, and_, text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine
)


class Base(DeclarativeBase):
    pass


_ASYNCPG_FORBIDDEN_PARAMS = {"sslmode", "channel_binding", "sslrootcert", "sslcert", "sslkey"}


def _strip_forbidden_params(url: str) -> str:
    if not url.startswith("postgresql://"):
        return url
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    for key in _ASYNCPG_FORBIDDEN_PARAMS:
        query.pop(key, None)
    new_query = urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


def _to_async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        url = _strip_forbidden_params(url)
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("file:"):
        url = url.replace("file:", "sqlite:///", 1)
    if not url.startswith("sqlite://"):
        url = "sqlite:///" + url.lstrip("/")
    if url.startswith("sqlite:///") and not url.startswith("sqlite+aiosqlite://"):
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


_is_postgres = DATABASE_URL.startswith("postgresql://")


def _mask_url(url: str) -> str:
    if "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            creds, host_part = rest.split("@", 1)
            if ":" in creds:
                user, _pw = creds.split(":", 1)
                return f"{scheme}://{user}:****@{host_part}"
            return f"{scheme}://****@{host_part}"
        return f"{scheme}://{rest}"
    return url


print("=" * 70, flush=True)
print(f"[DEBUG] DATABASE_URL raw length: {len(_raw_db)}", flush=True)
print(f"[DEBUG] DATABASE_URL (masked): {_mask_url(DATABASE_URL) if DATABASE_URL else '(empty)'}", flush=True)
print(f"[DEBUG] DATABASE_URL starts with postgresql:// : {_is_postgres}", flush=True)
print(f"[DEBUG] TELEGRAM_BOT_TOKEN set: {bool(BOT_TOKEN)}", flush=True)
print(f"[DEBUG] ADMIN_TELEGRAM_ID: {ADMIN_ID}", flush=True)
print("=" * 70, flush=True)
sys.stdout.flush()

if not DATABASE_URL:
    print("❌ خطأ: DATABASE_URL غير مضبوط!", flush=True)
    sys.exit(1)

if not _is_postgres:
    print(f"❌ خطأ: DATABASE_URL يجب أن يبدأ بـ postgresql://", flush=True)
    sys.exit(1)

_engine_kwargs = {"echo": False}
if _is_postgres:
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10
    _engine_kwargs["connect_args"] = {"ssl": True}

engine = create_async_engine(_to_async_url(DATABASE_URL), **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ============== 3. النماذج ==============

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # الحقول الأساسية للحفظ
    current_page: Mapped[int] = mapped_column(Integer, default=1)
    start_page: Mapped[int] = mapped_column(Integer, default=1)
    last_memorized_page: Mapped[int] = mapped_column(Integer, default=0)
    total_memorized: Mapped[int] = mapped_column(Integer, default=0)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False)

    # ====== حقول الإصدار v3 الجديدة ======
    # تاريخ بداية الخطة (تستخدم لدورات القراءة 30ي والاستماع 60ي)
    plan_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # مقدار الحفظ اليومي (1 أو 2 وجهًا)
    daily_memo_amount: Mapped[int] = mapped_column(Integer, default=2)
    # مقدار الحفظ الأسبوعي (مثلاً 7 أوجه/أسبوع) — يحدد نطاق التحضير الأسبوعي
    weekly_memo_amount: Mapped[int] = mapped_column(Integer, default=7)
    # بداية نطاق التحضير الأسبوعي القادم (يُحسب تلقائيًا = last_memorized_page + 1)
    weekly_prep_start: Mapped[int] = mapped_column(Integer, default=1)
    weekly_prep_end: Mapped[int] = mapped_column(Integer, default=7)
    # رقم دورة المراجعة البعيدة الحالية (1, 2, 3...)
    far_review_cycle: Mapped[int] = mapped_column(Integer, default=1)
    # أيام الالتزام المتتالية
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # عدد ختمات القراءة المنجزة (تزداد كل 30 يومًا)
    reading_khatmah_count: Mapped[int] = mapped_column(Integer, default=0)
    # عدد ختمات الاستماع المنجزة (تزداد كل 60 يومًا)
    listening_khatmah_count: Mapped[int] = mapped_column(Integer, default=0)

    # ====== أوقات التذكيرات الـ 8 ======
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Algiers")
    reminder_reading: Mapped[str] = mapped_column(String(5), default="08:00")
    reminder_listening: Mapped[str] = mapped_column(String(5), default="13:00")
    reminder_weekly_prep: Mapped[str] = mapped_column(String(5), default="09:00")
    reminder_nightly_prep: Mapped[str] = mapped_column(String(5), default="21:00")
    reminder_pre_session: Mapped[str] = mapped_column(String(5), default="10:00")
    reminder_memorize: Mapped[str] = mapped_column(String(5), default="06:00")
    reminder_near_review: Mapped[str] = mapped_column(String(5), default="16:00")
    reminder_far_review: Mapped[str] = mapped_column(String(5), default="20:00")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    memorization: Mapped[list["Memorization"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    weekly_reviews: Mapped[list["WeeklyReview"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    monthly_reviews: Mapped[list["MonthlyReview"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    daily_progress: Mapped[list["DailyProgress"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    achievement_logs: Mapped[list["AchievementLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Memorization(Base):
    __tablename__ = "memorization"
    __table_args__ = (UniqueConstraint("user_id", "page_number", name="uq_user_page"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, index=True)
    date_memorized: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reviewed: Mapped[date | None] = mapped_column(Date, nullable=True)
    user: Mapped["User"] = relationship(back_populates="memorization")


class WeeklyReview(Base):
    __tablename__ = "weekly_reviews"
    __table_args__ = (UniqueConstraint("user_id", "page_number", name="uq_weekly_user_page"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, index=True)
    review_1_layla: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_2_layl: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_3_thuluth: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_4_arbain: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_5_khamis: Mapped[date | None] = mapped_column(Date, nullable=True)
    done_1: Mapped[bool] = mapped_column(Boolean, default=False)
    done_2: Mapped[bool] = mapped_column(Boolean, default=False)
    done_3: Mapped[bool] = mapped_column(Boolean, default=False)
    done_4: Mapped[bool] = mapped_column(Boolean, default=False)
    done_5: Mapped[bool] = mapped_column(Boolean, default=False)
    date_memorized: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    user: Mapped["User"] = relationship(back_populates="weekly_reviews")


class MonthlyReview(Base):
    __tablename__ = "monthly_reviews"
    __table_args__ = (UniqueConstraint("user_id", "year", "month", name="uq_monthly_user_period"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    pages_reviewed: Mapped[str] = mapped_column(String(512), default="")
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    user: Mapped["User"] = relationship(back_populates="monthly_reviews")


class DailyProgress(Base):
    __tablename__ = "daily_progress"
    __table_args__ = (UniqueConstraint("user_id", "progress_date", name="uq_progress_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    progress_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())

    # الحصن الأول — التهيئة
    reading_done: Mapped[bool] = mapped_column(Boolean, default=False)
    reading_pages: Mapped[str] = mapped_column(String(64), default="")
    listening_done: Mapped[bool] = mapped_column(Boolean, default=False)
    listening_pages: Mapped[str] = mapped_column(String(64), default="")

    # الحصن الثاني — التحضير
    weekly_prep_done: Mapped[bool] = mapped_column(Boolean, default=False)
    nightly_prep_done: Mapped[bool] = mapped_column(Boolean, default=False)
    nightly_prep_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pre_session_prep_done: Mapped[bool] = mapped_column(Boolean, default=False)
    pre_session_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pre_session_duration_min: Mapped[int] = mapped_column(Integer, default=0)

    # الحصن الثالث — الحفظ
    memorize_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memorize_done: Mapped[bool] = mapped_column(Boolean, default=False)

    # الحصن الرابع — مراجعة القريب
    near_review_done: Mapped[bool] = mapped_column(Boolean, default=False)

    # الحصن الخامس — مراجعة البعيد
    far_review_done: Mapped[bool] = mapped_column(Boolean, default=False)

    # الحالة الإجمالية للمهام
    task_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/partial/completed/postponed

    daily_review_done: Mapped[bool] = mapped_column(Boolean, default=False)  # للتوافق مع الإصدار السابق

    user: Mapped["User"] = relationship(back_populates="daily_progress")


class AchievementLog(Base):
    """سجل إنجاز يومي دائم — يُسجّل نهاية كل يوم (أو عند أول نشاط في اليوم التالي)."""
    __tablename__ = "achievement_log"
    __table_args__ = (UniqueConstraint("user_id", "log_date", name="uq_achievement_log_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    log_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    overall_status: Mapped[str] = mapped_column(String(20), default="missed")  # completed/partial/missed
    reading_done: Mapped[bool] = mapped_column(Boolean, default=False)
    listening_done: Mapped[bool] = mapped_column(Boolean, default=False)
    weekly_prep_done: Mapped[bool] = mapped_column(Boolean, default=False)
    nightly_prep_done: Mapped[bool] = mapped_column(Boolean, default=False)
    pre_session_prep_done: Mapped[bool] = mapped_column(Boolean, default=False)
    memorize_done: Mapped[bool] = mapped_column(Boolean, default=False)
    near_review_done: Mapped[bool] = mapped_column(Boolean, default=False)
    far_review_done: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    user: Mapped["User"] = relationship(back_populates="achievement_logs")


async def init_db():
    """إنشاء الجداول + Migration آمن لإضافة الحقول الجديدة للجداول الموجودة."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if _is_postgres:
            migration_statements = [
                # ====== حقول User الجديدة (v3) ======
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_start_date DATE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_memo_amount INTEGER DEFAULT 2",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_memo_amount INTEGER DEFAULT 7",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_prep_start INTEGER DEFAULT 1",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_prep_end INTEGER DEFAULT 7",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS far_review_cycle INTEGER DEFAULT 1",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS streak_days INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_date DATE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS reading_khatmah_count INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS listening_khatmah_count INTEGER DEFAULT 0",
                # أوقات التذكيرات الـ 8
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_reading VARCHAR(5) DEFAULT '08:00'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_listening VARCHAR(5) DEFAULT '13:00'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_weekly_prep VARCHAR(5) DEFAULT '09:00'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_nightly_prep VARCHAR(5) DEFAULT '21:00'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_pre_session VARCHAR(5) DEFAULT '10:00'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_memorize VARCHAR(5) DEFAULT '06:00'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_near_review VARCHAR(5) DEFAULT '16:00'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_far_review VARCHAR(5) DEFAULT '20:00'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS notifications_enabled BOOLEAN DEFAULT TRUE",
                # تحديث last_memorized_page من الإصدار السابق
                "UPDATE users SET last_memorized_page = GREATEST(0, current_page - 1) "
                "WHERE last_memorized_page = 0 AND current_page > 1",
                # ضبط plan_start_date = created_at للحقول القديمة
                "UPDATE users SET plan_start_date = created_at WHERE plan_start_date IS NULL",
                # ====== حقول DailyProgress الجديدة ======
                "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS weekly_prep_done BOOLEAN DEFAULT FALSE",
                "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS nightly_prep_done BOOLEAN DEFAULT FALSE",
                "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS nightly_prep_page INTEGER",
                "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS pre_session_prep_done BOOLEAN DEFAULT FALSE",
                "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS pre_session_started_at TIMESTAMP",
                "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS pre_session_duration_min INTEGER DEFAULT 0",
                "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS near_review_done BOOLEAN DEFAULT FALSE",
                "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS far_review_done BOOLEAN DEFAULT FALSE",
                "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS task_status VARCHAR(20) DEFAULT 'pending'",
                # توسيع reading_pages/listening_pages من 32 إلى 64
                "ALTER TABLE daily_progress ALTER COLUMN reading_pages TYPE VARCHAR(64)",
                "ALTER TABLE daily_progress ALTER COLUMN listening_pages TYPE VARCHAR(64)",
            ]
            for stmt in migration_statements:
                try:
                    await conn.execute(text(stmt))
                except Exception as e:
                    logger.warning(f"Migration (تجاهل): {e}")
    logger.info("✅ قاعدة البيانات جاهزة (مع migrations)")


# ============== 4. المنطق الأساسي ==============
import quran_data as quran_data

# ====== الثوابت ======
NEAR_REVIEW_PAGES = 20     # الحصن الرابع
FAR_REVIEW_PAGES = 40      # الحصن الخامس — حجم الدورة الواحدة
READING_CYCLE_DAYS = 30    # ختمة قراءة كل 30 يومًا (حزبان/يوم × 30 = 60 حزب = 604 صفحة تقريبًا)
LISTENING_CYCLE_DAYS = 60  # ختمة استماع كل 60 يومًا (حزب/يوم × 60 = 60 حزب)
PAGES_PER_READING_DAY = 20  # حزبان/يوم
PAGES_PER_LISTENING_DAY = 10  # حزب/يوم


async def get_or_create_user(session, telegram_id, username=None, full_name=None):
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
    elif (username != user.username) or (full_name != user.full_name):
        user.username = username
        user.full_name = full_name
        await session.commit()
    return user


async def parse_memorization_input(text):
    """تحليل إدخال المستخدم حول آخر صفحة محفوظة."""
    text = text.strip()
    result = {"type": None, "value": None, "page": None,
              "first_page": None, "last_page": None, "raw": text}
    if "كل القرآن" in text or "كامل القرآن" in text or "ختمت" in text:
        result.update({"type": "all", "value": "all", "page": quran_data.TOTAL_PAGES,
                       "first_page": 1, "last_page": quran_data.TOTAL_PAGES})
        return result
    m = re.search(r"جزء\s*(\d+)", text)
    if m:
        juz = int(m.group(1))
        if 1 <= juz <= 30:
            start, end = quran_data.juz_pages(juz)
            result.update({"type": "juz", "value": juz, "page": end,
                           "first_page": start, "last_page": end})
            return result
    m = re.search(r"سورة\s+(.+)", text)
    if m:
        surah = quran_data.get_surah_by_name(m.group(1).strip())
        if surah:
            if surah.number < 114:
                last_page = quran_data.get_surah_by_number(surah.number + 1).page_start - 1
            else:
                last_page = quran_data.TOTAL_PAGES
            result.update({"type": "surah", "value": surah.name_ar, "page": last_page,
                           "first_page": 1, "last_page": last_page})
            return result
    m = re.search(r"صفحة\s*(\d+)\s*[-–]\s*(\d+)", text)
    if m:
        start_p, end_p = int(m.group(1)), int(m.group(2))
        if 1 <= end_p <= quran_data.TOTAL_PAGES and 1 <= start_p <= end_p:
            result.update({"type": "page_range", "value": (start_p, end_p), "page": end_p,
                           "first_page": start_p, "last_page": end_p})
            return result
    m = re.search(r"صفحة\s*(\d+)$", text)
    if m:
        p = int(m.group(1))
        if 1 <= p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page", "value": p, "page": p,
                           "first_page": 1, "last_page": p})
            return result
    m = re.match(r"^\s*(\d+)\s*$", text)
    if m:
        p = int(m.group(1))
        if 1 <= p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page", "value": p, "page": p,
                           "first_page": 1, "last_page": p})
            return result
    return result


async def set_memorized_up_to(session, user, page, first_page=None):
    """يسجّل أن المستخدم حفظ نطاقاً من first_page إلى page (شامل)."""
    page = max(1, min(int(page), quran_data.TOTAL_PAGES))
    if first_page is None:
        first_page = 1
    first_page = max(1, min(int(first_page), page))

    await session.execute(Memorization.__table__.delete().where(Memorization.user_id == user.id))
    today = date.today()
    for p in range(first_page, page + 1):
        session.add(Memorization(user_id=user.id, page_number=p, date_memorized=today, review_count=5))
    user.current_page = page + 1 if page < quran_data.TOTAL_PAGES else quran_data.TOTAL_PAGES
    user.start_page = first_page
    user.last_memorized_page = page
    user.total_memorized = page - first_page + 1
    user.onboarding_done = True
    # تحديث نطاق التحضير الأسبوعي القادم
    user.weekly_prep_start = page + 1 if page < quran_data.TOTAL_PAGES else quran_data.TOTAL_PAGES
    user.weekly_prep_end = min(quran_data.TOTAL_PAGES, user.weekly_prep_start + max(1, user.weekly_memo_amount) - 1)
    await session.commit()


def get_today_memorize_page(user):
    return user.current_page


async def mark_memorized(session, user, page):
    result = await session.execute(
        select(Memorization).where(and_(Memorization.user_id == user.id, Memorization.page_number == page))
    )
    memo = result.scalar_one_or_none()
    if memo is None:
        memo = Memorization(user_id=user.id, page_number=page, date_memorized=date.today(), review_count=0)
        session.add(memo)
        session.add(WeeklyReview(user_id=user.id, page_number=page, date_memorized=date.today(), review_1_layla=date.today()))
    else:
        memo.date_memorized = date.today()
        memo.review_count = 0
    if page < user.start_page:
        user.start_page = page
    current_last = getattr(user, "last_memorized_page", 0) or 0
    if page > current_last:
        user.last_memorized_page = page
        # تحديث نطاق التحضير الأسبوعي القادم
        next_start = page + 1 if page < quran_data.TOTAL_PAGES else quran_data.TOTAL_PAGES
        user.weekly_prep_start = next_start
        user.weekly_prep_end = min(quran_data.TOTAL_PAGES, next_start + max(1, user.weekly_memo_amount) - 1)
    if user.current_page <= page:
        user.current_page = min(page + 1, quran_data.TOTAL_PAGES)
    user.total_memorized = await count_memorized(session, user.id)
    await session.commit()
    await session.refresh(memo)
    return memo


async def count_memorized(session, user_id):
    result = await session.execute(select(func.count(Memorization.id)).where(Memorization.user_id == user_id))
    return result.scalar() or 0


async def get_or_create_progress(session, user_id, progress_date=None):
    progress_date = progress_date or date.today()
    result = await session.execute(
        select(DailyProgress).where(and_(DailyProgress.user_id == user_id, DailyProgress.progress_date == progress_date))
    )
    progress = result.scalar_one_or_none()
    if progress is None:
        progress = DailyProgress(user_id=user_id, progress_date=progress_date)
        session.add(progress)
        await session.commit()
        await session.refresh(progress)
    return progress


# ====== الحصن الأول: دورات القراءة والاستماع ======

def get_reading_pages_today(user):
    """الحصن الأول — القراءة: دورة 30 يومًا، حزبان/يوم، تبدأ من تاريخ بداية الخطة.

    القاعدة:
      - تبدأ من الوجه 1 في يوم plan_start_date
      - 20 وجهًا/يوم × 30 يومًا = 600 وجه (تكاد تُغطّي المصحف كله)
      - مع لفّ تلقائي عند الوصول لنهاية المصحف (604)
      - كل دورة كاملة (30 يومًا) = ختمة قراءة كاملة
    """
    start_date = getattr(user, "plan_start_date", None) or user.created_at or date.today()
    today = date.today()
    days_since = max(0, (today - start_date).days)
    # إزاحة بمقدار (days_since * 20) عن الوجه 1، مع لفّ
    offset = (days_since * PAGES_PER_READING_DAY) % quran_data.TOTAL_PAGES
    r_start = offset + 1
    r_end = r_start + PAGES_PER_READING_DAY - 1
    if r_end > quran_data.TOTAL_PAGES:
        # لفّ: النهاية تتجاوز المصحف، تعود من البداية
        r_end = r_end - quran_data.TOTAL_PAGES
    return r_start, r_end


def get_listening_pages_today(user):
    """الحصن الأول — الاستماع: دورة 60 يومًا، حزب/يوم، تبدأ من تاريخ بداية الخطة.

    القاعدة:
      - تبدأ من الوجه 1 في يوم plan_start_date
      - 10 أوجه/يوم × 60 يومًا = 600 وجه (تغطّي المصحف كله)
      - مع لفّ تلقائي عند نهاية المصحف
      - كل دورة كاملة (60 يومًا) = ختمة استماع كاملة
    """
    start_date = getattr(user, "plan_start_date", None) or user.created_at or date.today()
    today = date.today()
    days_since = max(0, (today - start_date).days)
    # إزاحة بمقدار (days_since * 10) عن الوجه 1، مع لفّ
    offset = (days_since * PAGES_PER_LISTENING_DAY) % quran_data.TOTAL_PAGES
    l_start = offset + 1
    l_end = l_start + PAGES_PER_LISTENING_DAY - 1
    if l_end > quran_data.TOTAL_PAGES:
        l_end = l_end - quran_data.TOTAL_PAGES
    return l_start, l_end


def get_reading_cycle_day(user):
    """يعيد رقم اليوم في دورة القراءة (1..30) وعدد الختمات المنجزة."""
    start_date = getattr(user, "plan_start_date", None) or user.created_at or date.today()
    days_since = max(0, (date.today() - start_date).days)
    completed_cycles = days_since // READING_CYCLE_DAYS
    day_in_cycle = (days_since % READING_CYCLE_DAYS) + 1
    return day_in_cycle, completed_cycles


def get_listening_cycle_day(user):
    """يعيد رقم اليوم في دورة الاستماع (1..60) وعدد الختمات المنجزة."""
    start_date = getattr(user, "plan_start_date", None) or user.created_at or date.today()
    days_since = max(0, (date.today() - start_date).days)
    completed_cycles = days_since // LISTENING_CYCLE_DAYS
    day_in_cycle = (days_since % LISTENING_CYCLE_DAYS) + 1
    return day_in_cycle, completed_cycles


# ====== الحصن الثاني: التحضير ======

def get_weekly_prep_range(user):
    """نطاق التحضير الأسبوعي = آخر محفوظ + 1 .. + weekly_memo_amount.

    يُخزَّن في user.weekly_prep_start / weekly_prep_end، ويُحدَّث تلقائيًا عند كل حفظ جديد.
    """
    start = max(1, getattr(user, "weekly_prep_start", 1) or 1)
    end = max(start, getattr(user, "weekly_prep_end", start) or start)
    # الحدّ الأقصى = نهاية المصحف
    end = min(end, quran_data.TOTAL_PAGES)
    return start, end


def get_nightly_prep_page(user):
    """التحضير الليلي = وجه الغد المتوقع (next_memorize_page)."""
    last = getattr(user, "last_memorized_page", 0) or 0
    return min(last + 1, quran_data.TOTAL_PAGES)


def get_pre_session_prep_page(user):
    """التحضير القبلي = وجه الحفظ القادم (نفس الليلي عادةً)."""
    return get_nightly_prep_page(user)


# ====== الحصن الرابع: مراجعة القريب ======

def get_near_review_range(user):
    """آخر 20 وجهًا محفوظًا فعليًا."""
    last = getattr(user, "last_memorized_page", 0) or 0
    if last < 1:
        return None, None
    start = max(1, last - NEAR_REVIEW_PAGES + 1)
    end = last
    return start, end


# ====== الحصن الخامس: مراجعة البعيد (دورات 40 وجهًا) ======

def get_far_review_range(user):
    """دورة المراجعة البعيدة الحالية (40 وجهًا).

    القاعدة:
      - عدد الدورات الكلية = ceil((last_memorized - 20) / 40)
        (نحجز 20 وجهًا للقريب، والباقي يُقسَّم على دورات 40 وجه)
      - الدورة 1 = الأحدث (آخر 40 وجهًا قبل القريب)
      - الدورة 2 = التي قبلها
      - عند إتمام دورة، تنتقل للأقدم (مع لفّ دائري)
    """
    last = getattr(user, "last_memorized_page", 0) or 0
    if last < 1:
        return None, None, 1, 0

    # عدد أوجه المراجعة البعيدة = last - NEAR_REVIEW_PAGES (نحجز 20 للقريب)
    far_pages_available = max(0, last - NEAR_REVIEW_PAGES)
    if far_pages_available < 1:
        return None, None, 1, 0

    total_cycles = max(1, (far_pages_available + FAR_REVIEW_PAGES - 1) // FAR_REVIEW_PAGES)
    cycle = max(1, min(getattr(user, "far_review_cycle", 1) or 1, total_cycles))

    # نطاق القريب
    near_start = max(1, last - NEAR_REVIEW_PAGES + 1)
    # نهاية البعيد = بداية القريب - 1
    far_end = near_start - 1
    if far_end < 1:
        return None, None, cycle, total_cycles
    # الدورة N تعني: نأخذ 40 وجهًا تبدأ من far_end - (N-1)*40
    far_start = max(1, far_end - FAR_REVIEW_PAGES + 1 - (cycle - 1) * FAR_REVIEW_PAGES)
    actual_end = max(far_start, far_end - (cycle - 1) * FAR_REVIEW_PAGES)
    if actual_end < 1:
        return None, None, cycle, total_cycles
    actual_start = max(1, actual_end - FAR_REVIEW_PAGES + 1)
    return actual_start, actual_end, cycle, total_cycles


def advance_far_review_cycle(user):
    """الانتقال للدورة التالية (مع لفّ دائري عند الوصول للأقدم)."""
    last = getattr(user, "last_memorized_page", 0) or 0
    if last < 1:
        return 1, 1
    far_pages_available = max(0, last - NEAR_REVIEW_PAGES)
    if far_pages_available < 1:
        return 1, 1
    total_cycles = max(1, (far_pages_available + FAR_REVIEW_PAGES - 1) // FAR_REVIEW_PAGES)
    current = getattr(user, "far_review_cycle", 1) or 1
    new_cycle = current + 1
    if new_cycle > total_cycles:
        new_cycle = 1  # لفّ دائري
    user.far_review_cycle = new_cycle
    return new_cycle, total_cycles


# ====== الحساب الموحَّد للحصون ======

def compute_fortresses(user):
    """الدالة الموحدة الوحيدة لحساب الحصون الخمسة كاملة."""
    empty = {
        "first_memorized_page": None,
        "last_memorized_page": None,
        "near_start": None, "near_end": None,
        "far_start": None, "far_end": None,
        "far_cycle": 1, "far_total_cycles": 0,
        "next_memorize_page": 1,
        "has_memorized": False,
        "has_far_review": False,
    }
    if user is None:
        return empty

    start_page = max(1, getattr(user, "start_page", 1) or 1)
    last_memorized = getattr(user, "last_memorized_page", 0) or 0
    has_memorized = last_memorized >= 1

    if not has_memorized:
        empty["next_memorize_page"] = max(1, start_page)
        empty["first_memorized_page"] = start_page
        return empty

    last_page = max(1, min(last_memorized, quran_data.TOTAL_PAGES))
    near_start = max(1, last_page - NEAR_REVIEW_PAGES + 1)
    near_end = last_page
    far_start, far_end, far_cycle, far_total = get_far_review_range(user)
    has_far = far_start is not None and far_end is not None and far_end >= 1
    next_memorize_page = last_page + 1 if last_page < quran_data.TOTAL_PAGES else quran_data.TOTAL_PAGES

    return {
        "first_memorized_page": start_page,
        "last_memorized_page": last_page,
        "near_start": near_start,
        "near_end": near_end,
        "far_start": far_start if has_far else None,
        "far_end": far_end if has_far else None,
        "far_cycle": far_cycle,
        "far_total_cycles": far_total,
        "next_memorize_page": next_memorize_page,
        "has_memorized": True,
        "has_far_review": has_far,
    }


# ====== تتبّع الالتزام (streak) ======

async def update_streak_on_activity(session, user):
    """يُحدّث أيام الالتزام المتتالية عند أي نشاط (مهمة واحدة على الأقل مكتملة)."""
    today = date.today()
    last_active = getattr(user, "last_active_date", None)

    if last_active is None:
        # أول نشاط على الإطلاق
        user.streak_days = 1
        user.last_active_date = today
    elif last_active == today:
        # نشاط متكرر في نفس اليوم — لا تغيير
        pass
    elif last_active == today - timedelta(days=1):
        # استمرارية — تزداد
        user.streak_days = (user.streak_days or 0) + 1
        user.last_active_date = today
    else:
        # انقطاع — إعادة من 1
        user.streak_days = 1
        user.last_active_date = today
    await session.commit()
    return user.streak_days


# ====== تسجيل الإنجاز اليومي ======

async def log_daily_achievement(session, user_id, log_date=None):
    """يُسجّل (أو يُحدّث) سجل إنجاز يوم كامل بناءً على DailyProgress."""
    log_date = log_date or date.today()
    result = await session.execute(
        select(DailyProgress).where(and_(DailyProgress.user_id == user_id, DailyProgress.progress_date == log_date))
    )
    progress = result.scalar_one_or_none()
    if progress is None:
        return None

    # حساب الحالة الإجمالية
    tasks = [
        progress.reading_done, progress.listening_done,
        progress.weekly_prep_done, progress.nightly_prep_done,
        progress.pre_session_prep_done, progress.memorize_done,
        progress.near_review_done, progress.far_review_done,
    ]
    completed_count = sum(1 for t in tasks if t)
    if completed_count == 8:
        overall = "completed"
    elif completed_count >= 1:
        overall = "partial"
    else:
        overall = "missed"

    # هل توجد مهام مؤجَّلة؟ (task_status = 'postponed')
    if getattr(progress, "task_status", "pending") == "postponed" and completed_count < 8:
        overall = "partial"

    # إدراج أو تحديث
    result = await session.execute(
        select(AchievementLog).where(and_(AchievementLog.user_id == user_id, AchievementLog.log_date == log_date))
    )
    log = result.scalar_one_or_none()
    if log is None:
        log = AchievementLog(
            user_id=user_id, log_date=log_date, overall_status=overall,
            reading_done=progress.reading_done, listening_done=progress.listening_done,
            weekly_prep_done=progress.weekly_prep_done, nightly_prep_done=progress.nightly_prep_done,
            pre_session_prep_done=progress.pre_session_prep_done, memorize_done=progress.memorize_done,
            near_review_done=progress.near_review_done, far_review_done=progress.far_review_done,
        )
        session.add(log)
    else:
        log.overall_status = overall
        log.reading_done = progress.reading_done
        log.listening_done = progress.listening_done
        log.weekly_prep_done = progress.weekly_prep_done
        log.nightly_prep_done = progress.nightly_prep_done
        log.pre_session_prep_done = progress.pre_session_prep_done
        log.memorize_done = progress.memorize_done
        log.near_review_done = progress.near_review_done
        log.far_review_done = progress.far_review_done
    await session.commit()
    return log


async def mark_progress_done(session, user_id, task_type):
    """يُسجّل إنجاز مهمة في DailyProgress ويُحدّث streak."""
    progress = await get_or_create_progress(session, user_id)
    if task_type == "reading":
        progress.reading_done = True
    elif task_type == "listening":
        progress.listening_done = True
    elif task_type == "memorize":
        progress.memorize_done = True
    elif task_type == "weekly_prep":
        progress.weekly_prep_done = True
    elif task_type == "nightly_prep":
        progress.nightly_prep_done = True
    elif task_type == "pre_session_prep":
        progress.pre_session_prep_done = True
        progress.pre_session_started_at = datetime.now()
    elif task_type == "pre_session_end":
        # حساب المدة
        if progress.pre_session_started_at:
            duration = (datetime.now() - progress.pre_session_started_at).total_seconds() / 60.0
            progress.pre_session_duration_min = int(duration)
        progress.pre_session_prep_done = True
    elif task_type == "near_review":
        progress.near_review_done = True
    elif task_type == "far_review":
        progress.far_review_done = True
    elif task_type == "daily_review":
        progress.daily_review_done = True
    # تحديث task_status
    tasks = [
        progress.reading_done, progress.listening_done,
        progress.weekly_prep_done, progress.nightly_prep_done,
        progress.pre_session_prep_done, progress.memorize_done,
        progress.near_review_done, progress.far_review_done,
    ]
    completed_count = sum(1 for t in tasks if t)
    if completed_count == 8:
        progress.task_status = "completed"
    elif completed_count >= 1:
        progress.task_status = "partial"
    await session.commit()

    # تحديث streak + تسجيل الإنجاز
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        await update_streak_on_activity(session, user)
        await log_daily_achievement(session, user_id)


async def postpone_task(session, user_id, task_type):
    """يؤجّل مهمة لليوم التالي — يُسجّلها كـ 'postponed' في task_status."""
    progress = await get_or_create_progress(session, user_id, progress_date=date.today() + timedelta(days=1))
    if task_type == "memorize":
        progress.memorize_done = False
    # لا نضع True لأن المهمة لم تُنجز — فقط نعلّمها كـ postponed
    progress.task_status = "postponed"
    await session.commit()


async def get_memorization_history(session, user_id):
    result = await session.execute(
        select(Memorization).where(Memorization.user_id == user_id).order_by(Memorization.date_memorized.asc())
    )
    return list(result.scalars().all())


# ============== 5. المعالجات (الأوامر) ==============
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)

# ====== حالة الـ onboarding متعدد الخطوات ======
# القيم الممكنة:
#   "waiting_for_memorization"    — بانتظار إدخال آخر سورة/صفحة محفوظة
#   "waiting_for_daily_amount"    — بانتظار مقدار الحفظ اليومي (1 أو 2)
#   "waiting_for_weekly_amount"   — بانتظار مقدار الحفظ الأسبوعي
#   "waiting_for_plan_start_date" — بانتظار تاريخ بداية الخطة (أو اضغط "اليوم")
#   "waiting_for_reminder_times"   — بانتظار تأكيد أوقات التذكيرات
ONBOARDING_STATE = {}
# بيانات مؤقتة لكل مستخدمة أثناء الـ onboarding
ONBOARDING_DATA = {}


# ====== دوال مساعدة آمنة ======

def esc(text) -> str:
    """هروب HTML آمن. يقبول str/int/float/date/None."""
    if text is None:
        return ""
    if isinstance(text, date):
        text = text.strftime("%Y-%m-%d")
    return html.escape(str(text), quote=False)


def bold(text) -> str:
    return f"<b>{esc(text)}</b>"


def code(text) -> str:
    return f"<code>{esc(text)}</code>"


def link(label, url) -> str:
    return f'<a href="{esc(url)}">{esc(label)}</a>'


def progress_bar(current, total, length=15):
    if total == 0: return "░" * length
    filled = int((current / total) * length)
    return "█" * filled + "░" * (length - filled)


def fmt_pages(start, end):
    """تنسيق نطاق أوجه مع معالجة اللفّ عند نهاية المصحف."""
    if start is None or end is None:
        return "—"
    if end < start:
        return f"{start}→{quran_data.TOTAL_PAGES} + 1→{end}"
    return f"{start}–{end}"


# ====== لوحات المفاتيح ======

def main_keyboard():
    """اللوحة الثابتة في الأسفل — 4 أزرار مرتّبة في صفّين."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🕌 الحصون الخمسة"), KeyboardButton("📊 تقدمي")],
            [KeyboardButton("📅 سجل الإنجاز"), KeyboardButton("⚙️ الإعدادات")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="اضغطي أحد الأزرار في الأسفل ✨",
    )


def fortresses_inline_keyboard():
    """أزرار الحصون الخمسة Inline — تظهر عند الضغط على '🕌 الحصون الخمسة'."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🕌 برنامج اليوم", callback_data="today_program")],
        [
            InlineKeyboardButton("🏰 1. التهيئة", callback_data="fortress_1"),
            InlineKeyboardButton("📚 2. التحضير", callback_data="fortress_2"),
        ],
        [
            InlineKeyboardButton("🆕 3. الحفظ", callback_data="fortress_3"),
            InlineKeyboardButton("🔄 4. القريب", callback_data="fortress_4"),
        ],
        [InlineKeyboardButton("🛡️ 5. البعيد", callback_data="fortress_5")],
    ])


def task_buttons_inline(progress, f):
    """أزرار تسجيل الإنجاز لكل من المهام الـ 8."""
    def btn(emoji, label, task, done):
        icon = "✅" if done else "⬜"
        return InlineKeyboardButton(f"{emoji} {icon}", callback_data=f"task_{task}" if not done else f"task_done_{task}")

    return InlineKeyboardMarkup([
        [
            btn("📖", "قراءة", "reading", progress.reading_done),
            btn("🎧", "استماع", "listening", progress.listening_done),
            btn("📚", "تحضير أسبوعي", "weekly_prep", progress.weekly_prep_done),
            btn("🌙", "تحضير ليلي", "nightly_prep", progress.nightly_prep_done),
        ],
        [
            btn("⏱️", "تحضير قبلي", "pre_session_prep", progress.pre_session_prep_done),
            btn("🆕", "حفظ", "memorize", progress.memorize_done),
            btn("🔄", "مراجعة قريب", "near_review", progress.near_review_done),
            btn("🔁", "مراجعة بعيد", "far_review", progress.far_review_done),
        ],
        [InlineKeyboardButton("🔙 العودة للقائمة", callback_data="fortresses_menu")],
    ])


def onboarding_question_keyboard():
    """أزرار سريعة لاختيار آخر سورة محفوظة."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔰 لم أحفظ شيئاً بعد", callback_data="ob_0")],
        [InlineKeyboardButton("📖 سورة البقرة", callback_data="ob_surah_2"),
         InlineKeyboardButton("📖 سورة آل عمران", callback_data="ob_surah_3")],
        [InlineKeyboardButton("📖 سورة النساء", callback_data="ob_surah_4"),
         InlineKeyboardButton("📖 سورة المائدة", callback_data="ob_surah_5")],
        [InlineKeyboardButton("📖 سورة الكهف", callback_data="ob_surah_18"),
         InlineKeyboardButton("📖 سورة يس", callback_data="ob_surah_36")],
        [InlineKeyboardButton("📖 سورة تبارك", callback_data="ob_surah_67"),
         InlineKeyboardButton("📖 سورة عمَّ", callback_data="ob_surah_78")],
        [InlineKeyboardButton("✅ ختمت القرآن كاملاً", callback_data="ob_all")],
        [InlineKeyboardButton("✍️ إدخال يدوي (اكتبي النص)", callback_data="ob_manual")],
    ])


def daily_amount_keyboard():
    """اختيار مقدار الحفظ اليومي (1 أو 2 وجه)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 وجه/يوم", callback_data="daily_1"),
            InlineKeyboardButton("2 وجه/يوم (موصى به)", callback_data="daily_2"),
        ],
    ])


def weekly_amount_keyboard():
    """اختيار مقدار الحفظ الأسبوعي."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("5 أوجه/أسبوع", callback_data="weekly_5"),
            InlineKeyboardButton("7 أوجه/أسبوع (موصى به)", callback_data="weekly_7"),
        ],
        [
            InlineKeyboardButton("10 أوجه/أسبوع", callback_data="weekly_10"),
            InlineKeyboardButton("14 وجه/أسبوع", callback_data="weekly_14"),
        ],
    ])


def plan_start_date_keyboard():
    """اختيار تاريخ بداية الخطة."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 اليوم (موصى به)", callback_data="plan_today")],
        [InlineKeyboardButton("✍️ إدخال تاريخ يدوي (YYYY-MM-DD)", callback_data="plan_manual")],
    ])


def reminders_confirm_keyboard():
    """تأكيد أوقات التذكيرات الافتراضية أو تخصيصها."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ قبول الأوقات الافتراضية", callback_data="reminders_default")],
        [InlineKeyboardButton("⚙️ تخصيص الأوقات لاحقًا", callback_data="reminders_customize")],
    ])


# خريطة النصوص المختصرة من لوحة المفاتيح الثابتة
KEYBOARD_TEXT_MAP = {
    "🕌 الحصون الخمسة": "fortresses",
    "🏰 الحصون": "fortresses",
    "🏰 الحصون الخمسة": "fortresses",
    "📊 تقدمي": "progress",
    "📅 سجل الإنجاز": "achievements",
    "📅 سجل الانجاز": "achievements",
    "⚙️ الإعدادات": "settings",
    "⚙️ الإعدادات والمساعدة": "settings",
    "⚙️ مساعدة": "help",
}


# ====== الـ Onboarding متعدد الخطوات ======

async def ask_onboarding_question(update, context, welcome=False):
    """الخطوة 1 من الـ onboarding: ما آخر سورة/صفحة حفظت؟"""
    user_info = update.effective_user
    ONBOARDING_STATE[user_info.id] = "waiting_for_memorization"
    ONBOARDING_DATA[user_info.id] = {}
    if welcome:
        intro = (
            "🤲 <b>بسم الله الرحمن الرحيم</b>\n\n"
            f"أهلاً {bold(user_info.first_name or 'أختي الكريمة')}! 🌟\n\n"
            "📖 <b>بوت الحصون الخمسة لحفظ القرآن (الإصدار الكامل v3)</b>\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
        )
    else:
        intro = "🤔 <b>نحتاج معرفة نقطة انطلاقك</b>\n\n━━━━━━━━━━━━━━━━\n\n"
    text = intro + (
        "❓ <b>الخطوة 1/5: ما آخر سورة (أو وجه) حفظتِها من القرآن؟</b>\n\n"
        "اقتراحات سريعة للإجابة 👇:\n\n"
        "• اضغطي أحد الأزرار بالأسفل، أو اكتبي إجابتك بالنص:\n"
        "  — <code>صفحة 127</code> — آخر وجه حفظته هو 127\n"
        "  — <code>سورة المائدة</code> — حفظت حتى نهاية سورة المائدة\n"
        "  — <code>جزء 7</code> — حفظت 7 أجزاء كاملة\n"
        "  — <code>ختمت القرآن</code> — حفظت القرآن كاملاً\n"
        "  — <code>0</code> — لم أحفظ شيئاً بعد، ابدأ من الوجه 1\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🌙 <i>أعانك الله وثبّت حفظك</i>"
    )
    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=onboarding_question_keyboard(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=onboarding_question_keyboard(),
            disable_web_page_preview=True,
        )


async def ask_daily_amount(update, context):
    """الخطوة 2: مقدار الحفظ اليومي."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "waiting_for_daily_amount"
    text = (
        "✅ <b>تمّ تسجيل محفوظك السابق!</b> 🎉\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "❓ <b>الخطوة 2/5: كم تريدين أن تحفظي يومياً؟</b>\n\n"
        "💡 <i>التوصية: وجهان في اليوم لمن تملك الوقت. لكن حتى وجه واحد يومياً يكفي لإتمام القرآن خلال سنتين.</i>\n"
        "━━━━━━━━━━━━━━━━"
    )
    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=daily_amount_keyboard(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=daily_amount_keyboard(),
                disable_web_page_preview=True,
            )
        except Exception:
            await update.effective_chat.send_message(
                text, parse_mode=ParseMode.HTML,
                reply_markup=daily_amount_keyboard(),
                disable_web_page_preview=True,
            )


async def ask_weekly_amount(update, context):
    """الخطوة 3: مقدار الحفظ الأسبوعي."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "waiting_for_weekly_amount"
    text = (
        "✅ <b>تمّ ضبط الحفظ اليومي!</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "❓ <b>الخطوة 3/5: كم تريدين أن تحفظي أسبوعياً؟</b>\n\n"
        "💡 <i>هذا يُحدّد نطاق التحضير الأسبوعي (الحصن الثاني). كل ما زاد المقدار، اتّسع نطاق التحضير للأسبوع القادم.</i>\n"
        "━━━━━━━━━━━━━━━━"
    )
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=weekly_amount_keyboard(),
                disable_web_page_preview=True,
            )
        except Exception:
            await update.effective_chat.send_message(
                text, parse_mode=ParseMode.HTML,
                reply_markup=weekly_amount_keyboard(),
                disable_web_page_preview=True,
            )
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=weekly_amount_keyboard(),
            disable_web_page_preview=True,
        )


async def ask_plan_start_date(update, context):
    """الخطوة 4: تاريخ بداية الخطة."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "waiting_for_plan_start_date"
    today_str = date.today().strftime("%Y-%m-%d")
    text = (
        "✅ <b>تمّ ضبط مقدار الحفظ الأسبوعي!</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"❓ <b>الخطوة 4/5: متى تريدين أن تبدأ خطمتك؟</b>\n\n"
        f"📅 اليوم: <code>{esc(today_str)}</code>\n\n"
        "💡 <i>تاريخ البداية يُحدّد دورة القراءة (30 يومًا) ودورة الاستماع (60 يومًا). عادةً يُضبط على تاريخ اليوم.</i>\n"
        "━━━━━━━━━━━━━━━━"
    )
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=plan_start_date_keyboard(),
                disable_web_page_preview=True,
            )
        except Exception:
            await update.effective_chat.send_message(
                text, parse_mode=ParseMode.HTML,
                reply_markup=plan_start_date_keyboard(),
                disable_web_page_preview=True,
            )
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=plan_start_date_keyboard(),
            disable_web_page_preview=True,
        )


async def ask_reminder_times(update, context):
    """الخطوة 5: تأكيد أوقات التذكيرات الـ 8."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "waiting_for_reminder_times"
    text = (
        "✅ <b>تمّ ضبط تاريخ البداية!</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "❓ <b>الخطوة 5/5: أوقات التذكيرات اليومية الـ 8</b>\n\n"
        "🕒 <b>الأوقات الافتراضية:</b>\n"
        "• <b>06:00</b> — تذكير الحفظ الجديد\n"
        "• <b>08:00</b> — تذكير القراءة الصباحية\n"
        "• <b>09:00</b> — تذكير التحضير الأسبوعي\n"
        "• <b>10:00</b> — تذكير التحضير القبلي\n"
        "• <b>13:00</b> — تذكير الاستماع\n"
        "• <b>16:00</b> — تذكير مراجعة القريب\n"
        "• <b>20:00</b> — تذكير مراجعة البعيد\n"
        "• <b>21:00</b> — تذكير التحضير الليلي\n\n"
        "💡 <i>يمكنك تخصيصها لاحقًا من ⚙️ الإعدادات</i>\n"
        "━━━━━━━━━━━━━━━━"
    )
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=reminders_confirm_keyboard(),
                disable_web_page_preview=True,
            )
        except Exception:
            await update.effective_chat.send_message(
                text, parse_mode=ParseMode.HTML,
                reply_markup=reminders_confirm_keyboard(),
                disable_web_page_preview=True,
            )
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=reminders_confirm_keyboard(),
            disable_web_page_preview=True,
        )


async def finalize_onboarding(update, context):
    """إنهاء الـ onboarding وعرض الحصون."""
    user_id = update.effective_user.id
    ONBOARDING_STATE.pop(user_id, None)
    ONBOARDING_DATA.pop(user_id, None)
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=user_id)
        if user.plan_start_date is None:
            user.plan_start_date = user.created_at or date.today()
            await session.commit()
        f = compute_fortresses(user)

    text = (
        "🎉 <b>ما شاء الله! اكتملت تهيئتك</b> 🌟\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📊 <b>ملخّص خطتك:</b>\n\n"
        f"📖 آخر وجه محفوظ: <b>{f['last_memorized_page'] or 0}</b>\n"
        f"🆕 الوجه القادم: <b>{f['next_memorize_page']}</b>\n"
        f"📅 تاريخ بداية الخطة: <code>{esc(user.plan_start_date)}</code>\n"
        f"📚 مقدار الحفظ اليومي: <b>{user.daily_memo_amount} وجه</b>\n"
        f"📚 مقدار الحفظ الأسبوعي: <b>{user.weekly_memo_amount} وجه</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🕌 اضغطي <b>🕌 الحصون الخمسة</b> في الأسفل لعرض برنامج اليوم الكامل 📋"
    )
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=fortresses_inline_keyboard(),
                disable_web_page_preview=True,
            )
        except Exception:
            await update.effective_chat.send_message(
                text, parse_mode=ParseMode.HTML,
                reply_markup=fortresses_inline_keyboard(),
                disable_web_page_preview=True,
            )
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=fortresses_inline_keyboard(),
            disable_web_page_preview=True,
        )


# ====== الأمر /start ======

async def start_command(update, context):
    user_info = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, user_info.id, user_info.username, user_info.full_name)
        needs_onboarding = not user.onboarding_done
        if not needs_onboarding:
            await update.message.reply_text(
                f"👋 <b>أهلاً بعودتك، {esc(user_info.first_name or 'أختي')}</b>! 🌟\n"
                "إليكِ <b>برنامج اليوم</b> 👇",
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
                disable_web_page_preview=True,
            )
            await _show_today_program(update, context)
            return
    await ask_onboarding_question(update, context, welcome=True)


# ====== معالج النص الحر ======

async def handle_free_text(update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # لو النص يطابق أحد أزرار لوحة المفاتيح الثابتة
    if text in KEYBOARD_TEXT_MAP:
        command = KEYBOARD_TEXT_MAP[text]
        if command == "fortresses":
            await fortresses_command(update, context)
        elif command == "progress":
            await progress_command(update, context)
        elif command == "achievements":
            await achievements_command(update, context)
        elif command == "settings":
            await settings_command(update, context)
        elif command == "help":
            await help_command(update, context)
        return

    # لو المستخدمة في وضع التهيئة
    state = ONBOARDING_STATE.get(user_id)
    if state == "waiting_for_memorization":
        await _process_onboarding_memorization(update, context, text)
        return
    if state == "waiting_for_plan_start_date":
        await _process_plan_start_date_text(update, context, text)
        return

    # نص حر غير مرتبط بأمر
    await update.message.reply_text(
        "💡 <b>اضغطي أحد أزرار القائمة في الأسفل</b>\n\n"
        "أو استخدمي الأوامر:\n"
        "• <code>/today</code> — برنامج اليوم\n"
        "• <code>/fortresses</code> — الحصون الخمسة\n"
        "• <code>/update سورة المائدة</code> — تحديث آخر وجه محفوظ",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


async def _process_onboarding_memorization(update, context, text):
    """معالجة إجابة الخطوة 1 (آخر محفوظ) ثم الانتقال للخطوة 2."""
    user_id = update.effective_user.id
    parsed = await parse_memorization_input(text)

    if parsed["page"] is None and "0" not in text and "لا شيء" not in text.lower() and "ما حفظت" not in text.lower():
        if update.message:
            await update.message.reply_text(
                "❌ <b>لم أفهم الإجابة</b> 😅\n\n"
                "جرّبي إحدى الصيغ التالية:\n"
                "• <code>صفحة 50</code>\n"
                "• <code>سورة المائدة</code>\n"
                "• <code>جزء 3</code>\n"
                "• <code>ختمت القرآن</code>\n"
                "• <code>0</code> (لم أحفظ شيئاً)",
                parse_mode=ParseMode.HTML,
                reply_markup=onboarding_question_keyboard(),
                disable_web_page_preview=True,
            )
        return

    page = parsed["page"] or 0
    first_p = parsed.get("first_page") or 1

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=user_id)
        if page == 0:
            user.current_page = 1
            user.start_page = 1
            user.last_memorized_page = 0
            user.total_memorized = 0
        else:
            await set_memorized_up_to(session, user, page, first_page=first_p)
        await session.refresh(user)
        ONBOARDING_DATA[user_id] = {"last_page": page}

    # الانتقال للخطوة 2
    await ask_daily_amount(update, context)


async def _process_plan_start_date_text(update, context, text):
    """معالجة إدخال تاريخ بداية الخطة يدويًا."""
    user_id = update.effective_user.id
    text = text.strip()
    try:
        # محاولة parse بصيغة YYYY-MM-DD
        parsed_date = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text(
            "❌ <b>صيغة التاريخ غير صحيحة</b>\n\n"
            "اكتبي التاريخ بصيغة <code>YYYY-MM-DD</code>\n"
            "مثال: <code>2026-08-09</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=plan_start_date_keyboard(),
            disable_web_page_preview=True,
        )
        return
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=user_id)
        user.plan_start_date = parsed_date
        await session.commit()
    await ask_reminder_times(update, context)


# ====== برنامج اليوم — العرض المدمج ======

async def _show_today_program(update, context):
    """يعرض برنامج اليوم المدمج مع أزرار الإنجاز الـ 8."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            await ask_onboarding_question(update, context, welcome=False)
            return

        progress = await get_or_create_progress(session, user.id)
        r_start, r_end = get_reading_pages_today(user)
        l_start, l_end = get_listening_pages_today(user)
        f = compute_fortresses(user)

        # حساب أرقام الدورات
        read_day, read_khatmah = get_reading_cycle_day(user)
        listen_day, listen_khatmah = get_listening_cycle_day(user)

        weekly_prep_start, weekly_prep_end = get_weekly_prep_range(user)
        nightly_page = get_nightly_prep_page(user)
        pre_session_page = get_pre_session_prep_page(user)

    today_str = date.today().strftime("%Y-%m-%d")
    days_since = max(0, (date.today() - (user.plan_start_date or user.created_at)).days) + 1

    r_pages_str = fmt_pages(r_start, r_end)
    l_pages_str = fmt_pages(l_start, l_end)

    # المهام المكتملة
    completed_count = sum([
        progress.reading_done, progress.listening_done,
        progress.weekly_prep_done, progress.nightly_prep_done,
        progress.pre_session_prep_done, progress.memorize_done,
        progress.near_review_done, progress.far_review_done,
    ])

    # مدة التحضير القبلي
    pre_session_duration = progress.pre_session_duration_min or 0

    text = (
        f"🕌 <b>برنامجك اليومي — {esc(today_str)}</b>\n"
        f"📅 اليوم رقم <b>{days_since}</b> منذ بدأتِ الخطة\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "🏰 <b>الحصن الأول — التهيئة</b>\n"
        f"📖 القراءة: الأوجه <b>{r_pages_str}</b> "
        f"(يوم {read_day}/30 — ختمة رقم {read_khatmah + 1})\n"
        f"🎧 الاستماع: الأوجه <b>{l_pages_str}</b> "
        f"(يوم {listen_day}/60 — ختمة رقم {listen_khatmah + 1})\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "🏰 <b>الحصن الثاني — التحضير</b>\n"
    )

    if f["has_memorized"]:
        text += (
            f"📚 التحضير الأسبوعي: الأوجه <b>{weekly_prep_start} → {weekly_prep_end}</b>\n"
            f"🌙 التحضير الليلي: الوجه <b>{nightly_page}</b>\n"
            f"⏱️ التحضير القبلي: الوجه <b>{pre_session_page}</b>"
        )
        if pre_session_duration > 0:
            text += f" (<b>{pre_session_duration} دقيقة</b>)"
        text += "\n\n"
        text += "━━━━━━━━━━━━━━━━\n\n"
        text += (
            "🏰 <b>الحصن الثالث — الحفظ الجديد</b>\n"
            f"🆕 الوجه <b>{f['next_memorize_page']}</b>\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "🏰 <b>الحصن الرابع — مراجعة القريب</b>\n"
            f"🔄 الأوجه <b>{f['near_start']} → {f['near_end']}</b>\n\n"
        )
        if f.get("has_far_review"):
            text += (
                "━━━━━━━━━━━━━━━━\n\n"
                "🏰 <b>الحصن الخامس — مراجعة البعيد</b>\n"
                f"🔁 الأوجه <b>{f['far_start']} → {f['far_end']}</b> "
                f"(الدورة {f['far_cycle']}/{f['far_total_cycles']})\n\n"
            )
        else:
            text += (
                "━━━━━━━━━━━━━━━━\n\n"
                "🏰 <b>الحصن الخامس — مراجعة البعيد</b>\n"
                "⏸️ <i>لا ينطبق الآن — سيُفعَّل بعد حفظ 20+ وجه</i>\n\n"
            )
    else:
        np1 = f["next_memorize_page"]
        text += (
            "🌱 <i>أنتِ في مرحلة البداية — لم تحفظي شيئاً بعد</i>\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "🏰 <b>الحصن الثالث — الحفظ الجديد</b>\n"
            f"🆕 ابدئي من الوجه <b>{np1}</b>\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "🏰 <b>الحصن الرابع — مراجعة القريب:</b> لا ينطبق الآن\n"
            "🏰 <b>الحصن الخامس — مراجعة البعيد:</b> لا ينطبق الآن\n\n"
        )

    text += (
        "━━━━━━━━━━━━━━━━\n"
        f"📊 <b>الإنجاز: {completed_count}/8 مهام</b>\n"
        f"🔥 <b>أيام الالتزام المتتالية: {user.streak_days or 0} يوم</b>\n\n"
        "👇 اضغطي على أي مهمة لتسجيل إنجازها:"
    )

    reply_markup = task_buttons_inline(progress, f)

    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=reply_markup, disable_web_page_preview=True,
        )
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=reply_markup, disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"تعذّر تعديل رسالة برنامج اليوم: {e}")


async def today_command(update, context):
    await _show_today_program(update, context)


# ====== الحصون الخمسة (الأزرار الفرعية) ======

async def fortresses_command(update, context):
    """يعرض القائمة الفرعية للحصون الخمسة."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            await ask_onboarding_question(update, context, welcome=False)
            return

    text = (
        "🏰 <b>الحصون الخمسة</b>\n\n"
        "اختري أحد الحصون لعرض التفاصيل:\n\n"
        "• <b>1. التهيئة</b> — القراءة والاستماع اليومي\n"
        "• <b>2. التحضير</b> — أسبوعي + ليلي + قبلي\n"
        "• <b>3. الحفظ الجديد</b> — الوجه القادم\n"
        "• <b>4. مراجعة القريب</b> — آخر 20 وجه\n"
        "• <b>5. مراجعة البعيد</b> — 40 وجه (دورات)\n\n"
        "أو اضغطي <b>🕌 برنامج اليوم</b> لعرض كل المهام في صفحة واحدة."
    )
    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
        )
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
            )
        except Exception:
            pass


async def fortress_1_command(update, context):
    """الحصن الأول: التهيئة (القراءة + الاستماع)."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        r_start, r_end = get_reading_pages_today(user)
        l_start, l_end = get_listening_pages_today(user)
        read_day, read_khatmah = get_reading_cycle_day(user)
        listen_day, listen_khatmah = get_listening_cycle_day(user)

    r_pages_str = fmt_pages(r_start, r_end)
    l_pages_str = fmt_pages(l_start, l_end)
    text = (
        "📖 <b>الحصن الأول — التهيئة المستمرة</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📅 <b>القراءة اليوم</b> — حزبان (20 وجه):\n"
        f"• الأوجه <b>{r_pages_str}</b>\n"
        f"• اليوم <b>{read_day}/30</b> من دورة القراءة\n"
        f"• ختمة رقم <b>{read_khatmah + 1}</b>\n"
        f"• عدد الختمات المنجزة: <b>{read_khatmah}</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🎧 <b>الاستماع اليوم</b> — حزب (10 أوجه):\n"
        f"• الأوجه <b>{l_pages_str}</b>\n"
        f"• اليوم <b>{listen_day}/60</b> من دورة الاستماع\n"
        f"• ختمة رقم <b>{listen_khatmah + 1}</b>\n"
        f"• عدد الختمات المنجزة: <b>{listen_khatmah}</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💡 <i>دورة القراءة 30 يومًا (حزبان/يوم)، ودورة الاستماع 60 يومًا (حزب/يوم). "
        "تبدآن من تاريخ بداية الخطة وتتكرّران تلقائيًا.</i>"
    )
    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
            )
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
        )


async def fortress_2_command(update, context):
    """الحصن الثاني: التحضير."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        weekly_start, weekly_end = get_weekly_prep_range(user)
        nightly_page = get_nightly_prep_page(user)
        pre_session_page = get_pre_session_prep_page(user)
        progress = await get_or_create_progress(session, user.id)

    pre_duration = progress.pre_session_duration_min or 0
    started = "✅ بدأت" if progress.pre_session_started_at else "⏳ لم تبدأ"
    text = (
        "📚 <b>الحصن الثاني — التحضير</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📅 <b>التحضير الأسبوعي</b> — قراءة حفظ الأسبوع القادم قبل دخوله:\n"
        f"• الأوجه <b>{weekly_start} → {weekly_end}</b>\n"
        f"• المقدار: <b>{user.weekly_memo_amount} وجه/أسبوع</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🌙 <b>التحضير الليلي</b> — قراءة وجه الغد قبل النوم:\n"
        f"• الوجه <b>{nightly_page}</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "⏱️ <b>التحضير القبلي</b> — قراءة الدرس قبل الحفظ مباشرة:\n"
        f"• الوجه <b>{pre_session_page}</b>\n"
        f"• الحالة: {started}\n"
        f"• المدة المسجَّلة: <b>{pre_duration} دقيقة</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💡 <i>اضغطي زر ⏱️ التحضير القبلي في برنامج اليوم لبدء المؤقّت، "
        "ثم اضغطيه مرة أخرى عند الانتهاء لحساب المدة.</i>"
    )
    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
            )
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
        )


async def fortress_3_command(update, context):
    """الحصن الثالث: الحفظ الجديد."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        f = compute_fortresses(user)
    np1 = f["next_memorize_page"]
    np2 = min(np1 + user.daily_memo_amount - 1, quran_data.TOTAL_PAGES)
    surah = quran_data.page_to_surah(np1)
    juz = quran_data.page_to_juz(np1)
    text = (
        "🆕 <b>الحصن الثالث — الحفظ الجديد</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📍 الأوجه القادمة: <b>{np1} → {np2}</b>\n"
        f"📖 السورة: <b>{esc(surah.name_ar)}</b>\n"
        f"📚 الجزء: <b>{juz}</b>\n"
        f"📊 المقدار: <b>{user.daily_memo_amount} وجه/يوم</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💡 <b>طريقة الحفظ:</b>\n"
        "• اقرئي كل آية 10 مرات\n"
        "• اربطي الآيات حتى تُحفظ الصفحة كاملة\n"
        "• لا تنتقلي لوجه جديد حتى تُتقني الحالي تماماً\n"
        "• بعد الحفظ، اضغطي زر 🆕 حفظ في برنامج اليوم\n\n"
        "🤲 <i>اللهم اجعل القرآن ربيع قلوبنا</i>"
    )
    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
            )
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
        )


async def fortress_4_command(update, context):
    """الحصن الرابع: مراجعة القريب."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        f = compute_fortresses(user)
    if not f["has_memorized"]:
        text = (
            "🔄 <b>الحصن الرابع — مراجعة القريب</b>\n\n"
            "⏸️ <i>لا ينطبق الآن — سيُفعَّل بعد حفظ أول وجه</i>"
        )
    else:
        start_surah = quran_data.page_to_surah(f["near_start"])
        end_surah = quran_data.page_to_surah(f["near_end"])
        text = (
            "🔄 <b>الحصن الرابع — مراجعة القريب</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            f"📍 الأوجه <b>{f['near_start']} → {f['near_end']}</b> (آخر 20 وجه محفوظ)\n"
            f"📖 السور: {esc(start_surah.name_ar)} ← {esc(end_surah.name_ar)}\n\n"
            "💡 <i>تُراجع يومياً كاملة. هذا أقوى الحصون ضد النسيان.</i>\n"
            "🤲 <i>اقرئيها من المصحف ثم من ذاكرتك</i>"
        )
    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
            )
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
        )


async def fortress_5_command(update, context):
    """الحصن الخامس: مراجعة البعيد."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        f = compute_fortresses(user)
        if f.get("has_far_review"):
            far_surah_start = quran_data.page_to_surah(f["far_start"])
            far_surah_end = quran_data.page_to_surah(f["far_end"])
    if not f["has_memorized"]:
        text = (
            "🛡️ <b>الحصن الخامس — مراجعة البعيد</b>\n\n"
            "⏸️ <i>لا ينطبق الآن — سيُفعَّل بعد حفظ 20+ وجه</i>"
        )
    elif not f.get("has_far_review"):
        text = (
            "🛡️ <b>الحصن الخامس — مراجعة البعيد</b>\n\n"
            "⏸️ <i>لا ينطبق الآن — المحفوظ أقل من 60 وجه</i>"
        )
    else:
        text = (
            "🛡️ <b>الحصن الخامس — مراجعة البعيد</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            f"📍 الأوجه <b>{f['far_start']} → {f['far_end']}</b>\n"
            f"📖 السور: {esc(far_surah_start.name_ar)} ← {esc(far_surah_end.name_ar)}\n"
            f"🔄 الدورة <b>{f['far_cycle']}/{f['far_total_cycles']}</b>\n\n"
            "💡 <i>تُقسَّم على أيام الأسبوع. الهدف التذكير لا الإتقان التام.</i>\n"
            "━━━━━━━━━━━━━━━━\n"
            "✅ عند إتمام الدورة، اضغطي زر 🔁 في برنامج اليوم لانتقال للدورة التالية."
        )
    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
            )
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
        )


# ====== التقدم ======

async def progress_command(update, context):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            await ask_onboarding_question(update, context, welcome=False)
            return
        count = await count_memorized(session, user.id)
        history = await get_memorization_history(session, user.id)
        read_day, read_khatmah = get_reading_cycle_day(user)
        listen_day, listen_khatmah = get_listening_cycle_day(user)

    total = quran_data.TOTAL_PAGES
    percent = (count / total) * 100 if total > 0 else 0
    bar = progress_bar(count, total, 20)
    remaining = total - count
    months = remaining // 30 if count > 0 else 0
    recent = history[-5:]
    recent_text = ""
    for m in reversed(recent):
        surah = quran_data.page_to_surah(m.page_number)
        recent_text += f"• وجه {esc(m.page_number)} ({esc(surah.name_ar)}) — {esc(m.date_memorized)}\n"
    percent_str = f"{percent:.1f}"
    text = (
        f"📊 <b>تقدّمك في حفظ القرآن</b>\n\n"
        f"<code>{bar}</code>\n"
        f"📖 المحفوظ: <b>{count} / {total}</b> وجه ({esc(percent_str)}%)\n"
        f"⏳ المتبقي: <b>{remaining}</b> وجه (~{months} شهر)\n\n"
        f"📍 الوجه الحالي: <b>{user.current_page}</b>\n"
        f"🔥 أيام الالتزام المتتالية: <b>{user.streak_days or 0} يوم</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📖 <b>دورة القراءة:</b> يوم {read_day}/30 (ختمة رقم {read_khatmah + 1})\n"
        f"🎧 <b>دورة الاستماع:</b> يوم {listen_day}/60 (ختمة رقم {listen_khatmah + 1})\n\n"
    )
    if recent_text:
        text += f"📋 <b>آخر 5 أوجه محفوظة:</b>\n{recent_text}\n"
    text += (
        "━━━━━━━━━━━━━━━━\n"
        "🤲 <i>اللهم اجعلنا من أهل القرآن الذين هم أهل لك وخاصتك</i>"
    )
    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
            )
        except Exception:
            pass


# ====== سجل الإنجاز ======

async def achievements_command(update, context):
    """يعرض سجل إنجاز آخر 14 يومًا."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            await ask_onboarding_question(update, context, welcome=False)
            return
        end_date = date.today()
        start_date = end_date - timedelta(days=13)
        result = await session.execute(
            select(AchievementLog).where(and_(
                AchievementLog.user_id == user.id,
                AchievementLog.log_date >= start_date,
                AchievementLog.log_date <= end_date,
            )).order_by(AchievementLog.log_date.desc())
        )
        logs = list(result.scalars().all())

    text = (
        f"📅 <b>سجل الإنجاز — آخر 14 يومًا</b>\n\n"
        f"🔥 أيام الالتزام المتتالية: <b>{user.streak_days or 0} يوم</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
    )

    if not logs:
        text += "<i>لا يوجد سجل بعد. ابدئي بإنجاز مهام اليوم!</i>"
    else:
        # إحصائيات
        completed_days = sum(1 for l in logs if l.overall_status == "completed")
        partial_days = sum(1 for l in logs if l.overall_status == "partial")
        missed_days = sum(1 for l in logs if l.overall_status == "missed")
        text += (
            f"✅ أيام مكتملة: <b>{completed_days}</b>\n"
            f"⚡ أيام جزئية: <b>{partial_days}</b>\n"
            f"❌ أيام فائتة: <b>{missed_days}</b>\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "📋 <b>التفاصيل:</b>\n\n"
        )
        for l in logs[:14]:
            status_icon = {"completed": "✅", "partial": "⚡", "missed": "❌"}.get(l.overall_status, "❓")
            completed_count = sum([
                l.reading_done, l.listening_done, l.weekly_prep_done, l.nightly_prep_done,
                l.pre_session_prep_done, l.memorize_done, l.near_review_done, l.far_review_done,
            ])
            text += f"{status_icon} <code>{esc(l.log_date)}</code> — {completed_count}/8 مهام\n"

    text += "\n🤲 <i>استمري، فالقليل الدائم خير من الكثير المنقطع</i>"
    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
            )
        except Exception:
            pass


# ====== الإعدادات ======

async def settings_command(update, context):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            await ask_onboarding_question(update, context, welcome=False)
            return
    text = (
        "⚙️ <b>الإعدادات</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📖 آخر وجه محفوظ: <b>{user.last_memorized_page or 0}</b>\n"
        f"📍 الوجه الحالي: <b>{user.current_page}</b>\n"
        f"📅 تاريخ بداية الخطة: <code>{esc(user.plan_start_date)}</code>\n"
        f"📚 مقدار الحفظ اليومي: <b>{user.daily_memo_amount} وجه</b>\n"
        f"📚 مقدار الحفظ الأسبوعي: <b>{user.weekly_memo_amount} وجه</b>\n"
        f"🌍 المنطقة الزمنية: <code>{esc(user.timezone)}</code>\n"
        f"🔔 الإشعارات: {'✅ مفعّلة' if user.notifications_enabled else '❌ معطّلة'}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🕒 <b>أوقات التذكيرات الـ 8:</b>\n"
        f"• 🆕 الحفظ: <code>{user.reminder_memorize}</code>\n"
        f"• 📖 القراءة: <code>{user.reminder_reading}</code>\n"
        f"• 📚 التحضير الأسبوعي: <code>{user.reminder_weekly_prep}</code>\n"
        f"• ⏱️ التحضير القبلي: <code>{user.reminder_pre_session}</code>\n"
        f"• 🎧 الاستماع: <code>{user.reminder_listening}</code>\n"
        f"• 🔄 مراجعة القريب: <code>{user.reminder_near_review}</code>\n"
        f"• 🛡️ مراجعة البعيد: <code>{user.reminder_far_review}</code>\n"
        f"• 🌙 التحضير الليلي: <code>{user.reminder_nightly_prep}</code>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📋 <b>الأوامر المتاحة:</b>\n"
        "• <code>/update سورة المائدة</code> — تحديث آخر وجه محفوظ\n"
        "• <code>/settime memorize 06:00</code> — ضبط وقت تذكير\n"
        "  الأنواع: memorize, reading, listening, weekly_prep,\n"
        "           nightly_prep, pre_session, near_review, far_review\n"
        "• <code>/setamount daily 2</code> — ضبط مقدار الحفظ اليومي\n"
        "• <code>/setamount weekly 7</code> — ضبط مقدار الحفظ الأسبوعي\n"
        "• <code>/planstart 2026-08-09</code> — تعديل تاريخ بداية الخطة\n"
        "• <code>/timezone Africa/Algiers</code> — ضبط المنطقة الزمنية\n"
        "• <code>/notifications on|off</code> — تفعيل/تعطيل الإشعارات\n"
        "• <code>/reset</code> — إعادة التهيئة\n"
        "• <code>/help</code> — المساعدة الشاملة\n\n"
        "🤲 <i>اللهم علّمنا ما ينفعنا</i>"
    )
    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
            )
        except Exception:
            pass


async def help_command(update, context):
    text = (
        "📖 <b>دليل بوت الحصون الخمسة (v3)</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🏰 <b>الحصون الخمسة:</b>\n\n"
        "1️⃣ <b>التهيئة المستمرة</b>\n"
        "   • قراءة حزبين/يوم (دورة 30 يومًا = ختمة)\n"
        "   • استماع حزب/يوم (دورة 60 يومًا = ختمة)\n\n"
        "2️⃣ <b>التحضير</b> — أسبوعي + ليلي + قبلي (مع مؤقّت)\n\n"
        "3️⃣ <b>الحفظ الجديد</b> — 1 أو 2 وجه/يوم حسب اختيارك\n\n"
        "4️⃣ <b>مراجعة القريب</b> — آخر 20 وجه محفوظ (يومياً)\n\n"
        "5️⃣ <b>مراجعة البعيد</b> — 40 وجه (دورات متجددة)\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🕒 <b>8 تذكيرات يومية</b> — قابلة للضبط من ⚙️ الإعدادات\n\n"
        "🔥 <b>أيام الالتزام المتتالية</b> — تُحسب عند إتمام مهمة واحدة على الأقل يومياً\n\n"
        "📋 <b>الأوامر:</b>\n"
        "• <code>/start</code> — البدء أو العودة\n"
        "• <code>/today</code> — برنامج اليوم المدمج\n"
        "• <code>/fortresses</code> — قائمة الحصون الخمسة\n"
        "• <code>/progress</code> — تقدّمك في الحفظ\n"
        "• <code>/achievements</code> — سجل الإنجاز\n"
        "• <code>/settings</code> — الإعدادات الكاملة\n"
        "• <code>/update سورة المائدة</code> — تحديث آخر محفوظ\n"
        "• <code>/settime memorize 06:00</code> — ضبط تذكير\n"
        "• <code>/setamount daily 2</code> — مقدار الحفظ اليومي\n"
        "• <code>/planstart 2026-08-09</code> — تاريخ بداية الخطة\n"
        "• <code>/notifications on</code> — تفعيل الإشعارات\n"
        "• <code>/reset</code> — إعادة التهيئة\n\n"
        "🤲 <i>اللهم اجعل القرآن ربيع قلوبنا ونور صدورنا</i>"
    )
    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=fortresses_inline_keyboard(), disable_web_page_preview=True,
            )
        except Exception:
            pass


# ====== /update — تحديث آخر وجه محفوظ ======

async def update_command(update, context):
    if not context.args:
        text = (
            "🔄 <b>تحديث آخر وجه محفوظ</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "استخدمي إحدى الصيغ التالية:\n\n"
            "• <code>/update صفحة 127</code>\n"
            "• <code>/update سورة المائدة</code>\n"
            "• <code>/update جزء 7</code>\n"
            "• <code>/update ختمت القرآن</code>\n"
            "• <code>/update 0</code> (إعادة من البداية)\n\n"
            "💡 <i>سيُعاد حساب الحصون تلقائياً</i>"
        )
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    text_input = " ".join(context.args)
    parsed = await parse_memorization_input(text_input)
    if parsed["page"] is None and "0" not in text_input:
        await update.message.reply_text(
            "❌ <b>لم أفهم الإدخال</b> 😅\nجرّب: <code>/update سورة المائدة</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    page = parsed["page"] or 0
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if page == 0:
            user.current_page = 1
            user.start_page = 1
            user.last_memorized_page = 0
            user.total_memorized = 0
            user.onboarding_done = True
            await session.execute(Memorization.__table__.delete().where(Memorization.user_id == user.id))
            await session.commit()
            await update.message.reply_text(
                "✅ <b>تمّت الإعادة من البداية</b> 🌱\n📖 ستبدئين من الوجه 1 (سورة الفاتحة)",
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(), disable_web_page_preview=True,
            )
        else:
            await set_memorized_up_to(session, user, page, first_page=parsed.get("first_page"))
            await session.refresh(user)
            f = compute_fortresses(user)
            far_str = (
                f"{f['far_start']}–{f['far_end']}"
                if f.get("has_far_review") else "⏸️ لا ينطبق بعد"
            )
            await update.message.reply_text(
                f"✅ <b>تمّ التحديث!</b> 🎉\n\n"
                f"آخر وجه محفوظ: <b>{f['last_memorized_page']}</b>\n\n"
                "━━━━━━━━━━━━━━━━\n"
                "📊 <b>الحصون بعد التحديث:</b>\n\n"
                f"🆕 الحفظ الجديد: الوجه <b>{f['next_memorize_page']}</b>\n"
                f"🔄 مراجعة القريب: <b>{f['near_start']}–{f['near_end']}</b>\n"
                f"🛡️ مراجعة البعيد: <b>{far_str}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(), disable_web_page_preview=True,
            )


# ====== /settime (محدّث لـ 8 تذكيرات) ======

async def settime_command(update, context):
    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ <b>استخدمي:</b>\n"
            "<code>/settime memorize 06:00</code>\n"
            "<code>/settime reading 08:00</code>\n"
            "<code>/settime listening 13:00</code>\n"
            "<code>/settime weekly_prep 09:00</code>\n"
            "<code>/settime nightly_prep 21:00</code>\n"
            "<code>/settime pre_session 10:00</code>\n"
            "<code>/settime near_review 16:00</code>\n"
            "<code>/settime far_review 20:00</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    period, time_str = context.args
    period = period.lower()
    valid_periods = {
        "memorize": "reminder_memorize",
        "reading": "reminder_reading",
        "listening": "reminder_listening",
        "weekly_prep": "reminder_weekly_prep",
        "nightly_prep": "reminder_nightly_prep",
        "pre_session": "reminder_pre_session",
        "near_review": "reminder_near_review",
        "far_review": "reminder_far_review",
    }
    if period not in valid_periods:
        await update.message.reply_text(
            "❌ النوع غير معروف. الأنواع: memorize, reading, listening,\n"
            "weekly_prep, nightly_prep, pre_session, near_review, far_review",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    try:
        h, m = map(int, time_str.split(":"))
        if not (0 <= h < 24 and 0 <= m < 60): raise ValueError
        time_str = f"{h:02d}:{m:02d}"
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ الوقت بصيغة HH:MM (مثلاً: 08:30)",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        setattr(user, valid_periods[period], time_str)
        await session.commit()
    labels = {
        "memorize": "الحفظ", "reading": "القراءة", "listening": "الاستماع",
        "weekly_prep": "التحضير الأسبوعي", "nightly_prep": "التحضير الليلي",
        "pre_session": "التحضير القبلي", "near_review": "مراجعة القريب",
        "far_review": "مراجعة البعيد",
    }
    await update.message.reply_text(
        f"✅ تحديث وقت <b>{labels[period]}</b>: <code>{esc(time_str)}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(), disable_web_page_preview=True,
    )


# ====== /setamount ======

async def setamount_command(update, context):
    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ استخدمي: <code>/setamount daily 2</code> أو <code>/setamount weekly 7</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    period, amount_str = context.args
    period = period.lower()
    if period not in ("daily", "weekly"):
        await update.message.reply_text(
            "❌ النوع: daily أو weekly",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    try:
        amount = int(amount_str)
    except ValueError:
        await update.message.reply_text(
            "❌ المقدار يجب أن يكون رقمًا",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    if amount < 1 or amount > 30:
        await update.message.reply_text(
            "❌ المقدار بين 1 و 30",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if period == "daily":
            user.daily_memo_amount = amount
        else:
            user.weekly_memo_amount = amount
            # تحديث نطاق التحضير الأسبوعي
            next_start = (user.last_memorized_page or 0) + 1
            user.weekly_prep_start = min(next_start, quran_data.TOTAL_PAGES)
            user.weekly_prep_end = min(quran_data.TOTAL_PAGES, user.weekly_prep_start + amount - 1)
        await session.commit()
    label = "اليومي" if period == "daily" else "الأسبوعي"
    await update.message.reply_text(
        f"✅ مقدار الحفظ {label}: <b>{amount} وجه</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(), disable_web_page_preview=True,
    )


# ====== /planstart ======

async def planstart_command(update, context):
    if not context.args:
        await update.message.reply_text(
            "❌ استخدمي: <code>/planstart 2026-08-09</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    try:
        new_date = datetime.strptime(context.args[0], "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text(
            "❌ صيغة التاريخ: YYYY-MM-DD (مثلاً: 2026-08-09)",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        user.plan_start_date = new_date
        await session.commit()
    await update.message.reply_text(
        f"✅ تاريخ بداية الخطة: <code>{esc(new_date)}</code>\n"
        "💡 ستُعاد حساب دورات القراءة والاستماع بناءً على هذا التاريخ.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(), disable_web_page_preview=True,
    )


# ====== /notifications ======

async def notifications_command(update, context):
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.message.reply_text(
            "❌ استخدمي: <code>/notifications on</code> أو <code>/notifications off</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    enabled = context.args[0].lower() == "on"
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        user.notifications_enabled = enabled
        await session.commit()
    await update.message.reply_text(
        f"✅ الإشعارات: {'✅ مفعّلة' if enabled else '❌ معطّلة'}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(), disable_web_page_preview=True,
    )


# ====== /timezone ======

async def timezone_command(update, context):
    if not context.args:
        await update.message.reply_text(
            "❌ استخدمي: <code>/timezone Africa/Algiers</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    tz = context.args[0]
    try:
        import pytz; pytz.timezone(tz)
    except Exception:
        await update.message.reply_text(
            "❌ منطقة غير معروفة",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(), disable_web_page_preview=True,
        )
        return
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        user.timezone = tz
        await session.commit()
    await update.message.reply_text(
        f"✅ المنطقة الزمنية: <code>{esc(tz)}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(), disable_web_page_preview=True,
    )


# ====== /reset ======

async def reset_command(update, context):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        await session.execute(Memorization.__table__.delete().where(Memorization.user_id == user.id))
        await session.execute(WeeklyReview.__table__.delete().where(WeeklyReview.user_id == user.id))
        await session.execute(MonthlyReview.__table__.delete().where(MonthlyReview.user_id == user.id))
        await session.execute(DailyProgress.__table__.delete().where(DailyProgress.user_id == user.id))
        await session.execute(AchievementLog.__table__.delete().where(AchievementLog.user_id == user.id))
        user.current_page = 1; user.start_page = 1; user.last_memorized_page = 0
        user.total_memorized = 0; user.onboarding_done = False
        user.streak_days = 0; user.last_active_date = None
        user.far_review_cycle = 1
        await session.commit()
    ONBOARDING_STATE.pop(update.effective_user.id, None)
    ONBOARDING_DATA.pop(update.effective_user.id, None)
    await update.message.reply_text(
        "✅ <b>تمت إعادة التهيئة</b>\n\nاكتبي /start لبدء التهيئة من جديد",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(), disable_web_page_preview=True,
    )


# ====== معالج أزرار Inline الموحَّد ======

async def button_callback(update, context):
    """معالج موحّد لكل أزرار Inline."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"تعذّر answer_callback_query: {e}")

    data = query.data or ""

    # ====== أزرار التهيئة (الخطوة 1) ======
    if data == "ob_0":
        await _process_onboarding_memorization(update, context, "0")
        return
    if data == "ob_all":
        await _process_onboarding_memorization(update, context, "ختمت القرآن")
        return
    if data == "ob_manual":
        ONBOARDING_STATE[update.effective_user.id] = "waiting_for_memorization"
        try:
            await query.edit_message_text(
                "✍️ <b>اكتبي إجابتك الآن</b>\n\n"
                "أمثلة:\n"
                "• <code>صفحة 127</code>\n"
                "• <code>سورة المائدة</code>\n"
                "• <code>جزء 7</code>\n"
                "• <code>0</code> (لم أحفظ شيئاً)",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception:
            pass
        return
    m = re.match(r"^ob_surah_(\d+)$", data)
    if m:
        surah_num = int(m.group(1))
        surah = quran_data.get_surah_by_number(surah_num)
        if surah:
            await _process_onboarding_memorization(update, context, f"سورة {surah.name_ar}")
        return

    # ====== أزرار التهيئة (الخطوة 2: مقدار يومي) ======
    m = re.match(r"^daily_(\d+)$", data)
    if m:
        amount = int(m.group(1))
        if amount in (1, 2):
            async with AsyncSessionLocal() as session:
                user = await get_or_create_user(session, telegram_id=update.effective_user.id)
                user.daily_memo_amount = amount
                await session.commit()
            await ask_weekly_amount(update, context)
        return

    # ====== أزرار التهيئة (الخطوة 3: مقدار أسبوعي) ======
    m = re.match(r"^weekly_(\d+)$", data)
    if m:
        amount = int(m.group(1))
        if amount in (5, 7, 10, 14):
            async with AsyncSessionLocal() as session:
                user = await get_or_create_user(session, telegram_id=update.effective_user.id)
                user.weekly_memo_amount = amount
                next_start = (user.last_memorized_page or 0) + 1
                user.weekly_prep_start = min(next_start, quran_data.TOTAL_PAGES)
                user.weekly_prep_end = min(quran_data.TOTAL_PAGES, user.weekly_prep_start + amount - 1)
                await session.commit()
            await ask_plan_start_date(update, context)
        return

    # ====== أزرار التهيئة (الخطوة 4: تاريخ البداية) ======
    if data == "plan_today":
        async with AsyncSessionLocal() as session:
            user = await get_or_create_user(session, telegram_id=update.effective_user.id)
            user.plan_start_date = date.today()
            await session.commit()
        await ask_reminder_times(update, context)
        return
    if data == "plan_manual":
        ONBOARDING_STATE[update.effective_user.id] = "waiting_for_plan_start_date"
        try:
            await query.edit_message_text(
                "✍️ <b>اكتبي تاريخ البداية</b>\n\n"
                "الصيغة: <code>YYYY-MM-DD</code>\n"
                "مثال: <code>2026-08-09</code>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception:
            pass
        return

    # ====== أزرار التهيئة (الخطوة 5: التذكيرات) ======
    if data == "reminders_default":
        await finalize_onboarding(update, context)
        return
    if data == "reminders_customize":
        # نُنهي الـ onboarding ونُظهر رسالة بأنها قابلة للتعديل
        await finalize_onboarding(update, context)
        return

    # ====== أزرار القائمة الفرعية للحصون ======
    if data == "fortresses_menu":
        await fortresses_command(update, context)
        return
    if data == "today_program":
        await _show_today_program(update, context)
        return
    if data == "fortress_1":
        await fortress_1_command(update, context)
        return
    if data == "fortress_2":
        await fortress_2_command(update, context)
        return
    if data == "fortress_3":
        await fortress_3_command(update, context)
        return
    if data == "fortress_4":
        await fortress_4_command(update, context)
        return
    if data == "fortress_5":
        await fortress_5_command(update, context)
        return

    # ====== أزرار تسجيل المهام ======
    m = re.match(r"^task_(?!done_)(.+)$", data)
    if m:
        task_type = m.group(1)
        async with AsyncSessionLocal() as session:
            user = await get_or_create_user(session, telegram_id=update.effective_user.id)
            if task_type == "memorize":
                # تسجيل الحفظ وتقدّم الوجه
                await mark_memorized(session, user, user.current_page)
            if task_type == "far_review":
                # عند إتمام مراجعة البعيد، ننتقل للدورة التالية
                advance_far_review_cycle(user)
                await session.commit()
            await mark_progress_done(session, user.id, task_type)
        # إعادة عرض برنامج اليوم
        await _show_today_program(update, context)
        return

    # مفتاح غرض_منتهي (للأزرار التي ضُغطت سابقاً) — لا شيء
    if data.startswith("task_done_"):
        # المهمة مكتملة بالفعل — نُظهر رسالة بسيطة
        try:
            await query.answer("✅ هذه المهمة مكتملة بالفعل", show_alert=False)
        except Exception:
            pass
        return

    logger.warning(f"callback_data غير معروف: {data}")


# ============== 6. المجدول (8 تذكيرات) ==============
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

scheduler = AsyncIOScheduler(timezone="UTC")


def _today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


async def _send_reminder(bot, telegram_id, task_type, text):
    """يُرسل تذكيرًا للمستخدمة."""
    try:
        async with AsyncSessionLocal() as session:
            user = await get_or_create_user(session, telegram_id=telegram_id)
            if not user.onboarding_done or not user.notifications_enabled:
                return
        await bot.send_message(
            chat_id=telegram_id,
            text=text, parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"خطأ في تذكير {task_type} لـ {telegram_id}: {e}")


async def send_memorize_reminder(bot, telegram_id):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=telegram_id)
        if not user.onboarding_done or not user.notifications_enabled: return
        f = compute_fortresses(user)
        next_page = f["next_memorize_page"]
        surah = quran_data.page_to_surah(next_page)
    text = (
        "🆕 <b>تذكير: وقت الحفظ الجديد</b>\n\n"
        f"📍 الوجه القادم: <b>{next_page}</b>\n"
        f"📖 سورة {esc(surah.name_ar)}\n\n"
        "💡 <i>ابدئي بقراءة الوجه 3 مرات قبل الحفظ</i>\n"
        "━━━━━━━━━━━━━━━━\n"
        "اضغطي 🕌 الحصون الخمسة ثم 🕌 برنامج اليوم"
    )
    await _send_reminder(bot, telegram_id, "memorize", text)


async def send_reading_reminder(bot, telegram_id):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=telegram_id)
        if not user.onboarding_done or not user.notifications_enabled: return
        r_start, r_end = get_reading_pages_today(user)
        read_day, read_khatmah = get_reading_cycle_day(user)
    r_pages_str = fmt_pages(r_start, r_end)
    text = (
        "📖 <b>تذكير: وقت القراءة الصباحية</b>\n\n"
        f"📍 الأوجه: <b>{r_pages_str}</b>\n"
        f"📅 اليوم {read_day}/30 من دورة القراءة (ختمة {read_khatmah + 1})\n\n"
        "💡 <i>حزبان في اليوم = ختمة كل 30 يومًا</i>"
    )
    await _send_reminder(bot, telegram_id, "reading", text)


async def send_listening_reminder(bot, telegram_id):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=telegram_id)
        if not user.onboarding_done or not user.notifications_enabled: return
        l_start, l_end = get_listening_pages_today(user)
        listen_day, listen_khatmah = get_listening_cycle_day(user)
    l_pages_str = fmt_pages(l_start, l_end)
    text = (
        "🎧 <b>تذكير: وقت الاستماع</b>\n\n"
        f"📍 الأوجه: <b>{l_pages_str}</b>\n"
        f"📅 اليوم {listen_day}/60 من دورة الاستماع (ختمة {listen_khatmah + 1})\n\n"
        "💡 <i>حزب في اليوم = ختمة كل 60 يومًا</i>"
    )
    await _send_reminder(bot, telegram_id, "listening", text)


async def send_weekly_prep_reminder(bot, telegram_id):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=telegram_id)
        if not user.onboarding_done or not user.notifications_enabled: return
        weekly_start, weekly_end = get_weekly_prep_range(user)
    text = (
        "📚 <b>تذكير: التحضير الأسبوعي</b>\n\n"
        f"📍 الأوجه: <b>{weekly_start} → {weekly_end}</b>\n"
        f"📊 المقدار: <b>{user.weekly_memo_amount} وجه/أسبوع</b>\n\n"
        "💡 <i>اقرئي حفظ الأسبوع القادم قبل دخوله</i>"
    )
    await _send_reminder(bot, telegram_id, "weekly_prep", text)


async def send_nightly_prep_reminder(bot, telegram_id):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=telegram_id)
        if not user.onboarding_done or not user.notifications_enabled: return
        nightly_page = get_nightly_prep_page(user)
    text = (
        "🌙 <b>تذكير: التحضير الليلي</b>\n\n"
        f"📍 اقرئي الوجه <b>{nightly_page}</b> قبل النوم\n\n"
        "💡 <i>قراءة فقط، دون حفظ — تهيئة الذهن لوجه الغد</i>"
    )
    await _send_reminder(bot, telegram_id, "nightly_prep", text)


async def send_pre_session_reminder(bot, telegram_id):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=telegram_id)
        if not user.onboarding_done or not user.notifications_enabled: return
        pre_page = get_pre_session_prep_page(user)
    text = (
        "⏱️ <b>تذكير: التحضير القبلي</b>\n\n"
        f"📍 اقرئي الوجه <b>{pre_page}</b> قبل الحفظ\n\n"
        "💡 <i>اضغطي زر ⏱️ في برنامج اليوم لبدء المؤقّت</i>"
    )
    await _send_reminder(bot, telegram_id, "pre_session", text)


async def send_near_review_reminder(bot, telegram_id):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=telegram_id)
        if not user.onboarding_done or not user.notifications_enabled: return
        near_start, near_end = get_near_review_range(user)
    if near_start is None:
        text = "🔄 <b>تذكير: مراجعة القريب</b>\n\n⏸️ <i>لا ينطبق الآن — حفظك أقل من 20 وجه</i>"
    else:
        text = (
            "🔄 <b>تذكير: مراجعة القريب</b>\n\n"
            f"📍 الأوجه: <b>{near_start} → {near_end}</b>\n\n"
            "💡 <i>آخر 20 وجه محفوظ — تُراجع يومياً</i>"
        )
    await _send_reminder(bot, telegram_id, "near_review", text)


async def send_far_review_reminder(bot, telegram_id):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=telegram_id)
        if not user.onboarding_done or not user.notifications_enabled: return
        f = compute_fortresses(user)
    if not f.get("has_far_review"):
        text = "🛡️ <b>تذكير: مراجعة البعيد</b>\n\n⏸️ <i>لا ينطبق الآن</i>"
    else:
        text = (
            "🛡️ <b>تذكير: مراجعة البعيد</b>\n\n"
            f"📍 الأوجه: <b>{f['far_start']} → {f['far_end']}</b>\n"
            f"🔄 الدورة {f['far_cycle']}/{f['far_total_cycles']}\n\n"
            "💡 <i>قسّميها على أيام الأسبوع</i>"
        )
    await _send_reminder(bot, telegram_id, "far_review", text)


async def schedule_user_jobs(bot):
    """يجدول 8 تذكيرات يومية لكل مستخدمة نشطة."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.is_active == True))
        users = list(result.scalars().all())

    REMINDER_FUNCS = {
        "reminder_memorize": send_memorize_reminder,
        "reminder_reading": send_reading_reminder,
        "reminder_listening": send_listening_reminder,
        "reminder_weekly_prep": send_weekly_prep_reminder,
        "reminder_nightly_prep": send_nightly_prep_reminder,
        "reminder_pre_session": send_pre_session_reminder,
        "reminder_near_review": send_near_review_reminder,
        "reminder_far_review": send_far_review_reminder,
    }

    for user in users:
        try:
            tz = pytz.timezone(user.timezone)
        except Exception:
            tz = pytz.timezone("Africa/Algiers")
        for field, func in REMINDER_FUNCS.items():
            time_str = getattr(user, field, "08:00") or "08:00"
            try:
                h, m = map(int, time_str.split(":"))
            except Exception:
                h, m = 8, 0
            job_id = f"{field}_{user.telegram_id}"
            try: scheduler.remove_job(job_id)
            except Exception: pass
            scheduler.add_job(
                func, CronTrigger(hour=h, minute=m, timezone=tz),
                args=[bot, user.telegram_id],
                id=job_id, replace_existing=True,
            )
    logger.info(f"تمت جدولة {len(users)} مستخدمًا × 8 تذكيرات = {len(users) * 8} وظيفة")


def start_scheduler(bot):
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ بدأ المجدول")
    asyncio.create_task(schedule_user_jobs(bot))


async def reschedule_all(bot):
    await schedule_user_jobs(bot)


async def _periodic_reschedule(bot):
    while True:
        await asyncio.sleep(3600)
        try:
            await reschedule_all(bot)
        except Exception as e:
            logger.error(f"خطأ في إعادة الجدولة: {e}")


# ============== 7. keep-alive مدمج ==============
from aiohttp import web


async def _health_handler(request):
    return web.json_response({
        "status": "ok", "service": "quran-husun-bot-v3",
        "timestamp": date.today().isoformat(),
    })


async def _root_handler(request):
    return web.Response(text="Quran Husun Bot v3 is running ✅")


async def _do_ping(url, timeout_sec=15.0):
    try:
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                return resp.status == 200
    except asyncio.CancelledError: raise
    except Exception as e:
        logger.warning(f"keep-alive: فشل الـ ping إلى {url}: {e}")
        return False


async def keepalive_loop(url, interval=280, startup_delay=15):
    if not url:
        logger.warning("keep-alive: URL غير مضبوط"); return
    logger.info(f"keep-alive: ping كل {interval} ثانية إلى {url}")
    await asyncio.sleep(startup_delay)
    success_count = 0; fail_count = 0
    while True:
        try:
            ok = await _do_ping(url)
            if ok:
                success_count += 1
                if success_count % 10 == 0:
                    logger.info(f"keep-alive: {success_count} نجاح، {fail_count} فشل")
            else:
                fail_count += 1
        except asyncio.CancelledError:
            break
        except Exception:
            fail_count += 1
        await asyncio.sleep(interval)


async def start_keepalive_server(port, public_health_url="", keepalive_interval=280):
    app = web.Application()
    app.router.add_get("/", _root_handler)
    app.router.add_get("/health", _health_handler)
    app.router.add_get("/ping", _health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"keep-alive: خادم HTTP على المنفذ {port}")
    keepalive_task = None
    if public_health_url:
        keepalive_task = asyncio.create_task(keepalive_loop(url=public_health_url, interval=keepalive_interval))
    return runner, keepalive_task


# ============== 8. نقطة التشغيل ==============

async def post_init(app):
    logger.info("🔧 تهيئة قاعدة البيانات...")
    await init_db()
    logger.info("✅ قاعدة البيانات جاهزة")
    logger.info("⏰ تشغيل المجدول...")
    start_scheduler(app.bot)
    asyncio.create_task(_periodic_reschedule(app.bot))

    if KEEPALIVE_ENABLED:
        public_url = f"{RENDER_EXTERNAL_URL}/health" if RENDER_EXTERNAL_URL else ""
        logger.info(f"🌐 بدء خادم keep-alive على المنفذ {PORT}...")
        try:
            runner, keepalive_task = await start_keepalive_server(
                port=PORT, public_health_url=public_url, keepalive_interval=KEEPALIVE_INTERVAL,
            )
            app._keepalive_runner = runner
            app._keepalive_task = keepalive_task
            if public_url:
                logger.info(f"✅ keep-alive نشط")
            else:
                logger.warning("⚠️ RENDER_EXTERNAL_URL غير مضبوط")
        except Exception as e:
            logger.warning(f"⚠️ تعذّر بدء keep-alive: {e}")


async def post_shutdown(app):
    task = getattr(app, "_keepalive_task", None)
    runner = getattr(app, "_keepalive_runner", None)
    if task:
        task.cancel()
        try: await task
        except (asyncio.CancelledError, Exception): pass
    if runner:
        await runner.cleanup()


async def _error_handler(update, context):
    from telegram.error import (
        Conflict, NetworkError, TimedOut, Forbidden, BadRequest,
    )
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
        logger.error(f"❌ BadRequest: {error}", exc_info=False)
        if update and getattr(update, "effective_chat", None):
            try:
                if getattr(update, "callback_query", None):
                    try: await update.callback_query.answer()
                    except Exception: pass
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ حدث خطأ بسيط. جرّبي مرة أخرى أو اضغطي /start",
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
                text="⚠️ حدث خطأ غير متوقع. جرّبي مرة أخرى أو اضغطي /start",
                reply_markup=main_keyboard(),
            )
        except Exception:
            pass


def build_application():
    if not BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN غير مضبوط"); sys.exit(1)
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("fortresses", fortresses_command))
    app.add_handler(CommandHandler("progress", progress_command))
    app.add_handler(CommandHandler("achievements", achievements_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("update", update_command))
    app.add_handler(CommandHandler("settime", settime_command))
    app.add_handler(CommandHandler("setamount", setamount_command))
    app.add_handler(CommandHandler("planstart", planstart_command))
    app.add_handler(CommandHandler("notifications", notifications_command))
    app.add_handler(CommandHandler("timezone", timezone_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(_error_handler)
    return app


def main():
    import traceback
    try:
        logger.info("📖 بوت الحصون الخمسة v3 — البدء")
        logger.info(f"  - المنطقة الزمنية: {DEFAULT_TIMEZONE}")
        logger.info(f"  - keep-alive: {'مُفعّل' if KEEPALIVE_ENABLED else 'مُعطّل'}")
        logger.info(f"  - DATABASE_URL يبدأ بـ postgresql: {_is_postgres}")
        logger.info(f"  - BOT_TOKEN مضبوط: {bool(BOT_TOKEN)}")
        logger.info(f"  - تنسيق الرسائل: HTML")
        logger.info(f"  - عدد التذكيرات: 8 لكل مستخدمة")

        app = build_application()
        logger.info("🚀 تشغيل البوت في وضع polling...")
        app.run_polling(poll_interval=3, drop_pending_updates=True, close_loop=False)
    except Exception as e:
        logger.error("❌ خطأ أثناء التشغيل:")
        logger.error(traceback.format_exc())
        print("❌ ERROR:", e, flush=True)
        traceback.print_exc()
        sys.stdout.flush(); sys.stderr.flush()
        raise


if __name__ == "__main__":
    main()

