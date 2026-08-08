"""
بوت تلغرام لحفظ القرآن — طريقة الحصون الخمسة
============================================
ملف واحد يجمع: الإعدادات + قاعدة البيانات + النماذج + المنطق
              + المعالجات + المجدول + keep-alive + نقطة التشغيل

التشغيل: python bot.py
"""

# ============== 1. الإعدادات ==============
import os
import sys
import asyncio
import logging
import re
from datetime import date, timedelta

from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql://")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://") and "sslmode" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"
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
    func, UniqueConstraint, select, and_
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine
)


class Base(DeclarativeBase):
    pass


def _to_async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("file:"):
        url = url.replace("file:", "sqlite:///", 1)
    if not url.startswith("sqlite://"):
        url = "sqlite:///" + url.lstrip("/")
    if url.startswith("sqlite:///") and not url.startswith("sqlite+aiosqlite://"):
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


_is_postgres = DATABASE_URL.startswith("postgresql://")
_engine_kwargs = {"echo": False}
if _is_postgres:
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10

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
    text = text.strip()
    result = {"type": None, "value": None, "page": None, "raw": text}
    if "كل القرآن" in text or "كامل القرآن" in text or "ختمت" in text:
        result.update({"type": "all", "value": "all", "page": quran_data.TOTAL_PAGES})
        return result
    m = re.search(r"جزء\s*(\d+)", text)
    if m:
        juz = int(m.group(1))
        if 1 <= juz <= 30:
            start, end = quran_data.juz_pages(juz)
            result.update({"type": "juz", "value": juz, "page": end})
            return result
    m = re.search(r"سورة\s+(.+)", text)
    if m:
        surah = quran_data.get_surah_by_name(m.group(1).strip())
        if surah:
            if surah.number < 114:
                last_page = quran_data.get_surah_by_number(surah.number + 1).page_start - 1
            else:
                last_page = quran_data.TOTAL_PAGES
            result.update({"type": "surah", "value": surah.name_ar, "page": last_page})
            return result
    m = re.search(r"صفحة\s*(\d+)\s*[-–]\s*(\d+)", text)
    if m:
        start_p, end_p = int(m.group(1)), int(m.group(2))
        if 1 <= end_p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page_range", "value": (start_p, end_p), "page": end_p})
            return result
    m = re.search(r"صفحة\s*(\d+)", text)
    if m:
        p = int(m.group(1))
        if 1 <= p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page", "value": p, "page": p})
            return result
    m = re.match(r"^\s*(\d+)\s*$", text)
    if m:
        p = int(m.group(1))
        if 1 <= p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page", "value": p, "page": p})
            return result
    return result


async def set_memorized_up_to(session, user, page):
    await session.execute(Memorization.__table__.delete().where(Memorization.user_id == user.id))
    today = date.today()
    for p in range(1, page + 1):
        session.add(Memorization(user_id=user.id, page_number=p, date_memorized=today, review_count=5))
    user.current_page = page + 1 if page < quran_data.TOTAL_PAGES else quran_data.TOTAL_PAGES
    user.start_page = 1
    user.total_memorized = page
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


async def get_monthly_review(session, user_id, year, month):
    result = await session.execute(
        select(MonthlyReview).where(and_(MonthlyReview.user_id == user_id, MonthlyReview.year == year, MonthlyReview.month == month))
    )
    review = result.scalar_one_or_none()
    if review is None:
        start_date = date(year, month, 1)
        end_date = date(year + 1, 1, 1) - timedelta(days=1) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)
        pages_result = await session.execute(
            select(Memorization).where(and_(Memorization.user_id == user_id,
                Memorization.date_memorized >= start_date, Memorization.date_memorized <= end_date))
            .order_by(Memorization.page_number)
        )
        pages = [str(m.page_number) for m in pages_result.scalars().all()]
        review = MonthlyReview(user_id=user_id, year=year, month=month, pages_reviewed=",".join(pages))
        session.add(review)
        await session.commit()
        await session.refresh(review)
    return review


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
    day_of_year = date.today().timetuple().tm_yday
    start_page = ((day_of_year - 1) * 20 % quran_data.TOTAL_PAGES) + 1
    end_page = min(start_page + 19, quran_data.TOTAL_PAGES)
    return start_page, end_page


def get_midday_listening_pages(user):
    day_of_year = date.today().timetuple().tm_yday
    start_page = (((day_of_year + 5) * 10) % quran_data.TOTAL_PAGES) + 1
    end_page = min(start_page + 9, quran_data.TOTAL_PAGES)
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


# ============== 5. المعالجات (الأوامر) ==============
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

ONBOARDING_STATE = {}


def escape_md(text):
    for char in "_*[]()~`>#+-=|{}.!":
        text = text.replace(char, f"\\{char}")
    return text


def progress_bar(current, total, length=15):
    if total == 0: return "░" * length
    filled = int((current / total) * length)
    return "█" * filled + "░" * (length - filled)


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 مهام اليوم", callback_data="today"),
         InlineKeyboardButton("🏰 الحصون", callback_data="fortresses")],
        [InlineKeyboardButton("📊 تقدمي", callback_data="progress"),
         InlineKeyboardButton("⚙️ مساعدة", callback_data="settings")],
    ])


async def start_command(update, context):
    user_info = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, user_info.id, user_info.username, user_info.full_name)
        needs_onboarding = not user.onboarding_done
    if needs_onboarding:
        ONBOARDING_STATE[user_info.id] = "waiting_for_memorization"
        text = (
            "🤲 *بسم الله الرحمن الرحيم*\n\n"
            f"أهلاً *{escape_md(user.full_name or 'أختي الكريمة')}*\\!\n\n"
            "📖 *بوت الحصون الخمسة لحفظ القرآن*\n\n"
            "قبل البدء، أخبريني ماذا حفظت سابقاً لأحدد نقطة البداية:\n\n"
            "• `صفحة 50` — حفظت إلى صفحة 50\n"
            "• `جزء 3` — حفظت 3 أجزاء\n"
            "• `سورة الكهف` — حفظت حتى سورة الكهف\n"
            "• `ختمت القرآن` — حفظت القرآن كاملاً\n"
            "• `0` — تبدأ من الصفحة الأولى"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await _show_today(update, context)


async def handle_free_text(update, context):
    user_id = update.effective_user.id
    if ONBOARDING_STATE.get(user_id) != "waiting_for_memorization":
        return
    text = update.message.text.strip()
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=user_id)
        parsed = await parse_memorization_input(text)
        if parsed["page"] is None and "0" not in text and "لا شيء" not in text.lower():
            await update.message.reply_text(
                "❌ لم أفهم\\! جرّب:\n• `صفحة 50`\n• `جزء 3`\n• `سورة الكهف`\n• `ختمت القرآن`\n• `0`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        page = parsed["page"] or 0
        if page == 0:
            user.current_page = 1
            user.start_page = 1
            user.total_memorized = 0
            user.onboarding_done = True
            await session.commit()
            del ONBOARDING_STATE[user_id]
            await update.message.reply_text(
                "✅ *تمّ الضبط\\!*\n📖 ستبدئين من *الصفحة 1* \\(الفاتحة\\)\nاكتبي /today لمهامك",
                parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu(),
            )
        else:
            await set_memorized_up_to(session, user, page)
            del ONBOARDING_STATE[user_id]
            next_page = page + 1 if page < quran_data.TOTAL_PAGES else page
            surah = quran_data.page_to_surah(next_page)
            await update.message.reply_text(
                f"✅ *ما شاء الله\\!* سجّلت أنك حفظت إلى *الصفحة {page}*\n"
                f"📖 صفحتك التالية: *{next_page}* \\— سورة {escape_md(surah.name_ar)}\n\n"
                f"🌅 الصباح 08:00: قراءة حزبين\n☀️ الظهيرة 13:00: استماع حزب\n🌙 المساء 20:00: سؤال تفاعلي\n\n"
                f"اكتبي /today",
                parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu(),
            )


async def _show_today(update, context):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            await start_command(update, context)
            return
        progress = await get_or_create_progress(session, user.id)
        weekly_review = await get_today_weekly_review(session, user.id)
        r_start, r_end = get_morning_reading_pages(user)
        l_start, l_end = get_midday_listening_pages(user)
        memo_page = get_today_memorize_page(user)
        memo_surah = quran_data.page_to_surah(memo_page)
        juz = quran_data.page_to_juz(r_start)

    today_date = date.today().strftime("%Y-%m-%d")
    text = (
        f"📋 *مهام اليوم — {today_date}*\n\n"
        f"🌅 *الصباح \\- القراءة:*\n"
        f"{'✅' if progress.reading_done else '⬜'} حزبين \\(20 صفحة\\): {r_start}–{r_end}\n"
        f"📖 الجزء {juz}\n\n"
        f"☀️ *الظهيرة \\- الاستماع:*\n"
        f"{'✅' if progress.listening_done else '⬜'} حزب \\(10 صفحات\\): {l_start}–{l_end}\n\n"
        f"🏰 *الحصون الخمسة:*\n\n"
        f"1️⃣ *الحفظ اليومي*\n"
        f"{'✅' if progress.memorize_done else '⬜'} صفحة {memo_page} \\— سورة {escape_md(memo_surah.name_ar)}\n\n"
        f"2️⃣ *المراجعة اليومية*\n"
        f"{'✅' if progress.daily_review_done else '⬜'} صفحة {memo_page}\n\n"
    )
    if weekly_review:
        text += "4️⃣ *مراجعة أسبوعية مستحقة اليوم:*\n"
        for wr in weekly_review:
            wr_surah = quran_data.page_to_surah(wr["page"])
            text += f"   • {wr['label']}: صفحة {wr['page']} \\({escape_md(wr_surah.name_ar)}\\)\n"
        text += "\n"
    text += "💡 `/markdone reading|listening|memorize`"
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu(), disable_web_page_preview=True)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu(), disable_web_page_preview=True)


async def today_command(update, context):
    await _show_today(update, context)


async def fortresses_command(update, context):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        today_memo = get_today_memorize_page(user)
        today_review = await get_today_review_pages(session, user.id)
        weekly_pages = await get_weekly_review_pages(session, user.id)
        weekly_review = await get_today_weekly_review(session, user.id)
        now = date.today()
        monthly = await get_monthly_review(session, user.id, now.year, now.month)
    text = (
        "🏰 *طريقة الحصون الخمسة*\n\n━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ *الحفظ اليومي* \\(الحصن الأول\\)\n📄 صفحة اليوم: *{today_memo}*\n📖 سورة {escape_md(quran_data.page_to_surah(today_memo).name_ar)}\n\n"
        f"━━━━━━━━━━━━━━━━\n\n2️⃣ *المراجعة اليومية* \\(الحصن الثاني\\)\n"
    )
    if today_review:
        text += f"📄 راجعي: {escape_md(', '.join(map(str, today_review)))}\n\n"
    else:
        text += "📄 لم تحفظي شيئاً اليوم بعد\\.\n\n"
    text += f"━━━━━━━━━━━━━━━━\n\n3️⃣ *الحفظ الأسبوعي* \\(الحصن الثالث\\)\n📄 آخر 7 أيام: {len(weekly_pages)} صفحة\n\n"
    if weekly_pages:
        text += f"📋 {escape_md(', '.join(map(str, weekly_pages[:10])))}"
        if len(weekly_pages) > 10:
            text += f" \\(\\+{len(weekly_pages)-10} أخرى\\)"
        text += "\n\n"
    text += "━━━━━━━━━━━━━━━━\n\n4️⃣ *المراجعة الأسبوعية* \\(الحصن الرابع\\)\n📅 5 مواعيد: ليلة، ليل، ثلث، اربعاء، خميس\n\n"
    if weekly_review:
        text += "🔍 *مستحقة اليوم:*\n"
        for wr in weekly_review:
            wr_surah = quran_data.page_to_surah(wr["page"])
            text += f"   • {wr['label']}: صفحة {wr['page']} \\({escape_md(wr_surah.name_ar)}\\)\n"
        text += "\n"
    else:
        text += "✅ لا مراجعات مستحقة اليوم\\.\n\n"
    text += f"━━━━━━━━━━━━━━━━\n\n5️⃣ *المراجعة الشهرية* \\(الحصن الخامس\\)\n📅 {now.month}/{now.year}\n"
    if monthly and monthly.pages_reviewed:
        pages = monthly.pages_reviewed.split(",")
        text += f"📄 {len(pages)} صفحة محفوظة هذا الشهر"
    else:
        text += "📄 لم تحفظي شيئاً هذا الشهر\\."
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu(), disable_web_page_preview=True)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu(), disable_web_page_preview=True)


async def progress_command(update, context):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        count = await count_memorized(session, user.id)
        history = await get_memorization_history(session, user.id)
    total = quran_data.TOTAL_PAGES
    percent = (count / total) * 100
    bar = progress_bar(count, total, 20)
    remaining = total - count
    months = remaining // 30 if count > 0 else 0
    recent = history[-5:]
    recent_text = ""
    for m in reversed(recent):
        surah = quran_data.page_to_surah(m.page_number)
        recent_text += f"• صفحة {m.page_number} \\({escape_md(surah.name_ar)}\\) — {m.date_memorized}\n"
    text = (
        f"📊 *تقدمك في حفظ القرآن*\n\n`{bar}`\n"
        f"📖 المحفوظ: *{count} / {total}* صفحة \\({percent:.1f}%\\)\n"
        f"⏳ المتبقي: *{remaining}* صفحة \\(~{months} شهر\\)\n\n"
        f"📍 الصفحة الحالية: *{user.current_page}*\n\n"
    )
    if recent_text:
        text += f"📋 *آخر 5 صفحات:*\n{recent_text}"
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu())


async def setpage_command(update, context):
    if not context.args:
        await update.message.reply_text("❌ استخدمي: `/setpage 25`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    try:
        page = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ رقم غير صحيح")
        return
    if page < 1 or page > quran_data.TOTAL_PAGES:
        await update.message.reply_text(f"❌ الصفحة بين 1 و {quran_data.TOTAL_PAGES}")
        return
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        user.current_page = page
        user.onboarding_done = True
        await session.commit()
    surah = quran_data.page_to_surah(page)
    await update.message.reply_text(
        f"✅ صفحتك الحالية: *{page}*\n📖 السورة: {surah.name_ar}",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def markdone_command(update, context):
    if not context.args:
        await update.message.reply_text(
            "❌ استخدمي:\n• `/markdone reading`\n• `/markdone listening`\n• `/markdone memorize`\n• `/markdone daily_review`\n• `/markdone weekly <page>`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    task = context.args[0].lower()
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if task == "reading":
            await mark_progress_done(session, user.id, "reading"); label = "القراءة"
        elif task == "listening":
            await mark_progress_done(session, user.id, "listening"); label = "الاستماع"
        elif task == "memorize":
            await mark_progress_done(session, user.id, "memorize")
            await mark_memorized(session, user, user.current_page); label = "الحفظ"
        elif task == "daily_review":
            await mark_progress_done(session, user.id, "daily_review"); label = "المراجعة اليومية"
        elif task == "weekly" and len(context.args) >= 2:
            try:
                page = int(context.args[1])
            except ValueError:
                await update.message.reply_text("❌ رقم الصفحة غير صحيح"); return
            weekly_today = await get_today_weekly_review(session, user.id)
            done = False
            for wr in weekly_today:
                if wr["page"] == page:
                    await mark_weekly_review_done(session, wr["review_id"], wr["done_field"])
                    done = True; break
            if not done:
                await update.message.reply_text(f"❌ لا مراجعة مستحقة اليوم للصفحة {page}"); return
            label = f"مراجعة الصفحة {page}"
        else:
            await update.message.reply_text("❌ نوع غير معروف"); return
    await update.message.reply_text(
        f"✅ *أحسنت\\!* تم تسجيل *{escape_md(label)}*\n🤲 تقبل الله منك",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def settime_command(update, context):
    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ استخدمي: `/settime morning 08:00`\nأو: `/settime midday 13:00`\nأو: `/settime evening 20:00`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    period, time_str = context.args
    period = period.lower()
    if period not in ("morning", "midday", "evening"):
        await update.message.reply_text("❌ الفترة: morning/midday/evening", parse_mode=ParseMode.MARKDOWN_V2); return
    try:
        h, m = map(int, time_str.split(":"))
        if not (0 <= h < 24 and 0 <= m < 60): raise ValueError
        time_str = f"{h:02d}:{m:02d}"
    except (ValueError, IndexError):
        await update.message.reply_text("❌ الوقت بصيغة HH:MM"); return
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if period == "morning": user.morning_time = time_str
        elif period == "midday": user.midday_time = time_str
        else: user.evening_time = time_str
        await session.commit()
    labels = {"morning": "الصباح", "midday": "الظهيرة", "evening": "المساء"}
    await update.message.reply_text(
        f"✅ تحديث وقت *{labels[period]}*: `{time_str}`",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def timezone_command(update, context):
    if not context.args:
        await update.message.reply_text(
            "❌ استخدمي: `/timezone Africa/Algiers`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    tz = context.args[0]
    try:
        import pytz; pytz.timezone(tz)
    except Exception:
        await update.message.reply_text("❌ منطقة غير معروفة"); return
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        user.timezone = tz
        await session.commit()
    await update.message.reply_text(f"✅ المنطقة الزمنية: `{tz}`", parse_mode=ParseMode.MARKDOWN_V2)


async def reset_command(update, context):
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        await session.execute(Memorization.__table__.delete().where(Memorization.user_id == user.id))
        await session.execute(WeeklyReview.__table__.delete().where(WeeklyReview.user_id == user.id))
        await session.execute(MonthlyReview.__table__.delete().where(MonthlyReview.user_id == user.id))
        await session.execute(DailyProgress.__table__.delete().where(DailyProgress.user_id == user.id))
        user.current_page = 1; user.start_page = 1; user.total_memorized = 0; user.onboarding_done = False
        await session.commit()
    ONBOARDING_STATE.pop(update.effective_user.id, None)
    await update.message.reply_text("✅ تمت إعادة التهيئة\\.\nاكتبي /start", parse_mode=ParseMode.MARKDOWN_V2)


async def help_command(update, context):
    text = (
        "📖 *دليل بوت الحصون الخمسة*\n\n"
        "🏰 *الحصون الخمسة:*\n"
        "1️⃣ الحفظ اليومي — صفحة جديدة\n"
        "2️⃣ المراجعة اليومية — ما حُفظ اليوم\n"
        "3️⃣ الحفظ الأسبوعي — آخر 7 أيام\n"
        "4️⃣ المراجعة الأسبوعية — 5 مواعيد\n"
        "5️⃣ المراجعة الشهرية\n\n"
        "⏰ *التذكيرات:*\n"
        "🌅 08:00 — قراءة حزبين\n"
        "☀️ 13:00 — استماع حزب\n"
        "🌙 20:00 — سؤال تفاعلي\n\n"
        "📋 *الأوامر:*\n"
        "/start — البدء\n"
        "/today — مهام اليوم\n"
        "/fortresses — الحصون\n"
        "/progress — تقدمك\n"
        "/setpage <رقم>\n"
        "/settime <morning|midday|evening> <HH:MM>\n"
        "/timezone <region>\n"
        "/markdone <reading|listening|memorize|daily_review|weekly <page>>\n"
        "/reset — إعادة التهيئة\n"
        "/help — هذا الدليل"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


async def button_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "today": await _show_today(update, context)
    elif data == "fortresses": await fortresses_command(update, context)
    elif data == "progress": await progress_command(update, context)
    elif data == "settings": await help_command(update, context)


# ============== 6. المجدول ==============
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

scheduler = AsyncIOScheduler(timezone="UTC")
DATE_FMT = "%Y-%m-%d"


def _today_str():
    return date.today().strftime(DATE_FMT)


async def send_morning_message(bot, telegram_id):
    try:
        async with AsyncSessionLocal() as session:
            user = await get_or_create_user(session, telegram_id=telegram_id)
            if not user.onboarding_done: return
            r_start, r_end = get_morning_reading_pages(user)
            juz = quran_data.page_to_juz(r_start)
            today_memo = get_today_memorize_page(user)
            memo_surah = quran_data.page_to_surah(today_memo)
        text = (
            "🌅 *صباح الخير\\!*\n\n"
            f"📅 {_today_str()}\n\n"
            f"📖 *القراءة \\- حزبين:*\nالصفحات {r_start}–{r_end} \\(الجزء {juz}\\)\n\n"
            f"✍️ *صفحة الحفظ اليوم:* {today_memo}\n"
            f"📖 سورة {escape_md(memo_surah.name_ar)}\n\n"
            f"💡 ابدئي بقراءة الصفحة {today_memo} 3 مرات قبل الحفظ\n"
            f"بعد الإنهاء: `/markdone reading`"
        )
        await bot.send_message(chat_id=telegram_id, text=text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
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
            "☀️ *وقت الاستماع\\!*\n\n"
            f"📅 {_today_str()}\n\n"
            f"🎧 *استماع لحزب:*\nالصفحات {l_start}–{l_end}\n\n"
        )
        if audio_url:
            text += f"🔊 [استمعي بصوت الحصري]({escape_md(audio_url)})\n\n"
        text += (
            "💡 *نصيحة:*\n• استمعي للتأمل\n• كرري 3 مرات\n• اقرئي بصوت منخفض مع القارئ\n\n"
            "بعد الإنهاء: `/markdone listening`"
        )
        await bot.send_message(chat_id=telegram_id, text=text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
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
        if not progress.memorize_done:
            text = (
                "🌙 *مساء الخير\\!*\n\n"
                f"📅 {_today_str()}\n\n"
                f"✍️ *صفحة الحفظ اليوم:* {today_memo}\n"
                f"📖 سورة {escape_md(memo_surah.name_ar)}\n\n"
                f"*هل أنهيتِ حفظ صفحة اليوم؟*"
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ نعم، حفظتها", callback_data="evening_yes"),
                InlineKeyboardButton("⏳ لسه", callback_data="evening_later"),
            ]])
            await bot.send_message(chat_id=telegram_id, text=text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)
        else:
            if weekly_today:
                text = "🌙 *مساء الخير\\!*\n\n✅ أحسنت\\! تم الحفظ\\.\n\n*🔍 مراجعات مستحقة اليوم:*\n"
                for wr in weekly_today:
                    wr_surah = quran_data.page_to_surah(wr["page"])
                    text += f"• {wr['label']}: صفحة {wr['page']} \\({escape_md(wr_surah.name_ar)}\\)\n"
                text += "\n💡 راجعيها قبل النوم"
            else:
                text = "🌙 *مساء الخير\\!*\n\n✅ أحسنت\\! تم الحفظ\\.\n🤲 تقبل الله منك"
            await bot.send_message(chat_id=telegram_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.error(f"خطأ في رسالة المساء لـ {telegram_id}: {e}")


async def evening_yes_callback(update, context):
    query = update.callback_query
    await query.answer()
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=update.effective_user.id)
        await mark_memorized(session, user, user.current_page)
        await mark_progress_done(session, user.id, "memorize")
        today_memo = get_today_memorize_page(user)
        next_page = user.current_page
        next_surah = quran_data.page_to_surah(next_page)
        weekly_today = await get_today_weekly_review(session, user.id)
    text = (
        f"🎉 *ما شاء الله\\!* تم تسجيل حفظ صفحة {today_memo - 1 if today_memo > 1 else 1}\n\n"
        f"📍 *صفحة الغد:* {next_page}\n📖 سورة {escape_md(next_surah.name_ar)}\n\n"
    )
    if weekly_today:
        text += "*🔍 مراجعات مستحقة:*\n"
        for wr in weekly_today:
            wr_surah = quran_data.page_to_surah(wr["page"])
            text += f"• {wr['label']}: صفحة {wr['page']} \\({escape_md(wr_surah.name_ar)}\\)\n"
        text += "\n💡 `/markdone weekly <page>`"
    else:
        text += "🤲 تقبل الله منك"
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu())


async def evening_later_callback(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⏳ *لا بأس، خذي وقتك\\!*\n\n• اقرئي الصفحة 3 مرات\n• كرري الآيات الصعبة\n• سجلي: `/markdone memorize`\n\n🤲 أعانك الله",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


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
        for jid in [morning_id, midday_id, evening_id]:
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

def build_application():
    if not BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN غير مضبوط"); sys.exit(1)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("fortresses", fortresses_command))
    app.add_handler(CommandHandler("progress", progress_command))
    app.add_handler(CommandHandler("setpage", setpage_command))
    app.add_handler(CommandHandler("markdone", markdone_command))
    app.add_handler(CommandHandler("settime", settime_command))
    app.add_handler(CommandHandler("timezone", timezone_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(today|fortresses|progress|settings)$"))
    app.add_handler(CallbackQueryHandler(evening_yes_callback, pattern="^evening_yes$"))
    app.add_handler(CallbackQueryHandler(evening_later_callback, pattern="^evening_later$"))
    return app


async def post_init(app):
    logger.info("🔧 تهيئة قاعدة البيانات...")
    await init_db()
    logger.info("✅ قاعدة البيانات جاهزة")
    logger.info("⏰ تشغيل المجدول...")
    start_scheduler(app.bot)
    asyncio.create_task(_periodic_reschedule(app.bot))


async def _run_polling_with_keepalive():
    app = build_application()
    keepalive_runner = None
    keepalive_task = None
    if KEEPALIVE_ENABLED:
        public_url = f"{RENDER_EXTERNAL_URL}/health" if RENDER_EXTERNAL_URL else ""
        logger.info(f"🌐 بدء خادم keep-alive على المنفذ {PORT}...")
        keepalive_runner, keepalive_task = await start_keepalive_server(
            port=PORT, public_health_url=public_url, keepalive_interval=KEEPALIVE_INTERVAL,
        )
        if public_url:
            logger.info(f"✅ keep-alive نشط — self-ping كل {KEEPALIVE_INTERVAL} ثانية")
        else:
            logger.warning("⚠️ RENDER_EXTERNAL_URL غير مضبوط — الخدمة قد تنام")
    await post_init(app)
    logger.info("🚀 تشغيل البوت في وضع polling...")
    try:
        await app.run_polling(poll_interval=3, drop_pending_updates=True, close_loop=False)
    finally:
        if keepalive_task:
            keepalive_task.cancel()
            try: await keepalive_task
            except asyncio.CancelledError: pass
        if keepalive_runner:
            await keepalive_runner.cleanup()


def main():
    logger.info("📖 بوت الحصون الخمسة — البدء")
    logger.info(f"  - الصباح: {MORNING_TIME}")
    logger.info(f"  - الظهيرة: {MIDDAY_TIME}")
    logger.info(f"  - المساء: {EVENING_TIME}")
    logger.info(f"  - المنطقة الزمنية: {DEFAULT_TIMEZONE}")
    logger.info(f"  - keep-alive: {'مُفعّل' if KEEPALIVE_ENABLED else 'مُعطّل'}")
    if RENDER_EXTERNAL_URL or KEEPALIVE_ENABLED:
        asyncio.run(_run_polling_with_keepalive())
    else:
        app = build_application()
        asyncio.run(post_init(app))
        logger.info("🚀 تشغيل البوت في وضع polling (محلي)...")
        asyncio.run(app.run_polling(poll_interval=3, drop_pending_updates=True, close_loop=False))


if __name__ == "__main__":
    main()
