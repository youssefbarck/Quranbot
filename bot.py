"""
بوت تلغرام لحفظ القرآن — طريقة الحصون الخمسة
============================================
ملف واحد يجمع: الإعدادات + قاعدة البيانات + النماذج + المنطق
              + المعالجات + المجدول + keep-alive + نقطة التشغيل

التشغيل: python bot.py

ملاحظات الإصدار:
- يستخدم HTML بدل MarkdownV2 (هروب أبسط = أخطاء 400 Bad Request أقل)
- لوحة تحكم ثابتة في الأسفل (ReplyKeyboardMarkup)
- سؤال تفاعلي عن آخر سورة/صفحة حفظت قبل حساب الحصون
- تفاصيل شاملة لكل مهمة وطلب
- معالج أخطاء يُجيب CallbackQuery دائماً حتى لا يبقى الزر "loading"
"""

# ============== 1. الإعدادات ==============
import os
import sys
import asyncio
import logging
import re
import html
from datetime import date, timedelta
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_raw_db = os.getenv("DATABASE_URL", "").strip()
DATABASE_URL = _raw_db.replace("postgres://", "postgresql://")
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0") or "0")

MORNING_TIME = os.getenv("MORNING_TIME", "08:00")
MIDDAY_TIME = os.getenv("MIDDAY_TIME", "13:00")
EVENING_TIME = os.getenv("EVENING_TIME", "20:00")
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
    BigInteger, Date, DateTime, ForeignKey, Integer, String, Boolean,
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
    """إزالة معاملات libpg التي لا يقبّلها asyncpg."""
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
    print("=" * 70, flush=True)
    print("❌ خطأ: متغيّر البيئة DATABASE_URL غير مضبوط!", flush=True)
    print("   اذهب إلى Render → Environment → أضف:", flush=True)
    print("   DATABASE_URL = postgresql://user:pass@host/dbname", flush=True)
    print("=" * 70, flush=True)
    sys.exit(1)

if not _is_postgres:
    print("=" * 70, flush=True)
    print(f"❌ خطأ: DATABASE_URL يجب أن يبدأ بـ postgresql://", flush=True)
    print(f"   القيمة الحالية (masked): {_mask_url(DATABASE_URL)}", flush=True)
    print("=" * 70, flush=True)
    sys.exit(1)

_engine_kwargs = {"echo": False}
if _is_postgres:
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10
    _engine_kwargs["connect_args"] = {"ssl": True}

engine = create_async_engine(_to_async_url(DATABASE_URL), **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ============== 3. النماذج (5 جداول) ==============

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_page: Mapped[int] = mapped_column(Integer, default=1)
    start_page: Mapped[int] = mapped_column(Integer, default=1)
    last_memorized_page: Mapped[int] = mapped_column(Integer, default=0)
    total_memorized: Mapped[int] = mapped_column(Integer, default=0)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Algiers")
    morning_time: Mapped[str] = mapped_column(String(5), default="08:00")
    midday_time: Mapped[str] = mapped_column(String(5), default="13:00")
    evening_time: Mapped[str] = mapped_column(String(5), default="20:00")
    created_at: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    memorization: Mapped[list["Memorization"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    weekly_reviews: Mapped[list["WeeklyReview"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    monthly_reviews: Mapped[list["MonthlyReview"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    daily_progress: Mapped[list["DailyProgress"]] = relationship(back_populates="user", cascade="all, delete-orphan")


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
    reading_done: Mapped[bool] = mapped_column(Boolean, default=False)
    reading_pages: Mapped[str] = mapped_column(String(32), default="")
    listening_done: Mapped[bool] = mapped_column(Boolean, default=False)
    listening_pages: Mapped[str] = mapped_column(String(32), default="")
    memorize_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memorize_done: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_review_done: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped["User"] = relationship(back_populates="daily_progress")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if _is_postgres:
            try:
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_memorized_page INTEGER DEFAULT 0"
                ))
                await conn.execute(text(
                    "UPDATE users SET last_memorized_page = GREATEST(0, current_page - 1) "
                    "WHERE last_memorized_page = 0 AND current_page > 1"
                ))
            except Exception as e:
                logger.warning(f"تعذّر إضافة/تهيئة عمود last_memorized_page: {e}")


# ============== 4. المنطق ==============
import quran_data as quran_data


async def get_or_create_user(session, telegram_id, username=None, full_name=None):
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, username=username, full_name=full_name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif (username != user.username) or (full_name != user.full_name):
        user.username = username
        user.full_name = full_name
        await session.commit()
    return user


async def parse_memorization_input(text):
    """تحليل إدخال المستخدم حول آخر صفحة محفوظة.

    يعيد dict يحوي: type, value, page (آخر صفحة محفوظة), first_page, last_page, raw.
    - "كل القرآن"/"ختمت" → page=604, first=1, last=604
    - "جزء N" → first/last نطاق الجزء N
    - "سورة X" → first=1 (افتراض أن المستخدم حفظ من البداية حتى نهاية السورة)، last=آخر صفحة السورة
    - "صفحة X-Y" → first=X, last=Y
    - "صفحة X" → first=X, last=X
    - "0"/"لا شيء" → page=None (لم يحفظ بعد)
    """
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
    m = re.search(r"صفحة\s*(\d+)", text)
    if m:
        p = int(m.group(1))
        if 1 <= p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page", "value": p, "page": p,
                           "first_page": p, "last_page": p})
            return result
    m = re.match(r"^\s*(\d+)\s*$", text)
    if m:
        p = int(m.group(1))
        if 1 <= p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page", "value": p, "page": p,
                           "first_page": p, "last_page": p})
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
    if user.current_page <= page:
        user.current_page = min(page + 1, quran_data.TOTAL_PAGES)
    user.total_memorized = await count_memorized(session, user.id)
    await session.commit()
    await session.refresh(memo)
    return memo


async def count_memorized(session, user_id):
    result = await session.execute(select(func.count(Memorization.id)).where(Memorization.user_id == user_id))
    return result.scalar() or 0


async def get_today_review_pages(session, user_id):
    result = await session.execute(
        select(Memorization).where(and_(Memorization.user_id == user_id, Memorization.date_memorized == date.today()))
        .order_by(Memorization.page_number)
    )
    return [m.page_number for m in result.scalars().all()]


async def get_weekly_review_pages(session, user_id):
    week_ago = date.today() - timedelta(days=7)
    result = await session.execute(
        select(Memorization).where(and_(Memorization.user_id == user_id, Memorization.date_memorized >= week_ago))
        .order_by(Memorization.page_number)
    )
    return [m.page_number for m in result.scalars().all()]


async def get_today_weekly_review(session, user_id):
    today = date.today()
    result = await session.execute(
        select(WeeklyReview).where(WeeklyReview.user_id == user_id).order_by(WeeklyReview.date_memorized.desc())
    )
    today_tasks = []
    for r in result.scalars().all():
        days = [(0, "done_1", "ليلة"), (1, "done_2", "ليل"), (2, "done_3", "ثلث"),
                (3, "done_4", "اربعاء"), (4, "done_5", "خميس")]
        for day_offset, done_field, label in days:
            if r.date_memorized + timedelta(days=day_offset) == today:
                if not getattr(r, done_field):
                    today_tasks.append({"page": r.page_number, "label": label, "done_field": done_field, "review_id": r.id})
                    break
    return today_tasks


async def mark_weekly_review_done(session, review_id, done_field):
    result = await session.execute(select(WeeklyReview).where(WeeklyReview.id == review_id))
    review = result.scalar_one_or_none()
    if review:
        setattr(review, done_field, True)
        await session.commit()


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


def get_morning_reading_pages(user):
    """الحصن الأول (القراءة الصباحية) — شخصية لكل مستخدمة.

    القاعدة الجديدة:
      تبدأ القراءة من نفس صفحة الحفظ الجديد (next_memorize_page)
      لربط التهيئة بنقطة الحفظ الفعلية، فيستفيد القلب من قراءة ما سيحفظ قريباً.
      حجم القراءة: 20 صفحة (حزبان) — قد تتعدّى نهاية المصحف فنلفّ من البداية.

    ملاحظة: إذا لم يحفظ المستخدم شيئاً بعد، تبدأ من الصفحة 1 (الفاتحة).
    """
    f = compute_fortresses(user)
    next_page = f["next_memorize_page"] if f["has_memorized"] else 1
    start_page = max(1, min(next_page, quran_data.TOTAL_PAGES))
    end_page = start_page + 19
    # إذا تجاوزنا نهاية المصحف، نلفّ من البداية
    if end_page > quran_data.TOTAL_PAGES:
        end_page = end_page - quran_data.TOTAL_PAGES
    return start_page, end_page


def get_midday_listening_pages(user):
    """الحصن الأول (الاستماع الظهيرة) — شخصية لكل مستخدمة.

    القاعدة الجديدة:
      يبدأ الاستماع من الصفحة التالية لنهاية القراءة الصباحية،
      فيكون الاستماع للصفحات التي ستحفظها لاحقاً (ترسيخ سمعي قبل الحفظ).
      حجم الاستماع: 10 صفحات (حزب) — مع لفّ من البداية عند تجاوز المصحف.
    """
    f = compute_fortresses(user)
    next_page = f["next_memorize_page"] if f["has_memorized"] else 1
    # الاستماع يبدأ بعد 20 صفحة من القراءة (لتغطية صفحات مختلفة في نفس اليوم)
    start_page = next_page + 20
    if start_page > quran_data.TOTAL_PAGES:
        start_page = start_page - quran_data.TOTAL_PAGES
    start_page = max(1, min(start_page, quran_data.TOTAL_PAGES))
    end_page = start_page + 9
    if end_page > quran_data.TOTAL_PAGES:
        end_page = end_page - quran_data.TOTAL_PAGES
    return start_page, end_page


async def mark_progress_done(session, user_id, task_type):
    progress = await get_or_create_progress(session, user_id)
    if task_type == "reading": progress.reading_done = True
    elif task_type == "listening": progress.listening_done = True
    elif task_type == "memorize": progress.memorize_done = True
    elif task_type == "daily_review": progress.daily_review_done = True
    await session.commit()


async def get_memorization_history(session, user_id):
    result = await session.execute(
        select(Memorization).where(Memorization.user_id == user_id).order_by(Memorization.date_memorized.asc())
    )
    return list(result.scalars().all())


# ============== 4.5. الحصون الخمسة — الدالة الموحدة ==============
NEAR_REVIEW_PAGES = 20  # الحصن الرابع
FAR_REVIEW_PAGES = 40   # الحصن الخامس


def compute_fortresses(user):
    """الدالة الموحدة الوحيدة لحساب الحصون الخمسة.

    الحصن الرابع (مراجعة القريب) = آخر 20 صفحة محفوظة فعلياً
    الحصن الخامس (مراجعة البعيد) = آخر 40 صفحة محفوظة فعلياً
    """
    empty = {
        "first_memorized_page": None,
        "last_memorized_page": None,
        "near_start": None, "near_end": None,
        "far_start": None, "far_end": None,
        "next_memorize_page": 1,
        "has_memorized": False,
    }
    if user is None:
        return empty

    start_page = max(1, getattr(user, "start_page", 1) or 1)
    last_memorized = getattr(user, "last_memorized_page", 0) or 0
    current = getattr(user, "current_page", 1) or 1
    last_page = last_memorized if last_memorized > 0 else (current - 1)

    has_memorized = (
        last_page >= start_page
        or getattr(user, "total_memorized", 0) > 0
        or getattr(user, "onboarding_done", False)
    )

    if not has_memorized or last_page < 1:
        empty["next_memorize_page"] = max(1, start_page)
        return empty

    last_page = max(start_page, min(last_page, quran_data.TOTAL_PAGES))
    near_start = max(start_page, last_page - NEAR_REVIEW_PAGES + 1)
    near_end = last_page
    far_start = max(start_page, last_page - FAR_REVIEW_PAGES + 1)
    far_end = last_page
    next_memorize_page = last_page + 1 if last_page < quran_data.TOTAL_PAGES else quran_data.TOTAL_PAGES

    return {
        "first_memorized_page": start_page,
        "last_memorized_page": last_page,
        "near_start": near_start,
        "near_end": near_end,
        "far_start": far_start,
        "far_end": far_end,
        "next_memorize_page": next_memorize_page,
        "has_memorized": True,
    }

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

# حالة التهيئة التفاعلية لكل مستخدم
# القيم الممكنة:
#   "waiting_for_memorization" — بانتظار إدخال آخر سورة/صفحة محفوظة
ONBOARDING_STATE = {}


def esc(text) -> str:
    """هروب HTML آمن. يقبول str/int/float/date/None."""
    if text is None:
        return ""
    if isinstance(text, date):
        text = text.strftime("%Y-%m-%d")
    return html.escape(str(text), quote=False)


def bold(text) -> str:
    """نص عريض آمن — يقوم بهروب المحتوى أولاً."""
    return f"<b>{esc(text)}</b>"


def code(text) -> str:
    """نص كود آمن."""
    return f"<code>{esc(text)}</code>"


def link(label, url) -> str:
    """رابط آمن."""
    return f'<a href="{esc(url)}">{esc(label)}</a>'


def progress_bar(current, total, length=15):
    if total == 0: return "░" * length
    filled = int((current / total) * length)
    return "█" * filled + "░" * (length - filled)


# ====== لوحات المفاتيح ======

def main_menu_inline():
    """القائمة السياقية Inline — تُعرض مع الرسائل المُعدّلة (edit_message_text)."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 مهام اليوم", callback_data="today"),
         InlineKeyboardButton("🏰 الحصون", callback_data="fortresses")],
        [InlineKeyboardButton("📊 تقدمي", callback_data="progress"),
         InlineKeyboardButton("⚙️ مساعدة", callback_data="help")],
        [InlineKeyboardButton("🔄 تحديث المحفوظ", callback_data="update_memorized")],
    ])


def main_keyboard():
    """لوحة المفاتيح الثابتة في الأسفل (ReplyKeyboard).
    تبقى مرئية دائماً أسفل المحادثة ويمكن للمستخدم الضغط عليها بسرعة.
    """
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📋 مهام اليوم"), KeyboardButton("🏰 الحصون الخمسة")],
            [KeyboardButton("📊 تقدمي"), KeyboardButton("🔄 تحديث المحفوظ")],
            [KeyboardButton("⚙️ الإعدادات والمساعدة")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="اضغطي أحد الأزرار في الأسفل ✨",
    )


# خريطة النصوص المختصرة من لوحة المفاتيح الثابتة
KEYBOARD_TEXT_MAP = {
    "📋 مهام اليوم": "today",
    "🏰 الحصون الخمسة": "fortresses",
    "🏰 الحصون": "fortresses",
    "📊 تقدمي": "progress",
    "🔄 تحديث المحفوظ": "update_memorized",
    "⚙️ الإعدادات والمساعدة": "help",
    "⚙️ الإعدادات": "help",
    "⚙️ مساعدة": "help",
}


# ====== سؤال التهيئة التفاعلي ======

def onboarding_question_keyboard():
    """أزرار سريعة لاختيار آخر سورة محفوظة — أكثر السور شيوعاً."""
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


async def ask_onboarding_question(update, context, welcome=False):
    """يطرح سؤال التهيئة: ما آخر سورة/صفحة حفظت؟"""
    user_info = update.effective_user
    ONBOARDING_STATE[user_info.id] = "waiting_for_memorization"
    if welcome:
        intro = (
            "🤲 <b>بسم الله الرحمن الرحيم</b>\n\n"
            f"أهلاً {bold(user_info.first_name or 'أختي الكريمة')}! 🌟\n\n"
            "📖 <b>بوت الحصون الخمسة لحفظ القرآن</b>\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
        )
    else:
        intro = (
            "🤔 <b>نحتاج معرفة نقطة انطلاقك</b>\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
        )
    text = intro + (
        "❓ <b>ما آخر سورة (أو صفحة) حفظتِها من القرآن؟</b>\n\n"
        "اقتراحات سريعة للإجابة 👇:\n\n"
        "• اضغطي أحد الأزرار بالأسفل، أو اكتبي إجابتك بالنص:\n"
        "  — <code>صفحة 127</code> — آخر صفحة حفظتها هي 127\n"
        "  — <code>سورة المائدة</code> — حفظت حتى نهاية سورة المائدة\n"
        "  — <code>جزء 7</code> — حفظت 7 أجزاء كاملة\n"
        "  — <code>ختمت القرآن</code> — حفظت القرآن كاملاً\n"
        "  — <code>0</code> — لم أحفظ شيئاً بعد، ابدأ من الصفحة 1\n\n"
        "💡 <i>بعد إجابتك سأحسب لكِ الحصون الخمسة فوراً:</i>\n"
        "  🆕 الحفظ الجديد (صفحتان بعد آخر محفوظ)\n"
        "  🔄 مراجعة القريب (آخر 20 صفحة محفوظة)\n"
        "  🛡️ مراجعة البعيد (آخر 40 صفحة محفوظة)\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🌙 <i>أعانك الله وثبّت حفظك</i>"
    )
    if update.message:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=onboarding_question_keyboard(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=onboarding_question_keyboard(),
            disable_web_page_preview=True,
        )


# ====== الأمر /start ======

async def start_command(update, context):
    user_info = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, user_info.id, user_info.username, user_info.full_name)
        needs_onboarding = not user.onboarding_done

        if not needs_onboarding:
            # مُستخدمة قد أكملت التهيئة — نُحييها ونعرض لها مهام اليوم
            await update.message.reply_text(
                f"👋 <b>أهلاً بعودتك، {esc(user_info.first_name or 'أختي')}</b>! 🌟\n"
                "إليكِ <b>مهام اليوم</b> 👇",
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
                disable_web_page_preview=True,
            )
            await _show_today(update, context)
            return

    # مستخدمة جديدة — نطرح سؤال التهيئة
    await ask_onboarding_question(update, context, welcome=True)


# ====== معالج النص الحر والإجابات التفاعلية ======

async def handle_free_text(update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # لو النص يطابق أحد أزرار لوحة المفاتيح الثابتة — نُحوّله إلى الأمر المناسب
    if text in KEYBOARD_TEXT_MAP:
        command = KEYBOARD_TEXT_MAP[text]
        if command == "today":
            await _show_today(update, context)
        elif command == "fortresses":
            await fortresses_command(update, context)
        elif command == "progress":
            await progress_command(update, context)
        elif command == "help":
            await help_command(update, context)
        elif command == "update_memorized":
            await update_command(update, context)
        return

    # لو المستخدمة في وضع التهيئة — نعالج إجابتها
    if ONBOARDING_STATE.get(user_id) != "waiting_for_memorization":
        # نص حر غير مرتبط بأمر — نُظهر لها القائمة الرئيسية
        await update.message.reply_text(
            "💡 <b>اضغطي أحد أزرار القائمة في الأسفل</b>\n\n"
            "أو استخدمي الأوامر:\n"
            "• <code>/today</code> — مهام اليوم\n"
            "• <code>/fortresses</code> — الحصون الخمسة\n"
            "• <code>/update سورة المائدة</code> — تحديث آخر صفحة محفوظة",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
        return

    # معالجة إجابة التهيئة كنص حر
    await _process_onboarding_answer(update, context, text)


async def _process_onboarding_answer(update, context, text):
    """يعالج إجابة المستخدمة في وضع التهيئة ويُحدّث المحفوظ ثم يعرض الحصون."""
    user_id = update.effective_user.id
    parsed = await parse_memorization_input(text)

    # لو لم يفهم الإدخال ولم يكن "0" أو "لا شيء"
    if parsed["page"] is None and "0" not in text and "لا شيء" not in text.lower() and "ما حفظت" not in text.lower():
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
            # لم تحفظ شيئاً — ابدأ من الصفحة 1
            user.current_page = 1
            user.start_page = 1
            user.last_memorized_page = 0
            user.total_memorized = 0
            user.onboarding_done = True
            await session.commit()
            ONBOARDING_STATE.pop(user_id, None)
            await update.message.reply_text(
                "✅ <b>تمّ الضبط!</b> 🌱\n\n"
                "📖 ستبدئين من <b>الصفحة 1</b> (سورة الفاتحة)\n\n"
                "━━━━━━━━━━━━━━━━\n"
                "💎 <b>نصيحة البداية:</b>\n"
                "• ابدئي بقراءة الصفحة 3 مرات\n"
                "• استمعي إليها من قارئ متقن\n"
                "• كرّري الآيات حتى تطمئنّي\n"
                "• ثم احفظيها كتابياً وشفاهاً\n\n"
                "━━━━━━━━━━━━━━━━\n"
                "اضغطي <b>📋 مهام اليوم</b> في الأسفل لمهامك 📝",
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
                disable_web_page_preview=True,
            )
            return

        # تسجيل الحفظ من first_p إلى page
        await set_memorized_up_to(session, user, page, first_page=first_p)
        ONBOARDING_STATE.pop(user_id, None)
        await session.refresh(user)
        f = compute_fortresses(user)
        last_surah = quran_data.page_to_surah(f["last_memorized_page"])
        next_surah = quran_data.page_to_surah(f["next_memorize_page"])
        first_surah = quran_data.page_to_surah(f["first_memorized_page"])

        if first_p > 1:
            range_msg = f"من <b>الصفحة {first_p}</b> ({esc(first_surah.name_ar)}) إلى <b>الصفحة {page}</b> ({esc(last_surah.name_ar)})"
        else:
            range_msg = f"حتى <b>الصفحة {page}</b> (سورة {esc(last_surah.name_ar)})"

        await update.message.reply_text(
            f"✅ <b>ما شاء الله! تبارك الرحمن</b> 🎉\n\n"
            f"سجّلت أنك حفظتِ {range_msg}\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📊 <b>حسابات الحصون الخمسة:</b>\n\n"
            f"🆕 <b>الحفظ الجديد:</b> صفحة <b>{f['next_memorize_page']}</b> — سورة {esc(next_surah.name_ar)}\n"
            f"🔄 <b>مراجعة القريب</b> (آخر 20 صفحة): {f['near_start']}–{f['near_end']}\n"
            f"🛡️ <b>مراجعة البعيد</b> (آخر 40 صفحة): {f['far_start']}–{f['far_end']}\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "💡 <i>اضغطي <b>📋 مهام اليوم</b> في الأسفل لمعرفة تفاصيل كل مهمة</i>\n"
            "🌙 <i>أعانك الله ويسّر لكِ حفظ كتابه</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )


# ====== مهام اليوم ======

async def _show_today(update, context):
    """يعرض تفاصيل مهام اليوم مع شرح كل مهمة."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            await ask_onboarding_question(update, context, welcome=False)
            return

        progress = await get_or_create_progress(session, user.id)
        r_start, r_end = get_morning_reading_pages(user)
        l_start, l_end = get_midday_listening_pages(user)
        f = compute_fortresses(user)
        memo_page = f["next_memorize_page"]
        memo_surah = quran_data.page_to_surah(memo_page)
        juz = quran_data.page_to_juz(r_start)
        today_str = date.today().strftime("%Y-%m-%d")

    today_date_esc = esc(today_str)
    r_done = "✅" if progress.reading_done else "⬜"
    l_done = "✅" if progress.listening_done else "⬜"
    m_done = "✅" if progress.memorize_done else "⬜"

    # حساب رقم اليوم في السنة (للعرض فقط)
    day_of_year = date.today().timetuple().tm_yday
    text = (
        f"📋 <b>مهام اليوم — {today_date_esc}</b>\n"
        f"📅 اليوم رقم <b>{day_of_year}</b> في السنة\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"🌅 <b>1. الصباح — القراءة (الحصن الأول)</b>\n"
        f"{r_done} قراءة <b>حزبين (20 صفحة)</b>: <b>{r_start}–{r_end}</b>\n"
        f"📖 الجزء <b>{juz}</b>\n"
        f"💡 <i>القراءة تبدأ من صفحة حفظك القادمة ({r_start}) — تهيّج قلبك لتلقّي ما ستحفظينه قريباً.</i>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"☀️ <b>2. الظهيرة — الاستماع (من الحصن الأول)</b>\n"
        f"{l_done} استماع <b>حزب (10 صفحات)</b>: <b>{l_start}–{l_end}</b>\n"
        f"💡 <i>الاستماع للصفحات التي ستحفظينها لاحقاً — ترسيخ سمعي قبل الحفظ. استمعي 3 مرات (تأمّل + متابعة + تكرار بصوت منخفض).</i>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "🏰 <b>3. الحصون الخمسة</b>\n\n"
    )

    if not f["has_memorized"]:
        # مستخدمة اختارت البداية من الصفر — لا يوجد محفوظ
        np1 = f["next_memorize_page"]  # = 1 عادةً
        np2 = min(np1 + 1, quran_data.TOTAL_PAGES)
        memo_surah_zero = quran_data.page_to_surah(np1)
        text += (
            f"🌱 <b>أنتِ في مرحلة البداية — لم تحفظي شيئاً بعد</b>\n"
            f"هذا لا بأس به! كل حافظة بدأت من الصفر.\n\n"
            f"🆕 <b>الحفظ الجديد (الحصن الثالث):</b> ابدئي من <b>الصفحة {np1}</b> — سورة {esc(memo_surah_zero.name_ar)}\n"
            f"💡 <i>اقرئي الصفحتين ({np1}–{np2}) 3 مرات، استمعي إليهما، ثم احفظي آية آية.</i>\n\n"
            f"🔄 <b>مراجعة القريب (الحصن الرابع):</b> لا ينطبق الآن (لم تحفظي شيئاً)\n"
            f"🛡️ <b>مراجعة البعيد (الحصن الخامس):</b> لا ينطبق الآن (لم تحفظي شيئاً)\n\n"
            f"<i>بعد حفظ أول صفحة، احفظيها في البوت بـ <code>/markdone memorize</code> ليبدأ حساب المراجعات.</i>\n\n"
        )
    else:
        # الحفظ الجديد
        np1 = f["next_memorize_page"]
        np2 = min(np1 + 1, quran_data.TOTAL_PAGES)
        if np1 >= quran_data.TOTAL_PAGES:
            new_text = "🎉 وصلتِ لنهاية المصحف! راجعي وثبّتي محفوظك."
        else:
            new_text = (
                f"{m_done} صفحتان: <b>{np1}–{np2}</b> — سورة {esc(memo_surah.name_ar)}\n"
                f"💡 <i>اقرئي الصفحتين 3 مرات، استمعي إليهما، ثم احفظي آية آية.</i>"
            )
        text += (
            f"🆕 <b>الحفظ الجديد (الحصن الثالث)</b>\n"
            f"{new_text}\n\n"
            f"🔄 <b>مراجعة القريب (الحصن الرابع — آخر 20 صفحة محفوظة)</b>\n"
            f"• الصفحات <b>{f['near_start']}–{f['near_end']}</b>\n"
            f"💡 <i>راجعيها كاملة اليوم. اقرئيها من المصحف ثم من ذاكرتك.</i>\n\n"
            f"🛡️ <b>مراجعة البعيد (الحصن الخامس — آخر 40 صفحة محفوظة)</b>\n"
            f"• الصفحات <b>{f['far_start']}–{f['far_end']}</b>\n"
            f"💡 <i>قسّميها على فترات اليوم. الهدف التثبيت لا الإتقان الكامل.</i>\n\n"
        )

    text += (
        "━━━━━━━━━━━━━━━━\n"
        "✍️ <b>لتسجيل إنجاز اليوم:</b>\n"
        "• <code>/markdone reading</code> — قراءة الصباح\n"
        "• <code>/markdone listening</code> — استماع الظهيرة\n"
        "• <code>/markdone memorize</code> — حفظ اليوم\n"
        "• <code>/markdone daily_review</code> — المراجعة اليومية\n"
        "━━━━━━━━━━━━━━━━\n"
        "🤲 <i>تقبّل الله منكِ، وأعانك على ذكره وشكره وحسن عبادته</i>"
    )

    if update.message:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_inline(),
            disable_web_page_preview=True,
        )


async def today_command(update, context):
    await _show_today(update, context)


# ====== الحصون الخمسة (العرض التفصيلي) ======

async def fortresses_command(update, context):
    """عرض الحصون الخمسة بشرح كامل."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            await ask_onboarding_question(update, context, welcome=False)
            return
        f = compute_fortresses(user)

    if not f["has_memorized"]:
        np1 = f["next_memorize_page"]
        np_surah = quran_data.page_to_surah(np1)
        r_start, r_end = get_morning_reading_pages(user)
        l_start, l_end = get_midday_listening_pages(user)
        text = (
            "🏰 <b>الحصون الخمسة — مرحلة البداية</b>\n\n"
            "🌱 <b>أنتِ لم تحفظي شيئاً بعد</b>\n"
            "كل حافظة بدأت من الصفر، فلا تقلقي! إليكِ كيف ستعمل الحصون:\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "📖 <b>الحصن الأول — التهيئة المستمرة (شخصية لكل حافظة)</b>\n"
            f"• <b>القراءة اليوم:</b> الصفحات <b>{r_start}–{r_end}</b>\n"
            f"• <b>الاستماع اليوم:</b> الصفحات <b>{l_start}–{l_end}</b>\n"
            f"💡 <i>تبدأ القراءة من صفحة حفظك القادمة، والاستماع للصفحات التي ستحفظينها لاحقاً. كل حافظة لها صفحاتها الخاصة.</i>\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "📚 <b>الحصن الثاني — التحضير</b>\n"
            "• <b>التحضير الليلي:</b> قبل النوم، اقرئي صفحة الغد من المصحف فقط (دون حفظ)\n"
            f"💡 <i>الصفحة التي ستُحفظ غداً: <b>{np1}</b> — سورة {esc(np_surah.name_ar)}</i>\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🆕 <b>الحصن الثالث — الحفظ الجديد</b>\n"
            f"• ابدئي من <b>الصفحة {np1}</b> — سورة {esc(np_surah.name_ar)}\n"
            f"💡 <i>بعد الحفظ، سجّليه بـ <code>/markdone memorize</code> ليتقدّم البوت للصفحة التالية.</i>\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "🔄 <b>الحصن الرابع — مراجعة القريب (آخر 20 صفحة محفوظة)</b>\n"
            "⏸️ <i>لا ينطبق الآن — سيُفعَّل بعد حفظ صفحتك الأولى</i>\n\n"
            "🛡️ <b>الحصن الخامس — مراجعة البعيد (آخر 40 صفحة محفوظة)</b>\n"
            "⏸️ <i>لا ينطبق الآن — سيُفعَّل بعد حفظ 20+ صفحة</i>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🤲 <i>ابدئي الآن بقراءة الصفحة 1 ثم احفظيها، وستتقدّمين بحول الله</i>"
        )
    else:
        first_surah = quran_data.page_to_surah(f["first_memorized_page"])
        last_surah = quran_data.page_to_surah(f["last_memorized_page"])
        near_surah_start = quran_data.page_to_surah(f["near_start"])
        near_surah_end = quran_data.page_to_surah(f["near_end"])
        far_surah_start = quran_data.page_to_surah(f["far_start"])
        far_surah_end = quran_data.page_to_surah(f["far_end"])
        next_surah = quran_data.page_to_surah(f["next_memorize_page"])

        r_start, r_end = get_morning_reading_pages(user)
        l_start, l_end = get_midday_listening_pages(user)

        text = (
            "🏰 <b>الحصون الخمسة لحفظ القرآن</b>\n\n"
            f"📍 <b>المحفوظ الحالي:</b> من <b>الصفحة {f['first_memorized_page']}</b> إلى <b>{f['last_memorized_page']}</b>\n"
            f"📖 السور: {esc(first_surah.name_ar)} ← {esc(last_surah.name_ar)}\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
        )

        # الحصن الأول
        text += (
            "📖 <b>الحصن الأول — التهيئة المستمرة (شخصية لكل حافظة)</b>\n"
            f"• <b>القراءة:</b> جزآن يومياً (الصفحات <b>{r_start}–{r_end}</b>)\n"
            f"• <b>الاستماع:</b> حزب يومياً (الصفحات <b>{l_start}–{l_end}</b>)\n"
            f"💡 <i>تبدأ القراءة من صفحة حفظك القادمة ({r_start})، والاستماع للصفحات اللاحقة ({l_start}+). كل حافظة لها صفحاتها الخاصة حسب تقدّمها.</i>\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
        )

        # الحصن الثاني
        text += (
            "📚 <b>الحصن الثاني — التحضير</b>\n"
            "• <b>التحضير الأسبوعي:</b> قراءة حفظ الأسبوع القادم قبل دخوله\n"
            "• <b>التحضير الليلي:</b> قراءة حفظ اليوم التالي قبل النوم\n"
            "• <b>التحضير القبلي:</b> قراءة الدرس قبل الحفظ مباشرة\n"
            f"💡 <i>الهدف: لا يأتي الحفظ غريباً على الذهن. سبق الإلمام يُقلّل المقاومة النفسية ويُسهّل التثبيت.</i>\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
        )

        # الحصن الثالث
        text += "🆕 <b>الحصن الثالث — الحفظ الجديد</b>\n"
        if f["next_memorize_page"] >= quran_data.TOTAL_PAGES:
            text += "🎉 <b>وصلتِ إلى نهاية المصحف!</b> راجعي وثبّتي محفوظك، فالختم لا يكتمل إلا بالمراجعة.\n\n"
        else:
            np1 = f["next_memorize_page"]
            np2 = min(np1 + 1, quran_data.TOTAL_PAGES)
            text += (
                f"• <b>صفحتان:</b> <b>{np1}–{np2}</b>\n"
                f"📖 السورة: {esc(next_surah.name_ar)}\n"
                f"💡 <i>طريقة الحفظ: اقرئي كل آية 10 مرات، ثم اربطي الآيات حتى تُحفظ الصفحة كاملة. لا تنتقلي لصفحة جديدة حتى تُتقني الحالية تماماً.</i>\n\n"
                "━━━━━━━━━━━━━━━━\n\n"
            )

        # الحصن الرابع
        text += (
            "🔄 <b>الحصن الرابع — مراجعة القريب (آخر 20 صفحة محفوظة)</b>\n"
            f"• الصفحات <b>{f['near_start']}–{f['near_end']}</b>\n"
            f"📖 السور: {esc(near_surah_start.name_ar)} ← {esc(near_surah_end.name_ar)}\n"
            f"💡 <i>تُراجع يومياً كاملة. هذا أقوى الحصون ضد النسيان لأنه يُثبّت المحفوظ الحديث.</i>\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
        )

        # الحصن الخامس
        text += (
            "🛡️ <b>الحصن الخامس — مراجعة البعيد (آخر 40 صفحة محفوظة)</b>\n"
            f"• الصفحات <b>{f['far_start']}–{f['far_end']}</b>\n"
            f"📖 السور: {esc(far_surah_start.name_ar)} ← {esc(far_surah_end.name_ar)}\n"
            f"💡 <i>تُراجع على مدار الأسبوع (يمكن تقسيمها على أيام الأسبوع). الهدف التذكير لا الإتقان التام.</i>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🤲 <i>اللهم اجعل القرآن ربيع قلوبنا ونور صدورنا</i>"
        )

    if update.message:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_inline(),
            disable_web_page_preview=True,
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

    total = quran_data.TOTAL_PAGES
    percent = (count / total) * 100 if total > 0 else 0
    bar = progress_bar(count, total, 20)
    remaining = total - count
    months = remaining // 30 if count > 0 else 0

    recent = history[-5:]
    recent_text = ""
    for m in reversed(recent):
        surah = quran_data.page_to_surah(m.page_number)
        recent_text += f"• صفحة {esc(m.page_number)} ({esc(surah.name_ar)}) — {esc(m.date_memorized)}\n"

    percent_str = f"{percent:.1f}"
    text = (
        f"📊 <b>تقدّمك في حفظ القرآن</b>\n\n"
        f"<code>{bar}</code>\n"
        f"📖 المحفوظ: <b>{count} / {total}</b> صفحة ({esc(percent_str)}%)\n"
        f"⏳ المتبقي: <b>{remaining}</b> صفحة (~{months} شهر)\n\n"
        f"📍 الصفحة الحالية: <b>{user.current_page}</b>\n\n"
    )
    if recent_text:
        text += f"📋 <b>آخر 5 صفحات محفوظة:</b>\n{recent_text}\n"
    text += (
        "━━━━━━━━━━━━━━━━\n"
        "💡 <i>الاستمرار سرّ النجاح. ولو حفظتِ صفحة واحدة يومياً، ستنهين القرآن خلال 20 شهراً فقط بإذن الله.</i>\n"
        "🤲 <i>اللهم اجعلنا من أهل القرآن الذين هم أهل لك وخاصتك</i>"
    )

    if update.message:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_inline(),
            disable_web_page_preview=True,
        )


# ====== /update — تحديث آخر صفحة محفوظة ======

async def update_command(update, context):
    """يُعيد تحديث آخر صفحة محفوظة ثم يُعيد حساب الحصون.
    يدعم نفس صيغ /start: صفحة X، سورة Y، جزء Z، ختمت القرآن، 0.
    مثال: /update سورة المائدة
    """
    if not context.args:
        text = (
            "🔄 <b>تحديث آخر صفحة محفوظة</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "استخدمي إحدى الصيغ التالية:\n\n"
            "• <code>/update صفحة 127</code>\n"
            "• <code>/update سورة المائدة</code>\n"
            "• <code>/update جزء 7</code>\n"
            "• <code>/update ختمت القرآن</code>\n"
            "• <code>/update 0</code> (إعادة من البداية)\n\n"
            "💡 <i>سيُعاد حساب الحصون تلقائياً بناءً على آخر محفوظ جديد</i>\n"
            "━━━━━━━━━━━━━━━━"
        )
        if update.message:
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
                disable_web_page_preview=True,
            )
        elif update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_inline(),
                disable_web_page_preview=True,
            )
        return

    text_input = " ".join(context.args)
    parsed = await parse_memorization_input(text_input)
    if parsed["page"] is None and "0" not in text_input:
        if update.message:
            await update.message.reply_text(
                "❌ <b>لم أفهم الإدخال</b> 😅\nجرّب: <code>/update سورة المائدة</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
                disable_web_page_preview=True,
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
                "✅ <b>تمّت الإعادة من البداية</b> 🌱\n📖 ستبدئين من الصفحة 1 (سورة الفاتحة)",
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
                disable_web_page_preview=True,
            )
        else:
            await set_memorized_up_to(session, user, page, first_page=parsed.get("first_page"))
            await session.refresh(user)
            f = compute_fortresses(user)
            last_surah = quran_data.page_to_surah(f["last_memorized_page"])
            await update.message.reply_text(
                f"✅ <b>تمّ التحديث!</b> 🎉\n\n"
                f"آخر صفحة محفوظة: <b>{f['last_memorized_page']}</b> (سورة {esc(last_surah.name_ar)})\n\n"
                "━━━━━━━━━━━━━━━━\n"
                "📊 <b>الحصون بعد التحديث:</b>\n\n"
                f"🆕 الحفظ الجديد: صفحة <b>{f['next_memorize_page']}</b>\n"
                f"🔄 مراجعة القريب: <b>{f['near_start']}–{f['near_end']}</b>\n"
                f"🛡️ مراجعة البعيد: <b>{f['far_start']}–{f['far_end']}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
                disable_web_page_preview=True,
            )


# ====== /setpage ======

async def setpage_command(update, context):
    """يحدّث صفحة الحفظ الحالية ويُعيد حساب الحصون."""
    if not context.args:
        await update.message.reply_text(
            "❌ استخدمي: <code>/setpage 25</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
        return
    try:
        page = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ رقم غير صحيح",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )
        return
    if page < 1 or page > quran_data.TOTAL_PAGES:
        await update.message.reply_text(
            f"❌ الصفحة بين 1 و {quran_data.TOTAL_PAGES}",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )
        return
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        user.current_page = page
        user.onboarding_done = True
        if page > getattr(user, "last_memorized_page", 0):
            user.last_memorized_page = max(1, page - 1)
        await session.commit()
        await session.refresh(user)
        f = compute_fortresses(user)
    surah = quran_data.page_to_surah(page)
    await update.message.reply_text(
        f"✅ صفحتك الحالية: <b>{page}</b>\n📖 السورة: {esc(surah.name_ar)}\n\n"
        f"🔄 مراجعة القريب: <b>{f['near_start']}–{f['near_end']}</b>\n"
        f"🛡️ مراجعة البعيد: <b>{f['far_start']}–{f['far_end']}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


# ====== /markdone ======

async def markdone_command(update, context):
    if not context.args:
        await update.message.reply_text(
            "❌ <b>استخدمي:</b>\n"
            "• <code>/markdone reading</code> — تسجيل قراءة الصباح\n"
            "• <code>/markdone listening</code> — تسجيل استماع الظهيرة\n"
            "• <code>/markdone memorize</code> — تسجيل حفظ اليوم\n"
            "• <code>/markdone daily_review</code> — تسجيل المراجعة اليومية\n"
            "• <code>/markdone weekly &lt;page&gt;</code> — تسجيل مراجعة أسبوعية لصفحة محددة",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
        return
    task = context.args[0].lower()
    label = None
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if task == "reading":
            await mark_progress_done(session, user.id, "reading"); label = "قراءة الصباح"
        elif task == "listening":
            await mark_progress_done(session, user.id, "listening"); label = "استماع الظهيرة"
        elif task == "memorize":
            await mark_progress_done(session, user.id, "memorize")
            await mark_memorized(session, user, user.current_page); label = "حفظ اليوم"
        elif task == "daily_review":
            await mark_progress_done(session, user.id, "daily_review"); label = "المراجعة اليومية"
        elif task == "weekly" and len(context.args) >= 2:
            try:
                page = int(context.args[1])
            except ValueError:
                await update.message.reply_text(
                    "❌ رقم الصفحة غير صحيح",
                    parse_mode=ParseMode.HTML,
                    reply_markup=main_keyboard(),
                )
                return
            weekly_today = await get_today_weekly_review(session, user.id)
            done = False
            for wr in weekly_today:
                if wr["page"] == page:
                    await mark_weekly_review_done(session, wr["review_id"], wr["done_field"])
                    done = True; break
            if not done:
                await update.message.reply_text(
                    f"❌ لا مراجعة مستحقة اليوم للصفحة {page}",
                    parse_mode=ParseMode.HTML,
                    reply_markup=main_keyboard(),
                )
                return
            label = f"مراجعة الصفحة {page}"
        else:
            await update.message.reply_text(
                "❌ نوع غير معروف",
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
            )
            return
    await update.message.reply_text(
        f"✅ <b>أحسنتِ! ما شاء الله</b> 🎉\n"
        f"تم تسجيل <b>{esc(label)}</b>\n"
        "🤲 <i>تقبّل الله منكِ، وزادكِ منه خيراً</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


# ====== /settime ======

async def settime_command(update, context):
    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ استخدمي: <code>/settime morning 08:00</code>\n"
            "أو: <code>/settime midday 13:00</code>\n"
            "أو: <code>/settime evening 20:00</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
        return
    period, time_str = context.args
    period = period.lower()
    if period not in ("morning", "midday", "evening"):
        await update.message.reply_text(
            "❌ الفترة: morning أو midday أو evening",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
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
            reply_markup=main_keyboard(),
        )
        return
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if period == "morning": user.morning_time = time_str
        elif period == "midday": user.midday_time = time_str
        else: user.evening_time = time_str
        await session.commit()
    labels = {"morning": "الصباح", "midday": "الظهيرة", "evening": "المساء"}
    await update.message.reply_text(
        f"✅ تحديث وقت <b>{labels[period]}</b>: <code>{esc(time_str)}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


# ====== /timezone ======

async def timezone_command(update, context):
    if not context.args:
        await update.message.reply_text(
            "❌ استخدمي: <code>/timezone Africa/Algiers</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
        return
    tz = context.args[0]
    try:
        import pytz; pytz.timezone(tz)
    except Exception:
        await update.message.reply_text(
            "❌ منطقة غير معروفة",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )
        return
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        user.timezone = tz
        await session.commit()
    await update.message.reply_text(
        f"✅ المنطقة الزمنية: <code>{esc(tz)}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


# ====== /reset ======

async def reset_command(update, context):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        await session.execute(Memorization.__table__.delete().where(Memorization.user_id == user.id))
        await session.execute(WeeklyReview.__table__.delete().where(WeeklyReview.user_id == user.id))
        await session.execute(MonthlyReview.__table__.delete().where(MonthlyReview.user_id == user.id))
        await session.execute(DailyProgress.__table__.delete().where(DailyProgress.user_id == user.id))
        user.current_page = 1; user.start_page = 1; user.last_memorized_page = 0
        user.total_memorized = 0; user.onboarding_done = False
        await session.commit()
    ONBOARDING_STATE.pop(update.effective_user.id, None)
    await update.message.reply_text(
        "✅ <b>تمت إعادة التهيئة</b>\n\n"
        "اكتبي /start لبدء التهيئة من جديد",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


# ====== /help ======

async def help_command(update, context):
    text = (
        "📖 <b>دليل بوت الحصون الخمسة</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🏰 <b>الحصون الخمسة (المنهجية):</b>\n\n"
        "1️⃣ <b>التهيئة المستمرة</b> — قراءة جزئين + استماع حزب يومياً\n"
        "   💡 تهيّج القلب وتُيسّر الحفظ\n\n"
        "2️⃣ <b>التحضير</b> — أسبوعي + ليلي + قبلي\n"
        "   💡 لا يأتي الحفظ غريباً على الذهن\n\n"
        "3️⃣ <b>الحفظ الجديد</b> — صفحتان بعد آخر محفوظ\n"
        "   💡 أُحفظي صفحة صفحة حتى الإتقان\n\n"
        "4️⃣ <b>مراجعة القريب</b> — آخر 20 صفحة محفوظة\n"
        "   💡 تُراجع يومياً كاملة\n\n"
        "5️⃣ <b>مراجعة البعيد</b> — آخر 40 صفحة محفوظة\n"
        "   💡 تُقسّم على أيام الأسبوع\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "⏰ <b>التذكيرات اليومية:</b>\n"
        "🌅 <b>08:00</b> — تذكير الصباح (القراءة + الحفظ)\n"
        "☀️ <b>13:00</b> — تذكير الظهيرة (الاستماع)\n"
        "🌙 <b>20:00</b> — سؤال مساء اليوم (هل أنهيتِ الحفظ؟)\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📋 <b>الأوامر المتاحة:</b>\n"
        "• <code>/start</code> — البدء أو إعادة التهيئة\n"
        "• <code>/today</code> — عرض مهام اليوم بالتفصيل\n"
        "• <code>/fortresses</code> — عرض الحصون الخمسة بشرح كامل\n"
        "• <code>/progress</code> — عرض نسبة تقدّمك في الحفظ\n"
        "• <code>/update &lt;صفحة X|سورة Y|جزء Z&gt;</code> — تحديث آخر صفحة محفوظة وإعادة حساب الحصون\n"
        "• <code>/setpage &lt;رقم&gt;</code> — ضبط الصفحة الحالية فقط\n"
        "• <code>/settime &lt;morning|midday|evening&gt; &lt;HH:MM&gt;</code> — ضبط أوقات التذكير\n"
        "• <code>/timezone &lt;region&gt;</code> — ضبط المنطقة الزمنية\n"
        "• <code>/markdone &lt;reading|listening|memorize|daily_review|weekly &lt;page&gt;&gt;</code> — تسجيل إنجاز\n"
        "• <code>/reset</code> — إعادة التهيئة الكاملة\n"
        "• <code>/help</code> — هذا الدليل\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💡 <b>أو استخدمي الأزرار في الأسفل للتنقّل السريع</b>\n"
        "🤲 <i>اللهم علّمنا ما ينفعنا وانفعنا بما علّمتنا</i>"
    )
    if update.message:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_inline(),
            disable_web_page_preview=True,
        )


# ====== معالج أزرار Inline ======

async def button_callback(update, context):
    """معالج موحّد لكل أزرار Inline."""
    query = update.callback_query
    # إجابة الاستعلام فوراً حتى لا يبقى الزر "loading"
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"تعذّر answer_callback_query: {e}")

    data = query.data or ""

    # أزرار التهيئة السريعة
    if data == "ob_0":
        await _process_onboarding_answer(update, context, "0")
        return
    if data == "ob_all":
        await _process_onboarding_answer(update, context, "ختمت القرآن")
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
            # لو تعذّر التعديل (نفس النص)، نُرسل رسالة جديدة
            pass
        return
    m = re.match(r"^ob_surah_(\d+)$", data)
    if m:
        surah_num = int(m.group(1))
        surah = quran_data.get_surah_by_number(surah_num)
        if surah:
            await _process_onboarding_answer(update, context, f"سورة {surah.name_ar}")
        return

    # أزرار القائمة الرئيسية
    if data == "today":
        await _show_today(update, context)
    elif data == "fortresses":
        await fortresses_command(update, context)
    elif data == "progress":
        await progress_command(update, context)
    elif data == "help":
        await help_command(update, context)
    elif data == "update_memorized":
        # نُظهر تعليمات /update داخل callback
        await update_command(update, context)
    elif data == "evening_yes":
        await evening_yes_callback(update, context)
    elif data == "evening_later":
        await evening_later_callback(update, context)
    else:
        # زر غير معروف — لا شيء
        logger.warning(f"callback_data غير معروف: {data}")


# ============== 6. المجدول ==============
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

scheduler = AsyncIOScheduler(timezone="UTC")


def _today_str() -> str:
    """تاريخ اليوم بصيغة نصية عادية (سيتعرّض لـ esc() لاحقاً)."""
    return date.today().strftime("%Y-%m-%d")


async def send_morning_message(bot, telegram_id):
    try:
        async with AsyncSessionLocal() as session:
            user = await get_or_create_user(session, telegram_id=telegram_id)
            if not user.onboarding_done: return
            r_start, r_end = get_morning_reading_pages(user)
            juz = quran_data.page_to_juz(r_start)
            today_memo = get_today_memorize_page(user)
            memo_surah = quran_data.page_to_surah(today_memo)
            f = compute_fortresses(user)
        text = (
            "🌅 <b>صباح الخير!</b>\n\n"
            f"📅 {_today_str()}\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"📖 <b>القراءة — حزبين (20 صفحة):</b>\n"
            f"الصفحات <b>{r_start}–{r_end}</b> (الجزء {juz})\n\n"
            f"✍️ <b>صفحة الحفظ اليوم:</b> <b>{today_memo}</b>\n"
            f"📖 سورة {esc(memo_surah.name_ar)}\n\n"
        )
        if f["has_memorized"]:
            text += (
                f"🔄 <b>مراجعة القريب:</b> <b>{f['near_start']}–{f['near_end']}</b>\n"
                f"🛡️ <b>مراجعة البعيد:</b> <b>{f['far_start']}–{f['far_end']}</b>\n\n"
            )
        text += (
            "━━━━━━━━━━━━━━━━\n"
            "💡 <i>ابدئي بقراءة الصفحة 3 مرات قبل الحفظ</i>\n"
            f"بعد الإنهاء: <code>/markdone reading</code>"
        )
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"خطأ في رسالة الصباح لـ {telegram_id}: {e}")


async def send_midday_message(bot, telegram_id):
    try:
        async with AsyncSessionLocal() as session:
            user = await get_or_create_user(session, telegram_id=telegram_id)
            if not user.onboarding_done: return
            l_start, l_end = get_midday_listening_pages(user)
            today_memo = get_today_memorize_page(user)
            audio_url = quran_data.get_page_audio_url(today_memo)
        text = (
            "☀️ <b>وقت الاستماع!</b>\n\n"
            f"📅 {_today_str()}\n\n"
            f"🎧 <b>استماع لحزب (10 صفحات):</b>\n"
            f"الصفحات <b>{l_start}–{l_end}</b>\n\n"
        )
        if audio_url:
            text += f'🔊 <a href="{esc(audio_url)}">استمعي بصوت الحصري</a>\n\n'
        text += (
            "💡 <b>نصيحة الاستماع:</b>\n"
            "• استمعي للتأمّل والتدبّر\n"
            "• كرّري الاستماع 3 مرات\n"
            "• اقرئي بصوت منخفض مع القارئ\n\n"
            "بعد الإنهاء: <code>/markdone listening</code>"
        )
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"خطأ في رسالة الظهيرة لـ {telegram_id}: {e}")


async def send_evening_message(bot, telegram_id):
    try:
        async with AsyncSessionLocal() as session:
            user = await get_or_create_user(session, telegram_id=telegram_id)
            if not user.onboarding_done: return
            today_memo = get_today_memorize_page(user)
            progress = await get_or_create_progress(session, user.id)
            memo_surah = quran_data.page_to_surah(today_memo)
            weekly_today = await get_today_weekly_review(session, user.id)
            f = compute_fortresses(user)
        if not progress.memorize_done:
            text = (
                "🌙 <b>مساء الخير!</b>\n\n"
                f"📅 {_today_str()}\n\n"
                f"✍️ <b>صفحة الحفظ اليوم:</b> <b>{today_memo}</b>\n"
                f"📖 سورة {esc(memo_surah.name_ar)}\n\n"
                "<b>هل أنهيتِ حفظ صفحة اليوم؟</b>"
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ نعم، حفظتها", callback_data="evening_yes"),
                InlineKeyboardButton("⏳ لسه، أحتاج وقتاً", callback_data="evening_later"),
            ]])
            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        else:
            if weekly_today:
                text = "🌙 <b>مساء الخير!</b>\n\n✅ <b>أحسنتِ! تم الحفظ</b> 🎉\n\n<b>🔍 مراجعات مستحقة اليوم:</b>\n"
                for wr in weekly_today:
                    wr_surah = quran_data.page_to_surah(wr["page"])
                    text += f"• {esc(wr['label'])}: صفحة {wr['page']} ({esc(wr_surah.name_ar)})\n"
                text += "\n💡 <i>راجعيها قبل النوم — أقوى وقت للتثبيت</i>"
            else:
                text = "🌙 <b>مساء الخير!</b>\n\n✅ <b>أحسنتِ! تم الحفظ</b> 🎉\n🤲 <i>تقبّل الله منكِ</i>"
            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
    except Exception as e:
        logger.error(f"خطأ في رسالة المساء لـ {telegram_id}: {e}")


async def evening_yes_callback(update, context):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=update.effective_user.id)
        await mark_memorized(session, user, user.current_page)
        await mark_progress_done(session, user.id, "memorize")
        today_memo = get_today_memorize_page(user)
        next_page = user.current_page
        next_surah = quran_data.page_to_surah(next_page)
        weekly_today = await get_today_weekly_review(session, user.id)
    saved_page = today_memo - 1 if today_memo > 1 else 1
    text = (
        f"🎉 <b>ما شاء الله! تبارك الرحمن</b>\n"
        f"تم تسجيل حفظ صفحة <b>{saved_page}</b>\n\n"
        f"📍 <b>صفحة الغد:</b> <b>{next_page}</b>\n"
        f"📖 سورة {esc(next_surah.name_ar)}\n\n"
    )
    if weekly_today:
        text += "<b>🔍 مراجعات مستحقة:</b>\n"
        for wr in weekly_today:
            wr_surah = quran_data.page_to_surah(wr["page"])
            text += f"• {esc(wr['label'])}: صفحة {wr['page']} ({esc(wr_surah.name_ar)})\n"
        text += "\n💡 <code>/markdone weekly &lt;page&gt;</code>"
    else:
        text += "🤲 <i>تقبّل الله منكِ، وزادكِ منه خيراً</i>"
    try:
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_inline(),
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"تعذّر تعديل رسالة evening_yes: {e}")


async def evening_later_callback(update, context):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    try:
        await query.edit_message_text(
            "⏳ <b>لا بأس، خذي وقتك!</b>\n\n"
            "💡 <b>خطوات مساعدة:</b>\n"
            "• اقرئي الصفحة 3 مرات من المصحف\n"
            "• كرّري الآيات الصعبة 10 مرات\n"
            "• استمعي إليها من قارئ متقن\n"
            "• اكتبية على ورقة لتثبيتها\n\n"
            "بعد الإنهاء: <code>/markdone memorize</code>\n\n"
            "🤲 <i>أعانك الله ويسّر أمرك</i>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"تعذّر تعديل رسالة evening_later: {e}")


async def schedule_user_jobs(bot):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.is_active == True))
        users = list(result.scalars().all())
    for user in users:
        try:
            tz = pytz.timezone(user.timezone)
        except Exception:
            tz = pytz.timezone("Africa/Algiers")
        m_h, m_m = map(int, user.morning_time.split(":"))
        d_h, d_m = map(int, user.midday_time.split(":"))
        e_h, e_m = map(int, user.evening_time.split(":"))
        morning_id = f"morning_{user.telegram_id}"
        midday_id = f"midday_{user.telegram_id}"
        evening_id = f"evening_{user.telegram_id}"
        for jid in (morning_id, midday_id, evening_id):
            try: scheduler.remove_job(jid)
            except Exception: pass
        scheduler.add_job(send_morning_message, CronTrigger(hour=m_h, minute=m_m, timezone=tz), args=[bot, user.telegram_id], id=morning_id, replace_existing=True)
        scheduler.add_job(send_midday_message, CronTrigger(hour=d_h, minute=d_m, timezone=tz), args=[bot, user.telegram_id], id=midday_id, replace_existing=True)
        scheduler.add_job(send_evening_message, CronTrigger(hour=e_h, minute=e_m, timezone=tz), args=[bot, user.telegram_id], id=evening_id, replace_existing=True)
    logger.info(f"تمت جدولة {len(users)} مستخدمًا بـ 3 تذكيرات يومية")


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
        "status": "ok", "service": "quran-husun-bot",
        "timestamp": date.today().isoformat(),
    })


async def _root_handler(request):
    return web.Response(text="Quran Husun Bot is running ✅")


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
        logger.warning("keep-alive: URL غير مضبوط — الخدمة قد تنام"); return
    logger.info(f"keep-alive: ping كل {interval} ثانية إلى {url}")
    await asyncio.sleep(startup_delay)
    success_count = 0
    fail_count = 0
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
        except Exception as e:
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
    """يُستدعى داخل event loop الخاص بـ PTB بعد إنشاء التطبيق."""
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
                logger.info(f"✅ keep-alive نشط — self-ping كل {KEEPALIVE_INTERVAL} ثانية")
            else:
                logger.warning("⚠️ RENDER_EXTERNAL_URL غير مضبوط — الخدمة قد تنام")
        except Exception as e:
            logger.warning(f"⚠️ تعذّر بدء خادم keep-alive: {e} — يُتابع البوت بدون keep-alive")


async def post_shutdown(app):
    """ينظّف خادم keep-alive عند التوقف."""
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


async def _error_handler(update, context):
    """معالج أخطاء شامل.

    ملاحظة مهمة: BadRequest يرث من NetworkError في PTB، لذا نُميّز بينهما بعناية.
    - BadRequest (مثل أخطاء Markdown): نسجّلها ونُجيب الـ callback_query حتى لا يبقى الزر "loading"
    - Conflict (409): مثيلان من البوت (عند النشر) — تجاهل صامت
    - TimedOut/NetworkError الشبكي: تجاهل صامت
    """
    from telegram.error import (
        Conflict, NetworkError, TimedOut, Forbidden, BadRequest,
    )
    error = context.error

    # أخطاء عابرة — نتجاهلها بصمت
    if isinstance(error, Conflict):
        logger.warning(f"⚠️ Conflict (تجاهل صامت): {error}")
        # نُجيب callback_query حتى لا يبقى الزر معلّقاً
        if update and getattr(update, "callback_query", None):
            try: await update.callback_query.answer()
            except Exception: pass
        return

    if isinstance(error, TimedOut):
        logger.warning(f"⚠️ TimedOut (تجاهل صامت): {error}")
        return

    if isinstance(error, Forbidden):
        logger.warning(f"⚠️ المستخدم حظر البوت: {error}")
        return

    # BadRequest — خطأ فعلي في الطلب (عادةً مشكلة HTML أو نص)
    if isinstance(error, BadRequest):
        logger.error(f"❌ BadRequest: {error}", exc_info=False)
        # محاولة إرسال رسالة خطأ بسيطة للمستخدم
        if update and getattr(update, "effective_chat", None):
            try:
                # نُجيب callback_query أولاً
                if getattr(update, "callback_query", None):
                    try: await update.callback_query.answer()
                    except Exception: pass
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ حدث خطأ بسيط في تجهيز الرد. جرّبي مرة أخرى أو اضغطي /start",
                    reply_markup=main_keyboard(),
                )
            except Exception:
                pass
        return

    # NetworkError عامة (وليس BadRequest/Conflict/TimedOut)
    if isinstance(error, NetworkError):
        logger.warning(f"⚠️ خطأ شبكة (تجاهل صامت): {error}")
        return

    # خطأ غير متوقع — نسجّله بالتفصيل
    logger.error(f"❌ خطأ أثناء معالجة تحديث: {type(error).__name__}: {error}", exc_info=True)
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
    """يبني تطبيق PTB مع كل المعالجات ويربط post_init/post_shutdown."""
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
    app.add_handler(CommandHandler("setpage", setpage_command))
    app.add_handler(CommandHandler("update", update_command))
    app.add_handler(CommandHandler("markdone", markdone_command))
    app.add_handler(CommandHandler("settime", settime_command))
    app.add_handler(CommandHandler("timezone", timezone_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))
    # معالج أزرار Inline موحّد — يقبل كل callback_data ويتفرّع داخل button_callback
    app.add_handler(CallbackQueryHandler(button_callback))
    # معالج أخطاء شامل
    app.add_error_handler(_error_handler)
    return app


def main():
    """نقطة التشغيل الرئيسية — تستخدم run_polling المتزامنة الخاصة بـ PTB."""
    import traceback
    try:
        logger.info("📖 بوت الحصون الخمسة — البدء")
        logger.info(f"  - الصباح: {MORNING_TIME}")
        logger.info(f"  - الظهيرة: {MIDDAY_TIME}")
        logger.info(f"  - المساء: {EVENING_TIME}")
        logger.info(f"  - المنطقة الزمنية: {DEFAULT_TIMEZONE}")
        logger.info(f"  - keep-alive: {'مُفعّل' if KEEPALIVE_ENABLED else 'مُعطّل'}")
        logger.info(f"  - DATABASE_URL يبدأ بـ postgresql: {_is_postgres}")
        logger.info(f"  - BOT_TOKEN مضبوط: {bool(BOT_TOKEN)}")
        logger.info(f"  - ADMIN_ID: {ADMIN_ID}")
        logger.info(f"  - تنسيق الرسائل: HTML (بدل MarkdownV2)")

        app = build_application()
        logger.info("🚀 تشغيل البوت في وضع polling...")
        app.run_polling(poll_interval=3, drop_pending_updates=True, close_loop=False)
    except Exception as e:
        logger.error("❌ خطأ أثناء التشغيل:")
        logger.error(traceback.format_exc())
        print("❌ ERROR:", e, flush=True)
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        raise


if __name__ == "__main__":
    main()
