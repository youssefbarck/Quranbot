"""
مجدول المهام — طريقة الحصون الخمسة
=================================
3 تذكيرات يومية:
1. الصباح (08:00) - تذكير بقراءة حزبين
2. الظهيرة (13:00) - تذكير بالاستماع لحزب
3. المساء (20:00) - سؤال تفاعلي: هل أنهيت الحفظ اليوم؟
"""
import logging
from datetime import date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from sqlalchemy import select

from .database import AsyncSessionLocal
from .models import User
from . import quran_data, logic, handlers

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

DATE_FMT = "%Y-%m-%d"


def _today_str() -> str:
    return date.today().strftime(DATE_FMT)


# ====== 1. تذكير الصباح: قراءة حزبين ======

async def send_morning_message(bot, telegram_id: int):
    try:
        async with AsyncSessionLocal() as session:
            user = await logic.get_or_create_user(session, telegram_id=telegram_id)
            if not user.onboarding_done:
                return  # تجاهل المستخدمين غير المهيئين

            r_start, r_end = logic.get_morning_reading_pages(user)
            juz = quran_data.page_to_juz(r_start)
            today_memo = logic.get_today_memorize_page(user)
            memo_surah = quran_data.page_to_surah(today_memo)

        text = (
            "🌅 *صباح الخير\\!*\n\n"
            f"📅 {_today_str()}\n\n"
            f"📖 *القراءة اليومية \\- حزبين:*\n"
            f"الصفحات {r_start}–{r_end} \\(الجزء {juz}\\)\n"
            f"🔗 [{handlers.escape_md('اقرأ هنا')}]({handlers.escape_md(quran_data.get_quran_text_url(r_start))})\n\n"
            f"✍️ *صفحة الحفظ اليوم:* {today_memo}\n"
            f"📖 سورة {handlers.escape_md(memo_surah.name_ar)}\n\n"
            f"💡 ابدئي بقراءة الصفحة {today_memo} 3 مرات قبل الحفظ\n"
            f"بعد الإنهاء: `/markdone reading`\n"
        )
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"خطأ في رسالة الصباح لـ {telegram_id}: {e}")


# ====== 2. تذكير الظهيرة: الاستماع لحزب ======

async def send_midday_message(bot, telegram_id: int):
    try:
        async with AsyncSessionLocal() as session:
            user = await logic.get_or_create_user(session, telegram_id=telegram_id)
            if not user.onboarding_done:
                return

            l_start, l_end = logic.get_midday_listening_pages(user)
            today_memo = logic.get_today_memorize_page(user)
            audio_url = quran_data.get_page_audio_url(today_memo)

        text = (
            "☀️ *وقت الاستماع\\!*\n\n"
            f"📅 {_today_str()}\n\n"
            f"🎧 *استماع لحزب واحد:*\n"
            f"الصفحات {l_start}–{l_end}\n\n"
        )
        if audio_url:
            text += f"🔊 [استمعي بصوت الحصري]({handlers.escape_md(audio_url)})\n\n"
        text += (
            "💡 *نصيحة:*\n"
            "• استمعي أولاً للتأمل\n"
            "• كرري الاستماع 3 مرات\n"
            "• اقرئي بصوت منخفض مع القارئ\n\n"
            "بعد الإنهاء: `/markdone listening`"
        )
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"خطأ في رسالة الظهيرة لـ {telegram_id}: {e}")


# ====== 3. تذكير المساء: سؤال تفاعلي ======

async def send_evening_message(bot, telegram_id: int):
    """يرسل سؤالاً تفاعلياً: هل أنهيت الحفظ اليوم؟"""
    try:
        async with AsyncSessionLocal() as session:
            user = await logic.get_or_create_user(session, telegram_id=telegram_id)
            if not user.onboarding_done:
                return

            today_memo = logic.get_today_memorize_page(user)
            progress = await logic.get_or_create_progress(session, user.id)
            memo_surah = quran_data.page_to_surah(today_memo)

            # المراجعات المستحقة اليوم (الحصن 4)
            weekly_today = await logic.get_today_weekly_review(session, user.id)

        # لو الحفظ لم يُسجل بعد
        if not progress.memorize_done:
            text = (
                "🌙 *مساء الخير\\!*\n\n"
                f"📅 {_today_str()}\n\n"
                f"✍️ *صفحة الحفظ اليوم:* {today_memo}\n"
                f"📖 سورة {handlers.escape_md(memo_surah.name_ar)}\n\n"
                f"*هل أنهيتِ حفظ صفحة اليوم؟*\n"
            )
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ نعم، حفظتها", callback_data="evening_yes"),
                    InlineKeyboardButton("⏳ لسه", callback_data="evening_later"),
                ]
            ])
            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
        else:
            # الحفظ أُتم، نتذكر بالمراجعة الأسبوعية إن وجدت
            if weekly_today:
                text = "🌙 *مساء الخير\\!*\n\n✅ أحسنت\\! تم حفظ صفحة اليوم\\.\n\n"
                text += "*🔍 مراجعات أسبوعية مستحقة اليوم:*\n"
                for wr in weekly_today:
                    wr_surah = quran_data.page_to_surah(wr["page"])
                    text += f"• {wr['label']}: صفحة {wr['page']} \\({handlers.escape_md(wr_surah.name_ar)}\\)\n"
                text += "\n💡 راجعيها قبل النوم"
            else:
                text = (
                    "🌙 *مساء الخير\\!*\n\n"
                    "✅ أحسنت\\! تم حفظ صفحة اليوم\\.\n\n"
                    "🤲 تقبل الله منك"
                )
            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    except Exception as e:
        logger.error(f"خطأ في رسالة المساء لـ {telegram_id}: {e}")


# ====== معالجة أزرار السؤال التفاعلي ======

async def evening_yes_callback(update, context):
    """عندما تؤكد المستخدمة إتمام الحفظ"""
    query = update.callback_query
    await query.answer()

    async with AsyncSessionLocal() as session:
        user = await logic.get_or_create_user(session, telegram_id=update.effective_user.id)
        # نسجل الحفظ
        await logic.mark_memorized(session, user, user.current_page)
        await logic.mark_progress_done(session, user.id, "memorize")

        today_memo = logic.get_today_memorize_page(user)
        # الصفحة الجديدة بعد التسجيل = current_page الحالي
        next_page = user.current_page
        next_surah = quran_data.page_to_surah(next_page)

        # المراجعات المستحقة اليوم
        weekly_today = await logic.get_today_weekly_review(session, user.id)

    text = (
        "🎉 *ما شاء الله\\! تبارك الله\\!*\n\n"
        f"✅ تم تسجيل حفظ صفحة {today_memo - 1 if today_memo > 1 else 1}\n\n"
        f"📍 *صفحة الغد:* {next_page}\n"
        f"📖 سورة {handlers.escape_md(next_surah.name_ar)}\n\n"
    )

    if weekly_today:
        text += "*🔍 مراجعات أسبوعية مستحقة:*\n"
        for wr in weekly_today:
            wr_surah = quran_data.page_to_surah(wr["page"])
            text += f"• {wr['label']}: صفحة {wr['page']} \\({handlers.escape_md(wr_surah.name_ar)}\\)\n"
        text += "\n💡 راجعيها قبل النوم: `/markdone weekly <page>`"
    else:
        text += "🤲 تقبل الله منك"

    await query.edit_message_text(
        text, parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=handlers.main_menu(),
    )


async def evening_later_callback(update, context):
    """عندما تؤجل المستخدمة"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⏳ *لا بأس، خذي وقتك\\!*\n\n"
        "💡 *نصيحة:*\n"
        "• اقرئي الصفحة 3 مرات\n"
        "• كرري الآيات الصعبة\n"
        "• سجلي الإتمام عند الانتهاء: `/markdone memorize`\n\n"
        "🤲 أعانك الله",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ====== بناء الجدول ======

async def schedule_user_jobs(bot):
    """يبني جدول كل مستخدم حسب توقيته"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.is_active == True)
        )
        users = list(result.scalars().all())

    import pytz
    for user in users:
        try:
            tz = pytz.timezone(user.timezone)
        except Exception:
            tz = pytz.timezone("Africa/Algiers")

        # الأوقات الثلاثة
        m_h, m_m = map(int, user.morning_time.split(":"))
        d_h, d_m = map(int, user.midday_time.split(":"))
        e_h, e_m = map(int, user.evening_time.split(":"))

        morning_id = f"morning_{user.telegram_id}"
        midday_id = f"midday_{user.telegram_id}"
        evening_id = f"evening_{user.telegram_id}"

        # إزالة الوظائف القديمة
        for jid in [morning_id, midday_id, evening_id]:
            try:
                scheduler.remove_job(jid)
            except Exception:
                pass

        # إضافة الوظائف الجديدة
        scheduler.add_job(
            send_morning_message,
            CronTrigger(hour=m_h, minute=m_m, timezone=tz),
            args=[bot, user.telegram_id],
            id=morning_id,
            replace_existing=True,
        )
        scheduler.add_job(
            send_midday_message,
            CronTrigger(hour=d_h, minute=d_m, timezone=tz),
            args=[bot, user.telegram_id],
            id=midday_id,
            replace_existing=True,
        )
        scheduler.add_job(
            send_evening_message,
            CronTrigger(hour=e_h, minute=e_m, timezone=tz),
            args=[bot, user.telegram_id],
            id=evening_id,
            replace_existing=True,
        )

    logger.info(f"تمت جدولة {len(users)} مستخدمًا بـ 3 تذكيرات يومية")


def start_scheduler(bot):
    """يبدي المجدول"""
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ بدأ المجدول")
    import asyncio
    asyncio.create_task(schedule_user_jobs(bot))


async def reschedule_all(bot):
    """يُعاد بناء الجدول (يُستدعى عند تغيير الإعدادات)"""
    await schedule_user_jobs(bot)
