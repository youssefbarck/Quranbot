"""
معالج الـ Onboarding — Setup Wizard من 5 خطوات.
"""
import re
import logging
from datetime import date, datetime

from sqlalchemy import select
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..database import AsyncSessionLocal
from ..services.user_service import get_or_create_user, set_initial_hifz, update_settings
from .. import quran_data, config
from ..ui.keyboards import (
    onboarding_start_inline, daily_amount_inline, weekly_amount_inline,
    plan_start_inline, reminders_confirm_inline,
    main_keyboard,
)
from ..ui.renderers import esc, bold, code
from .utils import safe_edit_message

logger = logging.getLogger(__name__)

# حالة الـ onboarding لكل مستخدم (مؤقتة في الذاكرة)
ONBOARDING_STATE = {}  # user_id -> "step_name"


async def start_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE, welcome: bool = True):
    """يبدأ Setup Wizard — الخطوة 1: آخر وجه محفوظ."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "ob_step_1_memorization"

    welcome_text = ""
    if welcome:
        welcome_text = (
            "🌟 <b>أهلًا بكِ في بوت الحصون الخمسة</b>\n\n"
            "مرافقك الشخصي لحفظ القرآن الكريم وفق منهج الحصون الخمسة.\n"
            "سنُهيّئ خطتك في 5 خطوات سريعة. 🚀\n\n"
        )

    text = (
        f"{welcome_text}"
        "━━━━━━━━━━━━━━━━\n"
        "❓ <b>الخطوة 1/5: أين وصلتِ في الحفظ؟</b>\n\n"
        "اختر آخر سورة حفظتِها كاملة، أو أدخلي يدويًا.\n"
        "إذا لم تحفظي شيئًا بعد، اختر 'لم أحفظ شيئًا'.\n"
        "━━━━━━━━━━━━━━━━"
    )
    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=onboarding_start_inline(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await safe_edit_message(update.callback_query, text, onboarding_start_inline())


async def process_onboarding_memorization(update: Update, context: ContextTypes.DEFAULT_TYPE, text_input: str):
    """معالجة إدخال الخطوة 1 ثم الانتقال للخطوة 2."""
    user_id = update.effective_user.id
    parsed = await parse_memorization_input(text_input)

    if parsed["page"] is None and "0" not in text_input and "لا" not in text_input.lower():
        # لم نفهم — نُعيد السؤال
        text = (
            "❌ <b>لم أفهم الإجابة</b> 😅\n\n"
            "جرّبي:\n"
            "• <code>صفحة 50</code>\n"
            "• <code>سورة المائدة</code>\n"
            "• <code>جزء 3</code>\n"
            "• <code>0</code> (لم أحفظ)"
        )
        if update.message:
            await update.message.reply_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=onboarding_start_inline(),
                disable_web_page_preview=True,
            )
        return

    page = parsed["page"] or 0
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=user_id)
        await set_initial_hifz(session, user, page)

    # الانتقال للخطوة 2
    await ask_daily_amount(update, context)


async def ask_daily_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 2: مقدار الحفظ اليومي."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "ob_step_2_daily_amount"
    text = (
        "✅ <b>تمّ تسجيل محفوظك السابق!</b> 🎉\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "❓ <b>الخطوة 2/5: كم تريدين أن تحفظي يوميًا؟</b>\n\n"
        "💡 <i>التوصية: وجهان لمن تملك الوقت. لكن حتى وجه واحد يومياً "
        "يكفي لإتمام القرآن خلال سنتين.</i>\n"
        "━━━━━━━━━━━━━━━━"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, daily_amount_inline())
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=daily_amount_inline(),
            disable_web_page_preview=True,
        )


async def ask_weekly_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 3: مقدار الحفظ الأسبوعي."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "ob_step_3_weekly_amount"
    text = (
        "✅ <b>تمّ ضبط الحفظ اليومي!</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "❓ <b>الخطوة 3/5: كم تريدين أن تحفظي أسبوعيًا؟</b>\n\n"
        "💡 <i>هذا يُحدّد نطاق التحضير الأسبوعي (الحصن الثاني).</i>\n"
        "━━━━━━━━━━━━━━━━"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, weekly_amount_inline())


async def ask_plan_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 4: تاريخ بداية الخطة."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "ob_step_4_plan_start"
    today_str = date.today().strftime("%Y-%m-%d")
    text = (
        "✅ <b>تمّ ضبط المقدار الأسبوعي!</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"❓ <b>الخطوة 4/5: متى تبدأ خطتك؟</b>\n\n"
        f"📅 اليوم: <code>{esc(today_str)}</code>\n\n"
        "💡 <i>يُحدّد بداية دورة القراءة (30 يومًا) ودورة الاستماع (60 يومًا).</i>\n"
        "━━━━━━━━━━━━━━━━"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, plan_start_inline())


async def ask_reminder_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الخطوة 5: تأكيد أوقات التذكيرات."""
    user_id = update.effective_user.id
    ONBOARDING_STATE[user_id] = "ob_step_5_reminders"
    from .. import config
    text = (
        "✅ <b>تمّ ضبط تاريخ البداية!</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "❓ <b>الخطوة 5/5: أوقات التذكيرات الـ 8</b>\n\n"
        "🕒 <b>الأوقات الافتراضية:</b>\n"
    )
    labels = config.REMINDER_LABELS_AR
    for rtype in config.REMINDER_TYPES:
        text += f"• <code>{config.DEFAULT_REMINDER_TIMES[rtype]}</code> — {labels[rtype]}\n"
    text += "\n💡 <i>يمكنك تخصيصها لاحقًا من ⚙️ الإعدادات</i>\n"
    text += "━━━━━━━━━━━━━━━━"
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reminders_confirm_inline())


async def finalize_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنهاء الـ onboarding وعرض ملخّص الخطة."""
    user_id = update.effective_user.id
    ONBOARDING_STATE.pop(user_id, None)

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, telegram_id=user_id)
        user.onboarding_done = True
        if user.plan_start_date is None:
            user.plan_start_date = user.created_at or date.today()
        await session.commit()

    text = (
        "🎉 <b>ما شاء الله! اكتملت تهيئتك</b> 🌟\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📊 <b>ملخّص خطتك:</b>\n\n"
        f"📖 آخر وجه محفوظ: <b>{user.last_hifz_page or 0}</b>\n"
        f"🆕 الوجه القادم: <b>{user.next_hifz_page or 1}</b>\n"
        f"📅 تاريخ بداية الخطة: <code>{esc(user.plan_start_date)}</code>\n"
        f"📚 المقدار اليومي: <b>{user.daily_hifz_amount} وجه</b>\n"
        f"📚 المقدار الأسبوعي: <b>{user.weekly_hifz_amount} وجه</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "👇 اضغط <b>📋 ورد اليوم</b> في الأسفل لعرض برنامجك الكامل"
    )

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
                disable_web_page_preview=True,
            )
        except Exception:
            await update.effective_chat.send_message(
                text, parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(),
                disable_web_page_preview=True,
            )
    elif update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )


async def parse_memorization_input(text: str) -> dict:
    """تحليل إدخال المستخدم حول آخر صفحة محفوظة.
    
    الصيغ المدعومة:
        "ختمت القرآن" / "كامل"  → page = 604
        "جزء 7"                → آخر وجه في الجزء 7
        "سورة المائدة"          → آخر وجه في سورة المائدة
        "صفحة 100-110"         → نطاق
        "صفحة 100"             → وجه واحد
        "100"                  → رقم مباشر
        "0" / "لا"             → لم يحفظ
    """
    text = text.strip()
    result = {"type": None, "page": None, "raw": text}

    # ختم القرآن
    if any(k in text for k in ["كل القرآن", "كامل القرآن", "ختمت", "كله"]):
        result.update({"type": "all", "page": quran_data.TOTAL_PAGES})
        return result

    # "لم أحفظ"
    if "0" in text or "لا" in text.lower() or "ما حفظت" in text or "لم" in text:
        if not any(c.isdigit() and int(c) > 0 for c in text.split()):
            result.update({"type": "none", "page": 0})
            return result

    # جزء N
    m = re.search(r"جزء\s*(\d+)", text)
    if m:
        juz = int(m.group(1))
        if 1 <= juz <= 30:
            start, end = quran_data.juz_pages(juz)
            result.update({"type": "juz", "page": end})
            return result

    # سورة X
    m = re.search(r"سورة\s+(.+)", text)
    if m:
        surah = quran_data.get_surah_by_name(m.group(1).strip())
        if surah:
            if surah.number < 114:
                last_page = quran_data.get_surah_by_number(surah.number + 1).page_start - 1
            else:
                last_page = quran_data.TOTAL_PAGES
            result.update({"type": "surah", "page": last_page})
            return result

    # نطاق صفحات
    m = re.search(r"صفحة\s*(\d+)\s*[-–]\s*(\d+)", text)
    if m:
        end_p = int(m.group(2))
        if 1 <= end_p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page_range", "page": end_p})
            return result

    # صفحة N
    m = re.search(r"صفحة\s*(\d+)", text)
    if m:
        p = int(m.group(1))
        if 1 <= p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page", "page": p})
            return result

    # رقم مباشر
    m = re.match(r"^\s*(\d+)\s*$", text)
    if m:
        p = int(m.group(1))
        if 1 <= p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page", "page": p})
            return result

    return result
