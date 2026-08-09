"""
معالج لوحة الإعدادات — تعديل يدوي لكل القيم.
"""
import logging
import re
from datetime import date

from sqlalchemy import select
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import AsyncSessionLocal
from models import UserSettings
from user_service import get_or_create_user, update_settings, set_initial_hifz
from smart_suggestions import generate_suggestions
from hifz_engine import set_last_hifz_page
from revision_engine import get_far_review_state
import config, quran_data
from keyboards import (
    settings_panel_inline, back_to_today_inline,
    confirm_inline, daily_amount_inline, weekly_amount_inline,
)
from renderers import render_settings_panel, render_suggestions, esc
from utils import safe_edit_message

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
            from models import FarReviewCycle
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
