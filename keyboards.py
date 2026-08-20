"""
لوحات المفاتيح — ReplyKeyboard ثابتة + Inline لكل شاشة.
============================================================
التصميم الجديد: مبسّط ومجمّع بالحصون — كل زرّ واضح ومفهوم.
"""
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton,
)


# ====== Reply Keyboard الثابتة (الشريط السفلي دائمًا) ======

def main_keyboard() -> ReplyKeyboardMarkup:
    """اللوحة الرئيسية الثابتة — 4 أزرار فقط في الأسفل.
    
    فلسفة التصميم:
    - ورد اليوم = الشاشة الأساسية (أكثر شيء يُستخدم)
    - تقدمي = نظرة سريعة على الإنجاز
    - الحصون = التفاصيل لمن يريدها
    - الإعدادات = نادرًا ما تُستخدم
    """
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📋 ورد اليوم"), KeyboardButton("📊 تقدمي")],
            [KeyboardButton("🏰 الحصون"), KeyboardButton("⚙️ الإعدادات")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="اضغط أحد الأزرار بالأسفل ✨",
    )


# خريطة نصوص الـ ReplyKeyboard ← أوامر داخلية
KEYBOARD_TEXT_MAP = {
    "📋 ورد اليوم": "today",
    "📊 تقدمي": "progress",
    "🏰 الحصون": "fortresses",
    "🏰 الحصون الخمسة": "fortresses",
    "⚙️ الإعدادات": "settings",
}


# ====== Inline Keyboards ======


def today_dashboard_with_status(plan: dict) -> InlineKeyboardMarkup:
    """أزرار ورد اليوم — مصمّمة لتكون واضحة لأي مستخدم.
    
    فلسفة التصميم:
    - كل مهمة تظهر باسمها الكامل (بدون اختصارات)
    - القراءة والاستماع يظهران مع رقم الحزب (المستخدم يرى التغيّر يوميًا)
    - الأزرار مجمّعة بالحصن الذي تنتمي إليه
    - أزرار التنقل في الأسفل فقط (3 أزرار)
    """
    progress = plan["progress"]
    reading = plan["reading"]
    listening = plan["listening"]

    def btn(label: str, task_type: str) -> InlineKeyboardButton:
        done = bool(getattr(progress, f"{task_type}_done", False))
        icon = "✅" if done else "⬜"
        return InlineKeyboardButton(f"{icon} {label}", callback_data=f"task_{task_type}")

    # أرقام الأحزاب للقراءة والاستماع
    r_h1, r_h2 = reading["hizb_list"]
    l_h = listening["hizb"]

    return InlineKeyboardMarkup([
        # ── الحصن الأول: التهيئة ──
        [
            btn(f"قراءة — حزبان {r_h1}+{r_h2}", "reading"),
            btn(f"استماع — حزب {l_h}", "listening"),
        ],
        # ── الحصن الثاني: التحضير ──
        [
            btn("تحضير أسبوعي 📚", "weekly_prep"),
            btn("تحضير ليلي 🌙", "nightly_prep"),
        ],
        [
            btn("تحضير قبلي ⏱️", "pre_session_prep"),
        ],
        # ── الحصن الثالث: الحفظ ──
        [
            btn("حفظ الوجه الجديد 🆕", "memorize"),
        ],
        # ── الحصن الرابع والخامس: المراجعة ──
        [
            btn("مراجعة قريبة (20 وجه) 🔄", "near_review"),
        ],
        [
            btn("مراجعة بعيدة (40 وجه) 🔁", "far_review"),
        ],
        # ── التنقل (فقط 3 أزرار) ──
        [
            InlineKeyboardButton("🏰 الحصون الخمسة", callback_data="fortresses_menu"),
            InlineKeyboardButton("📊 تقدمي", callback_data="show_progress"),
            InlineKeyboardButton("⚙️ إعدادات", callback_data="settings"),
        ],
    ])


def today_dashboard_inline() -> InlineKeyboardMarkup:
    """أزرار المهام الـ 8 بدون حالة (تُستخدم أحيانًا كـ fallback)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬜ قراءة", callback_data="task_reading"),
            InlineKeyboardButton("⬜ استماع", callback_data="task_listening"),
        ],
        [
            InlineKeyboardButton("⬜ تحضير أسبوعي 📚", callback_data="task_weekly_prep"),
            InlineKeyboardButton("⬜ تحضير ليلي 🌙", callback_data="task_nightly_prep"),
        ],
        [
            InlineKeyboardButton("⬜ تحضير قبلي ⏱️", callback_data="task_pre_session_prep"),
            InlineKeyboardButton("⬜ حفظ الوجه 🆕", callback_data="task_memorize"),
        ],
        [
            InlineKeyboardButton("⬜ مراجعة قريبة 🔄", callback_data="task_near_review"),
            InlineKeyboardButton("⬜ مراجعة بعيدة 🔁", callback_data="task_far_review"),
        ],
    ])


# ====== لوحة التحكم الشاملة (مبسّطة) ======

def main_panel_inline(plan: dict = None) -> InlineKeyboardMarkup:
    """لوحة تحكم مبسّطة — نفس ورد اليوم مع أزرار إضافية.
    
    التغيير الجوهري: بدل 17 صفاً من الأزرار، نستخدم نفس تصميم ورد اليوم
    مع إضافة زرّين فقط (السجل + المساعدة).
    """
    if plan is not None:
        return today_dashboard_with_status(plan)
    # بدون خطة (حالة نادرة)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 ورد اليوم", callback_data="today_dashboard")],
        [InlineKeyboardButton("📊 تقدمي", callback_data="show_progress")],
        [InlineKeyboardButton("🏰 الحصون الخمسة", callback_data="fortresses_menu")],
        [InlineKeyboardButton("❓ المساعدة", callback_data="show_help")],
    ])


# ====== الحصون الخمسة ======

def fortresses_menu_inline() -> InlineKeyboardMarkup:
    """قائمة الحصون الخمسة — كل حصن مع وصف مختصر في الزر."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 1. التهيئة (قراءة + استماع)", callback_data="fortress_1"),
        ],
        [
            InlineKeyboardButton("📚 2. التحضير (أسبوعي + ليلي + قبلي)", callback_data="fortress_2"),
        ],
        [
            InlineKeyboardButton("🆕 3. الحفظ الجديد", callback_data="fortress_3"),
        ],
        [
            InlineKeyboardButton("🔄 4. مراجعة قريبة (20 وجه)", callback_data="fortress_4"),
        ],
        [
            InlineKeyboardButton("🔁 5. مراجعة بعيدة (40 وجه)", callback_data="fortress_5"),
        ],
        [
            InlineKeyboardButton("🔙 الرجوع لورد اليوم", callback_data="today_dashboard"),
        ],
    ])


def back_to_today_inline() -> InlineKeyboardMarkup:
    """زر الرجوع لورد اليوم — بسيط."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 ورد اليوم", callback_data="today_dashboard"),
        ],
    ])


# ====== Onboarding ======

def onboarding_start_inline() -> InlineKeyboardMarkup:
    """اختيار آخر وجه محفوظ — مصمّم بوضوح."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌱 لم أحفظ شيئًا بعد", callback_data="ob_0")],
        [
            InlineKeyboardButton("📖 البقرة", callback_data="ob_surah_2"),
            InlineKeyboardButton("📖 آل عمران", callback_data="ob_surah_3"),
        ],
        [
            InlineKeyboardButton("📖 النساء", callback_data="ob_surah_4"),
            InlineKeyboardButton("📖 المائدة", callback_data="ob_surah_5"),
        ],
        [
            InlineKeyboardButton("📖 الكهف", callback_data="ob_surah_18"),
            InlineKeyboardButton("📖 يس", callback_data="ob_surah_36"),
        ],
        [
            InlineKeyboardButton("📖 تبارك", callback_data="ob_surah_67"),
            InlineKeyboardButton("📖 عمَّ", callback_data="ob_surah_78"),
        ],
        [InlineKeyboardButton("✅ ختمت القرآن كاملًا", callback_data="ob_all")],
        [InlineKeyboardButton("✍️ إدخال يدوي (اكتب رقم الصفحة)", callback_data="ob_manual")],
    ])


def daily_amount_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 وجه / يوم", callback_data="ob_daily_1"),
            InlineKeyboardButton("2 وجه / يوم ⭐ موصى به", callback_data="ob_daily_2"),
        ],
        [InlineKeyboardButton("✍️ أريد مقدارًا آخر", callback_data="ob_daily_custom")],
    ])


def weekly_amount_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("5 أوجه / أسبوع", callback_data="ob_weekly_5"),
            InlineKeyboardButton("7 أوجه ⭐ موصى به", callback_data="ob_weekly_7"),
        ],
        [
            InlineKeyboardButton("10 أوجه / أسبوع", callback_data="ob_weekly_10"),
            InlineKeyboardButton("14 وجه / أسبوع", callback_data="ob_weekly_14"),
        ],
    ])


def plan_start_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 أبدأ اليوم ⭐", callback_data="ob_plan_today")],
        [InlineKeyboardButton("✍️ تاريخ آخر", callback_data="ob_plan_manual")],
    ])


def reminders_confirm_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ الأوقات الافتراضية تناسبني", callback_data="ob_reminders_default")],
        [InlineKeyboardButton("⚙️ أريد تعديلها لاحقًا", callback_data="ob_reminders_customize")],
    ])


# ====== الإعدادات (مبسّطة) ======

def settings_panel_inline() -> InlineKeyboardMarkup:
    """لوحة الإعدادات — فقط ما يحتاجه المستخدم العادي.
    
    تمت إزالة الأزرار التقنية (حزب القراءة، حزب الاستماع، دورة المراجعة)
    لأنها تُعدَّل تلقائيًا ولا يحتاج المستخدم التدخل فيها يدويًا.
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 آخر وجه محفوظ", callback_data="set_last_page"),
            InlineKeyboardButton("📊 مقدار الحفظ اليومي", callback_data="set_daily_amount"),
        ],
        [
            InlineKeyboardButton("📚 مقدار الحفظ الأسبوعي", callback_data="set_weekly_amount"),
        ],
        [
            InlineKeyboardButton("⏰ أوقات التذكيرات", callback_data="set_reminders"),
            InlineKeyboardButton("🔔 تفعيل/تعطيل الإشعارات", callback_data="set_notifications"),
        ],
        [
            InlineKeyboardButton("🔙 الرجوع لورد اليوم", callback_data="today_dashboard"),
        ],
    ])


# ====== أدوات عامة ======

def confirm_inline(action: str, label: str) -> InlineKeyboardMarkup:
    """زر تأكيد قبل تعديل مهم."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"✅ نعم، {label}", callback_data=f"confirm_{action}"),
            InlineKeyboardButton("❌ إلغاء", callback_data="cancel_action"),
        ],
    ])


def pre_session_start_inline() -> InlineKeyboardMarkup:
    """زر بدء مؤقّت التحضير القبلي."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ بدء التحضير (15 دقيقة)", callback_data="start_pre_session")],
        [InlineKeyboardButton("🔙 الرجوع", callback_data="today_dashboard")],
    ])


def pre_session_end_inline() -> InlineKeyboardMarkup:
    """زر إنهاء المؤقّت."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ انتهيت من التحضير", callback_data="task_pre_session_prep")],
        [InlineKeyboardButton("🔙 الرجوع", callback_data="today_dashboard")],
    ])
