"""
معالجات الأوامر النصية: /start /help /today /progress /settings /update /settime ...
"""
import logging
from datetime import date, datetime

from sqlalchemy import select
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import AsyncSessionLocal
from models import UserSettings, FarReviewCycle
from user_service import get_or_create_user, update_settings, set_initial_hifz
import config
from keyboards import main_keyboard
from onboarding import start_onboarding
from today_dashboard import show_today_dashboard
from progress import show_progress, show_activity_log
from fortress_views import show_fortresses_menu
from settings_panel import show_settings_panel, show_suggestions
from utils import safe_send_message

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /start — يبدأ الـ onboarding أو يعرض ورد اليوم."""
    user_info = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, user_info.id, user_info.username, user_info.full_name)
        needs_onboarding = not user.onboarding_done

    if needs_onboarding:
        await start_onboarding(update, context, welcome=True)
        return

    await update.message.reply_text(
        f"👋 <b>أهلًا بعودتك!</b> 🌟\nإليكِ <b>ورد اليوم</b> 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )
    await show_today_dashboard(update, context)


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_today_dashboard(update, context)


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
    from onboarding import parse_memorization_input
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
    from reminders import schedule_user_jobs
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
