"""
معالجات أوامر البوت — طريقة الحصون الخمسة
=========================================
الأوامر:
/start      - ترحيب + سؤال تفاعلي (ماذا حفظت؟)
/today      - كل مهام اليوم
/fortresses - عرض الحصون الخمسة
/progress   - تقدم الحفظ
/setpage    - تحديد الصفحة يدوياً
/settime    - تحديد أوقات التذكير
/timezone   - تحديد المنطقة الزمنية
/markdone   - تسجيل إتمام مهمة
/reset      - إعادة التهيئة
/help       - دليل الأوامر
"""
import logging
from datetime import date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
)
from sqlalchemy import select

from .database import AsyncSessionLocal
from .models import User, Memorization, WeeklyReview, MonthlyReview, DailyProgress
from . import quran_data, logic

logger = logging.getLogger(__name__)

# حالة المستخدمين الذين في طور إدخال ما حفظوه
ONBOARDING_STATE = {}


# ====== مساعدون ======

def escape_md(text: str) -> str:
    """يهرب الرموز الخاصة في Markdown V2"""
    escape_chars = "_*[]()~`>#+-=|{}.!"
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text


def progress_bar(current: int, total: int, length: int = 15) -> str:
    if total == 0:
        return "░" * length
    filled = int((current / total) * length)
    return "█" * filled + "░" * (length - filled)


def main_menu() -> InlineKeyboardMarkup:
    """القائمة الرئيسية"""
    kb = [
        [InlineKeyboardButton("📋 مهام اليوم", callback_data="today"),
         InlineKeyboardButton("🏰 الحصون الخمسة", callback_data="fortresses")],
        [InlineKeyboardButton("📊 تقدمي", callback_data="progress"),
         InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")],
    ]
    return InlineKeyboardMarkup(kb)


# ====== /start ======

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /start — يرحب ويسأل المستخدم ماذا حفظ"""
    user_info = update.effective_user
    async with AsyncSessionLocal() as session:
        user = await logic.get_or_create_user(
            session,
            telegram_id=user_info.id,
            username=user_info.username,
            full_name=user_info.full_name,
        )
        needs_onboarding = not user.onboarding_done

    if needs_onboarding:
        # نبدأ التهيئة التفاعلية
        ONBOARDING_STATE[user_info.id] = "waiting_for_memorization"
        text = (
            "🤲 *بسم الله الرحمن الرحيم*\n\n"
            f"أهلاً وسهلاً *{escape_md(user.full_name or 'أختي الكريمة')}*\\!\n\n"
            "📖 *بوت الحصون الخمسة لحفظ القرآن*\n\n"
            "قبل أن نبدأ، أحتاج معرفة ماذا حفظت سابقاً لأحدد لك نقطة البداية\\.\n\n"
            "*اكتب لي أحد الخيارات التالية:*\n\n"
            "• `صفحة 50` — إذا حفظت إلى صفحة 50\n"
            "• `جزء 3` — إذا حفظت 3 أجزاء كاملة\n"
            "• `سورة الكهف` — إذا حفظت حتى سورة الكهف\n"
            "• `ختمت القرآن` — إذا حفظت القرآن كاملاً وتريد المراجعة\n"
            "• `0` أو `لا شيء` — تبدأ من الصفحة الأولى\n\n"
            "💡 مثال: `صفحة 25`"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        # مستخدم قديم — نعرض له المهام
        await _show_today(update, context)


# ====== معالج الرسائل الحرة (للتهيئة) ======

async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعالج الرسائل الحرة - يستخدم في التهيئة"""
    user_id = update.effective_user.id
    state = ONBOARDING_STATE.get(user_id)

    if state == "waiting_for_memorization":
        text = update.message.text.strip()
        async with AsyncSessionLocal() as session:
            user = await logic.get_or_create_user(session, telegram_id=user_id)
            parsed = await logic.parse_memorization_input(text)

            if parsed["page"] is None and "0" not in text and "لا شيء" not in text.lower():
                # فشل التحليل
                await update.message.reply_text(
                    "❌ لم أفهم\\! جرّب أحد الصيغ:\n\n"
                    "• `صفحة 50`\n• `جزء 3`\n• `سورة الكهف`\n• `ختمت القرآن`\n• `0`",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return

            page = parsed["page"] or 0
            if page == 0:
                # تبدأ من الصفحة الأولى
                user.current_page = 1
                user.start_page = 1
                user.total_memorized = 0
                user.onboarding_done = True
                await session.commit()
                del ONBOARDING_STATE[user_id]
                await update.message.reply_text(
                    "✅ *تمّ ضبط الإعدادات\\!*\n\n"
                    "📖 ستبدئين حفظ القرآن من *الصفحة 1* \\(سورة الفاتحة\\)\n\n"
                    "استخدمي /today لعرض مهامك اليومية",
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=main_menu(),
                )
            else:
                # نسجل كل ما حفظته من 1 إلى page
                await logic.set_memorized_up_to(session, user, page)
                del ONBOARDING_STATE[user_id]
                surah = quran_data.page_to_surah(page + 1 if page < quran_data.TOTAL_PAGES else page)
                await update.message.reply_text(
                    f"✅ *ما شاء الله\\!*\n\n"
                    f"📚 سجّلت أنك حفظت إلى *الصفحة {page}*\n"
                    f"📖 صفحتك التالية للحفظ: *الصفحة {page + 1 if page < quran_data.TOTAL_PAGES else page}* \\— سورة {escape_md(surah.name_ar)}\n\n"
                    f"🗓️ سأرسل لك التذكيرات في أوقاتها:\n"
                    f"🌅 الصباح \\(08:00\\): تذكير بقراءة حزبين\n"
                    f"☀️ الظهيرة \\(13:00\\): تذكير بالاستماع لحزب\n"
                    f"🌙 المساء \\(20:00\\): سؤال تفاعلي عن الحفظ\n\n"
                    f"اكتبي /today لعرض مهامك الآن",
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=main_menu(),
                )


# ====== /today ======

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_today(update, context)


async def _show_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعرض كل مهام اليوم"""
    async with AsyncSessionLocal() as session:
        user = await logic.get_or_create_user(session, update.effective_user.id)
        if not user.onboarding_done:
            await start_command(update, context)
            return

        progress = await logic.get_or_create_progress(session, user.id)
        today_review = await logic.get_today_review_pages(session, user.id)
        weekly_review = await logic.get_today_weekly_review(session, user.id)

        # 1. الصباح: قراءة حزبين
        r_start, r_end = logic.get_morning_reading_pages(user)
        read_status = "✅" if progress.reading_done else "⬜"
        juz = quran_data.page_to_juz(r_start)

        # 2. الظهيرة: استماع حزب
        l_start, l_end = logic.get_midday_listening_pages(user)
        listen_status = "✅" if progress.listening_done else "⬜"

        # 3. الحفظ اليومي (الحصن 1)
        memo_page = logic.get_today_memorize_page(user)
        memo_status = "✅" if progress.memorize_done else "⬜"
        memo_surah = quran_data.page_to_surah(memo_page)

        # 4. المراجعة اليومية (الحصن 2)
        review_status = "✅" if progress.daily_review_done else "⬜"

        today_date = date.today().strftime("%Y-%m-%d")

        text = (
            f"📋 *مهام اليوم — {today_date}*\n\n"
            f"🌅 *الصباح \\- القراءة:*\n"
            f"{read_status} حزبين \\(20 صفحة\\): {r_start}–{r_end}\n"
            f"📖 الجزء {juz} — [اقرأ]({quran_data.get_quran_text_url(r_start)})\n\n"
            f"☀️ *الظهيرة \\- الاستماع:*\n"
            f"{listen_status} حزب \\(10 صفحات\\): {l_start}–{l_end}\n"
            f"🎧 [استماع بصوت الحصري]({quran_data.get_page_audio_url(memo_page) or ''})\n\n"
            f"🏰 *الحصون الخمسة:*\n\n"
            f"1️⃣ *الحفظ اليومي*\n"
            f"{memo_status} الصفحة {memo_page} \\— سورة {escape_md(memo_surah.name_ar)}\n\n"
            f"2️⃣ *المراجعة اليومية*\n"
            f"{review_status} {'صفحة ' + str(memo_page) if memo_page else 'لا يوجد'}\n\n"
        )

        # المراجعة الأسبوعية المستحقة اليوم
        if weekly_review:
            text += f"4️⃣ *المراجعة الأسبوعية \\(مستحقة اليوم\\):*\n"
            for wr in weekly_review:
                wr_surah = quran_data.page_to_surah(wr["page"])
                text += f"   • {wr['label']}: صفحة {wr['page']} \\({escape_md(wr_surah.name_ar)}\\)\n"
            text += "\n"

        text += (
            f"💡 استخدمي `/markdone reading` أو `/markdone listening` "
            f"أو `/markdone memorize` لتسجيل الإتمام\n\n"
            f"🔍 اكتبي /fortresses لعرض كل الحصون الخمسة"
        )

    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu(),
            disable_web_page_preview=True,
        )


# ====== /fortresses ======

async def fortresses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعرض الحصون الخمسة بتفصيل"""
    async with AsyncSessionLocal() as session:
        user = await logic.get_or_create_user(session, update.effective_user.id)

        # الحصن 1: الحفظ اليومي
        today_memo = logic.get_today_memorize_page(user)

        # الحصن 2: المراجعة اليومية
        today_review = await logic.get_today_review_pages(session, user.id)

        # الحصن 3: الحفظ الأسبوعي
        weekly_pages = await logic.get_weekly_review_pages(session, user.id)

        # الحصن 4: المراجعة الأسبوعية (المستحقة اليوم)
        weekly_review = await logic.get_today_weekly_review(session, user.id)

        # الحصن 5: المراجعة الشهرية
        now = date.today()
        monthly = await logic.get_monthly_review(session, user.id, now.year, now.month)

    text = (
        "🏰 *طريقة الحصون الخمسة*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ *الحفظ اليومي* \\(الحصن الأول\\)\n"
        f"📄 صفحة اليوم للحفظ: *{today_memo}*\n"
        f"📖 سورة {escape_md(quran_data.page_to_surah(today_memo).name_ar)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"2️⃣ *المراجعة اليومية* \\(الحصن الثاني\\)\n"
    )

    if today_review:
        text += f"📄 راجعي اليوم: {escape_md(', '.join(map(str, today_review)))}\n\n"
    else:
        text += "📄 لم تحفظي شيئاً اليوم بعد\\.\n\n"

    text += (
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"3️⃣ *الحفظ الأسبوعي* \\(الحصن الثالث\\)\n"
        f"📄 آخر 7 أيام: {len(weekly_pages)} صفحة\n"
    )
    if weekly_pages:
        text += f"📋 {escape_md(', '.join(map(str, weekly_pages[:10])))}"
        if len(weekly_pages) > 10:
            text += f" \\(\\+{len(weekly_pages)-10} أخرى\\)"
        text += "\n\n"
    else:
        text += "\n\n"

    text += (
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"4️⃣ *المراجعة الأسبوعية* \\(الحصن الرابع\\)\n"
        f"📅 5 مواعيد: ليلة، ليل، ثلث، اربعاء، خميس\n\n"
    )
    if weekly_review:
        text += "🔍 *المستحقة اليوم:*\n"
        for wr in weekly_review:
            wr_surah = quran_data.page_to_surah(wr["page"])
            text += f"   • {wr['label']}: صفحة {wr['page']} \\({escape_md(wr_surah.name_ar)}\\)\n"
        text += "\n💡 سجلي الإتمام: `/markdone weekly <page>`\n\n"
    else:
        text += "✅ لا توجد مراجعات مستحقة اليوم\\.\n\n"

    text += (
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"5️⃣ *المراجعة الشهرية* \\(الحصن الخامس\\)\n"
        f"📅 شهر {now.month}/{now.year}\n"
    )
    if monthly and monthly.pages_reviewed:
        pages = monthly.pages_reviewed.split(",")
        text += f"📄 {len(pages)} صفحة محفوظة هذا الشهر\n"
        text += f"✅ راجعيها قبل نهاية الشهر\n"
    else:
        text += "📄 لم تحفظي شيئاً هذا الشهر بعد\\.\n"

    if update.message:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu(),
            disable_web_page_preview=True,
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu(),
            disable_web_page_preview=True,
        )


# ====== /progress ======

async def progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as session:
        user = await logic.get_or_create_user(session, update.effective_user.id)
        count = await logic.count_memorized(session, user.id)
        history = await logic.get_memorization_history(session, user.id)

    total = quran_data.TOTAL_PAGES
    percent = (count / total) * 100
    bar = progress_bar(count, total, 20)
    remaining = total - count
    months = remaining // 30 if count > 0 else 0

    recent = history[-5:]
    recent_text = ""
    for m in reversed(recent):
        surah = quran_data.page_to_surah(m.page_number)
        recent_text += f"• صفحة {m.page_number} \\({escape_md(surah.name_ar)}\\) — {m.date_memorized}\n"

    text = (
        f"📊 *تقدمك في حفظ القرآن*\n\n"
        f"`{bar}`\n"
        f"📖 المحفوظ: *{count} / {total}* صفحة \\({percent:.1f}%\\)\n"
        f"⏳ المتبقي: *{remaining}* صفحة \\(~{months} شهر\\)\n\n"
        f"📍 الصفحة الحالية: *{user.current_page}*\n\n"
    )
    if recent_text:
        text += f"📋 *آخر 5 صفحات محفوظة:*\n{recent_text}"

    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu(),
        )


# ====== /setpage ======

async def setpage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ استخدمي: `/setpage <رقم_الصفحة>`\nمثال: `/setpage 25`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    try:
        page = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ الرجاء إدخال رقم صحيح")
        return

    if page < 1 or page > quran_data.TOTAL_PAGES:
        await update.message.reply_text(
            f"❌ الصفحة يجب أن تكون بين 1 و {quran_data.TOTAL_PAGES}"
        )
        return

    async with AsyncSessionLocal() as session:
        user = await logic.get_or_create_user(session, update.effective_user.id)
        user.current_page = page
        if user.start_page == 1 and page != 1:
            user.start_page = page
        user.onboarding_done = True
        await session.commit()

    surah = quran_data.page_to_surah(page)
    await update.message.reply_text(
        f"✅ تم تحديد صفحتك الحالية: *الصفحة {page}*\n"
        f"📖 السورة: {surah.name_ar}\n\n"
        f"استخدمي /today لعرض مهامك",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ====== /markdone ======

async def markdone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ استخدمي أحد الأوامر:\n"
            "• `/markdone reading` — إتمام القراءة\n"
            "• `/markdone listening` — إتمام الاستماع\n"
            "• `/markdone memorize` — إتمام الحفظ\n"
            "• `/markdone daily_review` — إتمام المراجعة اليومية\n"
            "• `/markdone weekly <page>` — إتمام مراجعة أسبوعية لصفحة",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    task = context.args[0].lower()
    async with AsyncSessionLocal() as session:
        user = await logic.get_or_create_user(session, update.effective_user.id)

        if task == "reading":
            await logic.mark_progress_done(session, user.id, "reading")
            label = "القراءة"
        elif task == "listening":
            await logic.mark_progress_done(session, user.id, "listening")
            label = "الاستماع"
        elif task == "memorize":
            await logic.mark_progress_done(session, user.id, "memorize")
            # نسجل الحفظ فعلياً
            await logic.mark_memorized(session, user, user.current_page)
            label = "الحفظ"
        elif task == "daily_review":
            await logic.mark_progress_done(session, user.id, "daily_review")
            label = "المراجعة اليومية"
        elif task == "weekly" and len(context.args) >= 2:
            try:
                page = int(context.args[1])
            except ValueError:
                await update.message.reply_text("❌ رقم الصفحة يجب أن يكون رقمًا")
                return
            # نبحث عن المراجعة الأسبوعية المستحقة اليوم لهذه الصفحة
            weekly_today = await logic.get_today_weekly_review(session, user.id)
            done = False
            for wr in weekly_today:
                if wr["page"] == page:
                    await logic.mark_weekly_review_done(session, wr["review_id"], wr["done_field"])
                    done = True
                    break
            if not done:
                await update.message.reply_text(
                    f"❌ لا توجد مراجعة أسبوعية مستحقة اليوم للصفحة {page}"
                )
                return
            label = f"المراجعة الأسبوعية للصفحة {page}"
        else:
            await update.message.reply_text("❌ نوع غير معروف")
            return

    await update.message.reply_text(
        f"✅ *أحسنت\\!* تم تسجيل إتمام *{escape_md(label)}*\n"
        f"🤲 تقبل الله منك",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ====== /settime ======

async def settime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ استخدمي: `/settime morning 08:00`\n"
            "أو: `/settime midday 13:00`\n"
            "أو: `/settime evening 20:00`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    period, time_str = context.args
    period = period.lower()
    if period not in ("morning", "midday", "evening"):
        await update.message.reply_text(
            "❌ الفترة يجب أن تكون: `morning` أو `midday` أو `evening`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    try:
        h, m = map(int, time_str.split(":"))
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError
        time_str = f"{h:02d}:{m:02d}"
    except (ValueError, IndexError):
        await update.message.reply_text("❌ الوقت بصيغة HH:MM، مثال: 08:00")
        return

    async with AsyncSessionLocal() as session:
        user = await logic.get_or_create_user(session, update.effective_user.id)
        if period == "morning":
            user.morning_time = time_str
        elif period == "midday":
            user.midday_time = time_str
        else:
            user.evening_time = time_str
        await session.commit()

    labels = {"morning": "الصباح", "midday": "الظهيرة", "evening": "المساء"}
    await update.message.reply_text(
        f"✅ تم تحديث وقت تذكير *{labels[period]}*: `{time_str}`\n"
        f"سيتم تطبيق ذلك في الجدولة القادمة",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ====== /timezone ======

async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ استخدمي: `/timezone Africa/Algiers`\n"
            "أو: `/timezone Asia/Riyadh`\n\n"
            "📌 ابحثي عن منطقتك: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    tz = context.args[0]
    try:
        import pytz
        pytz.timezone(tz)
    except Exception:
        await update.message.reply_text("❌ المنطقة الزمنية غير معروفة")
        return

    async with AsyncSessionLocal() as session:
        user = await logic.get_or_create_user(session, update.effective_user.id)
        user.timezone = tz
        await session.commit()

    await update.message.reply_text(
        f"✅ تم تحديث منطقتك الزمنية: `{tz}`",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ====== /reset ======

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as session:
        user = await logic.get_or_create_user(session, update.effective_user.id)
        await session.execute(
            Memorization.__table__.delete().where(Memorization.user_id == user.id)
        )
        await session.execute(
            WeeklyReview.__table__.delete().where(WeeklyReview.user_id == user.id)
        )
        await session.execute(
            MonthlyReview.__table__.delete().where(MonthlyReview.user_id == user.id)
        )
        await session.execute(
            DailyProgress.__table__.delete().where(DailyProgress.user_id == user.id)
        )
        user.current_page = 1
        user.start_page = 1
        user.total_memorized = 0
        user.onboarding_done = False
        await session.commit()

    ONBOARDING_STATE.pop(update.effective_user.id, None)
    await update.message.reply_text(
        "✅ تمت إعادة التهيئة\\.\n\nاكتبي /start للبدء من جديد",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ====== /help ======

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *دليل بوت الحصون الخمسة*\n\n"
        "🏰 *الحصون الخمسة:*\n"
        "1️⃣ الحفظ اليومي — صفحة جديدة كل يوم\n"
        "2️⃣ المراجعة اليومية — مراجعة ما حُفظ اليوم\n"
        "3️⃣ الحفظ الأسبوعي — مراجعة آخر 7 أيام\n"
        "4️⃣ المراجعة الأسبوعية — 5 مرات: ليلة، ليل، ثلث، اربعاء، خميس\n"
        "5️⃣ المراجعة الشهرية — مراجعة كل صفحات الشهر\n\n"
        "⏰ *التذكيرات اليومية:*\n"
        "🌅 08:00 — تذكير بقراءة حزبين\n"
        "☀️ 13:00 — تذكير بالاستماع لحزب\n"
        "🌙 20:00 — سؤال تفاعلي عن الحفظ\n\n"
        "📋 *الأوامر:*\n"
        "/start — البدء\n"
        "/today — مهام اليوم\n"
        "/fortresses — الحصون الخمسة\n"
        "/progress — تقدمك\n"
        "/setpage <رقم> — تحديد صفحتك\n"
        "/settime <morning|midday|evening> <HH:MM> — وقت التذكير\n"
        "/timezone <region> — منطقتك الزمنية\n"
        "/markdone <reading|listening|memorize|daily_review|weekly <page>>\n"
        "/reset — إعادة التهيئة\n"
        "/help — هذا الدليل"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


# ====== معالجة الأزرار ======

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "today":
        await _show_today(update, context)
    elif data == "fortresses":
        await fortresses_command(update, context)
    elif data == "progress":
        await progress_command(update, context)
    elif data == "settings":
        await help_command(update, context)
