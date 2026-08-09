"""
معالج شاشة التقدم.
"""
import logging

from sqlalchemy import select, func
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import AsyncSessionLocal
from models import MemorizationLog, ActivityLog
from user_service import get_or_create_user
from task_service import get_or_create_progress
from today_plan import compute_today_plan
from renderers import render_progress_dashboard, render_activity_log
from keyboards import back_to_today_inline
from utils import safe_edit_message, safe_send_message
from onboarding import start_onboarding

logger = logging.getLogger(__name__)


async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض شاشة التقدم."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            await start_onboarding(update, context, welcome=False)
            return
        progress = await get_or_create_progress(session, user.id)
        plan = await compute_today_plan(session, user, progress)

        # عدد الأوجه المحفوظة فعليًا
        result = await session.execute(
            select(func.count(MemorizationLog.id)).where(MemorizationLog.user_id == user.id)
        )
        total_memorized = result.scalar() or 0

    text = render_progress_dashboard(user, plan, total_memorized)
    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=back_to_today_inline(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())


async def show_activity_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض سجل النشاط."""
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, update.effective_user.id)
        result = await session.execute(
            select(ActivityLog)
            .where(ActivityLog.user_id == user.id)
            .order_by(ActivityLog.log_date.desc(), ActivityLog.log_time.desc())
            .limit(50)
        )
        logs = list(result.scalars().all())

    text = render_activity_log(logs)
    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=back_to_today_inline(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await safe_edit_message(update.callback_query, text, back_to_today_inline())
