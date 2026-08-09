"""
معالج الأخطاء الموحَّد.
"""
import logging
import traceback

from telegram import Update
from telegram.error import (
    Conflict, NetworkError, TimedOut, Forbidden, BadRequest,
)
from telegram.ext import ContextTypes

from keyboards import main_keyboard

logger = logging.getLogger(__name__)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج موحَّد للأخطاء."""
    error = context.error

    if isinstance(error, Conflict):
        logger.warning(f"⚠️ Conflict (تجاهل): {error}")
        if update and getattr(update, "callback_query", None):
            try: await update.callback_query.answer()
            except Exception: pass
        return

    if isinstance(error, TimedOut):
        logger.warning(f"⚠️ TimedOut (تجاهل): {error}")
        return

    if isinstance(error, Forbidden):
        logger.warning(f"⚠️ المستخدم حظر البوت: {error}")
        return

    if isinstance(error, BadRequest):
        msg = str(error).lower()
        if "not modified" in msg:
            return  # لا خطأ
        logger.error(f"❌ BadRequest: {error}", exc_info=False)
        if update and getattr(update, "effective_chat", None):
            try:
                if getattr(update, "callback_query", None):
                    try: await update.callback_query.answer()
                    except Exception: pass
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ حدث خطأ بسيط. جرّب مرة أخرى أو /start",
                    reply_markup=main_keyboard(),
                )
            except Exception:
                pass
        return

    if isinstance(error, NetworkError):
        logger.warning(f"⚠️ خطأ شبكة: {error}")
        return

    logger.error(f"❌ خطأ: {type(error).__name__}: {error}", exc_info=True)
    if update and getattr(update, "effective_chat", None):
        try:
            if getattr(update, "callback_query", None):
                try: await update.callback_query.answer()
                except Exception: pass
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ حدث خطأ غير متوقع. جرّب مرة أخرى أو /start",
                reply_markup=main_keyboard(),
            )
        except Exception:
            pass
