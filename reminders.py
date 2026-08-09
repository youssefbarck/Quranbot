"""
المجدول — 8 تذكيرات يومية لكل مستخدم.
"""
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from ..database import AsyncSessionLocal
from ..models import User, UserSettings
from .. import config
from ..ui.keyboards import main_keyboard

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
    """جدولة كل المستخدمين عند بدء التشغيل."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.onboarding_done == True))
        users = list(result.scalars().all())

    for user in users:
        await schedule_user_jobs(bot, user)
    logger.info(f"✅ تمت جدولة التذكيرات لـ {len(users)} مستخدم")


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
