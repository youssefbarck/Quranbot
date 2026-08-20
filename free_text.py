"""
معالج النص الحر — NLP بسيط لفهم أوامر المستخدم بالعربية.
"""
import re
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import AsyncSessionLocal
from user_service import get_or_create_user
import config, quran_data
from keyboards import main_keyboard, back_to_today_inline
from onboarding import ONBOARDING_STATE, parse_memorization_input, ask_daily_amount
from settings_panel import INPUT_STATE, process_free_input
from today_dashboard import show_today_dashboard, show_main_panel
from progress import show_progress
from utils import safe_send_message

logger = logging.getLogger(__name__)


# خريطة نصوص ReplyKeyboard
from keyboards import KEYBOARD_TEXT_MAP


async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج النص الحر — NLP بسيط + توجيه للأوامر."""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # 1. لو النص يطابق أحد أزرار الـ ReplyKeyboard
    if text in KEYBOARD_TEXT_MAP:
        cmd = KEYBOARD_TEXT_MAP[text]
        if cmd == "main_panel":
            await show_main_panel(update, context)
        elif cmd == "today":
            await show_today_dashboard(update, context)
        elif cmd == "progress":
            await show_progress(update, context)
        elif cmd == "fortresses":
            from fortress_views import show_fortresses_menu
            await show_fortresses_menu(update, context)
        elif cmd == "settings":
            from settings_panel import show_settings_panel
            await show_settings_panel(update, context)
        return

    # 2. لو المستخدم في وضع الإدخال اليدوي (إعدادات)
    if user_id in INPUT_STATE:
        handled = await process_free_input(update, context, text)
        if handled:
            return

    # 3. لو المستخدم في وضع الـ onboarding
    state = ONBOARDING_STATE.get(user_id)
    if state == "ob_step_1_memorization":
        from onboarding import process_onboarding_memorization
        await process_onboarding_memorization(update, context, text)
        return

    # 4. NLP بسيط لفهم أوامر عربية طبيعية
    handled = await try_natural_language(update, context, text)
    if handled:
        return

    # 5. نص حر غير مفهوم
    await update.message.reply_text(
        "💡 <b>اضغط أحد أزرار القائمة بالأسفل</b>\n\n"
        "أو جرّب:\n"
        "• <code>صفحة 50</code> — تعديل آخر محفوظ\n"
        "• <code>وش نحفظ اليوم؟</code> — عرض ورد اليوم\n"
        "• <code>وين وصلت؟</code> — عرض التقدم\n"
        "• <code>حفظت الوجه 41</code> — تسجيل الحفظ",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


async def try_natural_language(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """محاولة فهم اللغة الطبيعية العربية.
    
    يدعم:
        "وش نحفظ اليوم؟" / "شنو نحفظ" → ورد اليوم
        "وين وصلت؟" → التقدم
        "وش نراجع؟" → الحصون الرابع والخامس
        "حفظت الوجه X" / "حفظت X" → تسجيل الحفظ
        "قريت الورد" / "ختمت القراءة" → تأكيد القراءة
        "اليوم ما قدرت" → تسجيل كغير مكتمل (دون تحريك الحفظ)
        "نسيت وين وصلت" → عرض التقدم
        "أريد نغيّر الحفظ إلى X" → تعديل المقدار
    """
    text_lower = text.lower()

    # === "وش نحفظ اليوم؟" ===
    if any(k in text_lower for k in ["شنو نحفظ", "وش نحفظ", "ايش نحفظ", "ماذا أحفظ", "ماذا احفظ", "وش نقرا", "وش نراجع"]):
        if "راجع" in text_lower:
            from fortress_views import show_fortress_4, show_fortress_5, show_fortresses_menu
            await show_fortresses_menu(update, context)
        else:
            await show_today_dashboard(update, context)
        return True

    # === "وين وصلت؟" ===
    if any(k in text_lower for k in ["وين وصلت", "وين وصل", "وش المحفوظ", "وصلت ل", "وين انا", "نسيت وين"]):
        await show_progress(update, context)
        return True

    # === "حفظت الوجه X" / "حفظت X" ===
    m = re.search(r"حفظت\s*(?:الوجه\s*)?(\d+)", text)
    if m:
        page = int(m.group(1))
        if 1 <= page <= quran_data.TOTAL_PAGES:
            # تعديل آخر محفوظ
            async with AsyncSessionLocal() as session:
                from user_service import get_or_create_user, set_initial_hifz
                user = await get_or_create_user(session, telegram_id=update.effective_user.id)
                # إذا الصفحة أكبر من last_hifz_page، نحدّث
                if page > (user.last_hifz_page or 0):
                    await set_initial_hifz(session, user, page)
                    await update.message.reply_text(
                        f"✅ تم تسجيل حفظ الوجه <b>{page}</b> 🎉",
                        parse_mode=ParseMode.HTML,
                        reply_markup=back_to_today_inline(),
                        disable_web_page_preview=True,
                    )
                else:
                    await update.message.reply_text(
                        f"⚠️ الوجه {page} محفوظ سابقًا.\nآخر محفوظ: <b>{user.last_hifz_page}</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=back_to_today_inline(),
                        disable_web_page_preview=True,
                    )
            return True

    # === "قريت الورد" / "ختمت القراءة" ===
    if any(k in text_lower for k in ["قريت الورد", "قريت ورد", "ختمت القراءة", "خلصت القراءة", "قرأت الورد"]):
        async with AsyncSessionLocal() as session:
            from user_service import get_or_create_user
            from task_service import get_or_create_progress, toggle_task
            user = await get_or_create_user(session, telegram_id=update.effective_user.id)
            progress = await get_or_create_progress(session, user.id)
            if not progress.reading_done:
                await toggle_task(session, user, progress, "reading")
                await update.message.reply_text(
                    "✅ تم تسجيل إنجاز القراءة 📖",
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_to_today_inline(),
                    disable_web_page_preview=True,
                )
            else:
                await update.message.reply_text(
                    "✅ القراءة مكتملة بالفعل اليوم",
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_to_today_inline(),
                    disable_web_page_preview=True,
                )
        return True

    # === "سمعت الاستماع" / "خلصت الاستماع" ===
    if any(k in text_lower for k in ["سمعت", "خلصت الاستماع", "قريت الاستماع", "أنهيت الاستماع"]):
        async with AsyncSessionLocal() as session:
            from user_service import get_or_create_user
            from task_service import get_or_create_progress, toggle_task
            user = await get_or_create_user(session, telegram_id=update.effective_user.id)
            progress = await get_or_create_progress(session, user.id)
            if not progress.listening_done:
                await toggle_task(session, user, progress, "listening")
                await update.message.reply_text(
                    "✅ تم تسجيل إنجاز الاستماع 🎧",
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_to_today_inline(),
                    disable_web_page_preview=True,
                )
        return True

    # === "اليوم ما قدرت" ===
    if any(k in text_lower for k in ["ما قدرت", "ما قديت", "اليوم ما", "نسيت اليوم", "تأجيل", "أجّل"]):
        async with AsyncSessionLocal() as session:
            from user_service import get_or_create_user
            from task_service import log_activity
            user = await get_or_create_user(session, telegram_id=update.effective_user.id)
            await log_activity(session, user.id, "postponed", "أجّل المستخدم مهام اليوم")
        await update.message.reply_text(
            "📝 <b>سُجِّل اليوم كغير مكتمل</b>\n\n"
            "<i>لا تقلق — لم يتحرك الحفظ للأمام. الوجه المطلوب غدًا هو نفسه.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_today_inline(),
            disable_web_page_preview=True,
        )
        return True

    # === "أريد نغيّر الحفظ إلى X" ===
    m = re.search(r"(?:الحفظ|المقدار).{0,15}(\d+)", text)
    if m and ("غيّر" in text_lower or "تغيير" in text_lower or "نولي" in text_lower or "بدّل" in text_lower):
        amount = int(m.group(1))
        if 1 <= amount <= 10:
            async with AsyncSessionLocal() as session:
                from user_service import get_or_create_user, update_settings
                user = await get_or_create_user(session, telegram_id=update.effective_user.id)
                await update_settings(session, user, daily_amount=amount)
            await update.message.reply_text(
                f"✅ تم تغيير المقدار اليومي إلى <b>{amount} وجه</b>\n"
                "<i>تم إعادة حساب التحضير الأسبوعي تلقائيًا.</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_today_inline(),
                disable_web_page_preview=True,
            )
            return True

    # === "صفحة X" / "سورة Y" — تعديل آخر محفوظ ===
    if any(k in text_lower for k in ["صفحة", "سورة", "جزء", "ختمت"]):
        parsed = await parse_memorization_input(text)
        if parsed["page"] is not None:
            async with AsyncSessionLocal() as session:
                from user_service import get_or_create_user, set_initial_hifz
                user = await get_or_create_user(session, telegram_id=update.effective_user.id)
                await set_initial_hifz(session, user, parsed["page"])
            await update.message.reply_text(
                f"✅ تم ضبط آخر وجه محفوظ على <b>{parsed['page']}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_today_inline(),
                disable_web_page_preview=True,
            )
            return True

    return False
