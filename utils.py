"""
معالجات مساعدة مشتركة بين المعالجات الأخرى.
"""
import logging
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TimedOut

logger = logging.getLogger(__name__)


async def safe_edit_message(query, text, reply_markup=None) -> bool:
    """تحرير رسالة inline بسلامة — يتجاهل 'الرسالة لم تتغيّر'."""
    try:
        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=reply_markup, disable_web_page_preview=True,
        )
        return True
    except BadRequest as e:
        msg = str(e).lower()
        if "not modified" in msg or "message is not modified" in msg:
            return True
        if "message can't be edited" in msg or "too old" in msg:
            logger.warning(f"لا يمكن تحرير الرسالة: {e}")
            return False
        logger.warning(f"BadRequest في edit_message_text: {e}")
        return False
    except Exception as e:
        logger.warning(f"تعذّر تعديل الرسالة: {e}")
        return False


async def safe_send_message(bot, chat_id, text, reply_markup=None) -> bool:
    """إرسال آمن."""
    try:
        await bot.send_message(
            chat_id=chat_id, text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
        return True
    except Exception as e:
        logger.warning(f"تعذّر إرسال الرسالة: {e}")
        return False
