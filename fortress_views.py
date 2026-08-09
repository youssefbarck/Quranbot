"""
معالجات الحصون الخمسة — عرض تفصيلي لكل حصن.
"""
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import AsyncSessionLocal
from user_service import get_or_create_user
from task_service import get_or_create_progress
from today_plan import compute_today_plan
from keyboards import fortresses_menu_inline, back_to_today_inline
from renderers import (
    render_fortress_1, render_fortress_2, render_fortress_3,
    render_fortress_4, render_fortress_5,
)
from utils import safe_edit_message
from onboarding import start_onboarding

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
