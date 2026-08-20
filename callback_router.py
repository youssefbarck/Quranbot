"""
الموجّه الرئيسي لكل أزرار Inline — يربط callback_data بالمعالجات.
"""
import re
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import AsyncSessionLocal
from user_service import get_or_create_user
from task_service import get_or_create_progress, toggle_task, start_pre_session
from today_plan import compute_today_plan
import config, quran_data
from onboarding import (
    ONBOARDING_STATE, start_onboarding, process_onboarding_memorization,
    ask_daily_amount, ask_weekly_amount, ask_plan_start_date,
    ask_reminder_times, finalize_onboarding,
)
from today_dashboard import (
    show_today_dashboard, handle_task_button, show_pre_session_start,
    show_main_panel, show_help,
)
from fortress_views import (
    show_fortresses_menu, show_fortress_1, show_fortress_2,
    show_fortress_3, show_fortress_4, show_fortress_5,
)
from progress import show_progress, show_activity_log
from settings_panel import (
    show_settings_panel, ask_last_page, ask_daily_amount as settings_ask_daily,
    ask_weekly_amount as settings_ask_weekly,
    ask_reading_hizb, ask_listening_hizb, ask_far_cycle,
    ask_notifications, show_reminders_settings, show_suggestions,
)
from utils import safe_edit_message

logger = logging.getLogger(__name__)

# خريطة أنواع المهام
from task_service import TASK_FIELD_MAP


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
                from user_service import update_settings
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
                from user_service import update_settings
                user = await get_or_create_user(session, telegram_id=update.effective_user.id)
                await update_settings(session, user, weekly_amount=amount)
            await ask_plan_start_date(update, context)
        return

    # ====== Onboarding: الخطوة 4 (تاريخ البداية) ======
    if data == "ob_plan_today":
        from datetime import date as date_cls
        async with AsyncSessionLocal() as session:
            from user_service import update_settings
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
                from user_service import update_settings
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
