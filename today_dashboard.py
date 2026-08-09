"""
معالج ورد اليوم — يعرض المهام الـ 8 + يستقبل الضغطات (toggleable).
"""
import logging
from datetime import date

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import AsyncSessionLocal
from user_service import get_or_create_user, update_user_activity
from task_service import get_or_create_progress, toggle_task, start_pre_session
from today_plan import compute_today_plan
from keyboards import today_dashboard_with_status, pre_session_start_inline, back_to_today_inline
from renderers import render_today_dashboard
from utils import safe_edit_message
from onboarding import start_onboarding, ONBOARDING_STATE

logger = logging.getLogger(__name__)


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


async def handle_task_button(update: Update, context: ContextTypes.DEFAULT_TYPE, task_type: str):
    """معالجة ضغط زر مهمة — تبديل الحالة + إعادة عرض الواجهة."""
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
            # إذا لم يبدأ المؤقّت بعد، نبدؤه أولاً
            if not user.pre_session_started_at:
                await start_pre_session(session, user, progress)
                toast_text = "⏱️ بدأ المؤقّت (15 دقيقة)"
            else:
                # المؤقّت قيد التشغيل — هذا الضغط يعني الإنهاء
                result = await toggle_task(session, user, progress, task_type)
                if result.get("success"):
                    toast_text = "✅ تم الإنهاء"
        else:
            # المهام الأخرى: تبديل بسيط
            result = await toggle_task(session, user, progress, task_type)
            if result.get("success"):
                toast_text = "✅ تم الإنجاز" if result.get("action") == "done" else "↩️ تم التراجع"

        # refresh للحصول على أحدث حالة
        plan = await compute_today_plan(session, user, progress)

    # toast فوري
    if toast_text:
        try:
            await query.answer(text=toast_text, show_alert=False)
        except Exception:
            pass

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
