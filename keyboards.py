"""
لوحات المفاتيح — ReplyKeyboard ثابتة + Inline لكل شاشة.
"""
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton,
)


# ====== Reply Keyboard الثابتة ======

def main_keyboard() -> ReplyKeyboardMarkup:
    """اللوحة الرئيسية الثابتة — تظهر دائمًا في الأسفل."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🏠 لوحة التحكم"), KeyboardButton("📋 ورد اليوم")],
            [KeyboardButton("📊 تقدمي"), KeyboardButton("⚙️ الإعدادات")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="اضغط أحد الأزرار بالأسفل ✨",
    )


# خريطة نصوص الـ ReplyKeyboard ← أوامر داخلية
KEYBOARD_TEXT_MAP = {
    "🏠 لوحة التحكم": "main_panel",
    "📋 ورد اليوم": "today",
    "📊 تقدمي": "progress",
    "🏰 الحصون الخمسة": "fortresses",
    "⚙️ الإعدادات": "settings",
}


# ====== Inline Keyboards ======

def today_dashboard_inline() -> InlineKeyboardMarkup:
    """أزرار المهام الـ 8 (Toggleable) + إغلاق."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 قراءة", callback_data="task_reading"),
            InlineKeyboardButton("🎧 استماع", callback_data="task_listening"),
        ],
        [
            InlineKeyboardButton("📚 تحضير أسبوعي", callback_data="task_weekly_prep"),
            InlineKeyboardButton("🌙 تحضير ليلي", callback_data="task_nightly_prep"),
        ],
        [
            InlineKeyboardButton("⏱️ تحضير قبلي", callback_data="task_pre_session_prep"),
            InlineKeyboardButton("🆕 حفظ", callback_data="task_memorize"),
        ],
        [
            InlineKeyboardButton("🔄 مراجعة قريب", callback_data="task_near_review"),
            InlineKeyboardButton("🔁 مراجعة بعيد", callback_data="task_far_review"),
        ],
        [
            InlineKeyboardButton("🏰 تفاصيل الحصون", callback_data="fortresses_menu"),
            InlineKeyboardButton("❌ إغلاق", callback_data="close_inline"),
        ],
    ])


def today_dashboard_with_status(plan: dict) -> InlineKeyboardMarkup:
    """أزرار المهام مع علامات ✅/⬜ تعكس الحالة الفعلية."""
    progress = plan["progress"]

    def btn(label: str, task_type: str) -> InlineKeyboardButton:
        done = bool(getattr(progress, f"{task_type}_done", False))
        icon = "✅" if done else "⬜"
        return InlineKeyboardButton(f"{icon} {label}", callback_data=f"task_{task_type}")

    return InlineKeyboardMarkup([
        [
            btn("📖 قراءة", "reading"),
            btn("🎧 استماع", "listening"),
        ],
        [
            btn("📚 تحضير أسبوعي", "weekly_prep"),
            btn("🌙 تحضير ليلي", "nightly_prep"),
        ],
        [
            btn("⏱️ تحضير قبلي", "pre_session_prep"),
            btn("🆕 حفظ", "memorize"),
        ],
        [
            btn("🔄 مراجعة قريب", "near_review"),
            btn("🔁 مراجعة بعيد", "far_review"),
        ],
        [
            InlineKeyboardButton("🏠 لوحة التحكم", callback_data="main_panel"),
            InlineKeyboardButton("🏰 تفاصيل الحصون", callback_data="fortresses_menu"),
        ],
    ])


# ====== لوحة التحكم الشاملة (Main Panel) ======
# تجمع معظم الأساسيات في شاشة واحدة منظّمة بأقسام — مستوحاة من بوتات المخزن الاحترافية.

def main_panel_inline(plan: dict = None) -> InlineKeyboardMarkup:
    """لوحة تحكم شاملة بأقسام منظّمة:
    
    - الإحصائيات السريعة (التقدّم / الالتزام)
    - مهام اليوم (8 أزرار toggleable)
    - الحصون الخمسة (5 أزرار)
    - الإعدادات والتذكيرات (4 أزرار)
    - إجراءات سريعة (3 أزرار)
    """
    rows = []

    # ── القسم 1: المهام السريعة (4 أزرار toggleable في صف واحد مضغوط) ──
    if plan is not None:
        progress = plan["progress"]

        def mini(label: str, task_type: str) -> InlineKeyboardButton:
            done = bool(getattr(progress, f"{task_type}_done", False))
            icon = "✅" if done else "⬜"
            return InlineKeyboardButton(f"{icon} {label}", callback_data=f"task_{task_type}")

        rows.append([
            mini("قراءة", "reading"),
            mini("استماع", "listening"),
            mini("حفظ", "memorize"),
        ])
        rows.append([
            mini("تحضير أ.", "weekly_prep"),
            mini("تحضير ل.", "nightly_prep"),
            mini("تحضير ق.", "pre_session_prep"),
        ])
        rows.append([
            mini("مراجعة ق.", "near_review"),
            mini("مراجعة ب.", "far_review"),
        ])

    # ── القسم 2: ورد اليوم + تفاصيل الحصون ──
    rows.append([
        InlineKeyboardButton("📋 ورد اليوم", callback_data="today_dashboard"),
        InlineKeyboardButton("🏰 الحصون الخمسة", callback_data="fortresses_menu"),
    ])

    # ── القسم 3: الحصون الخمسة (وصول سريع لكل حصن) ──
    rows.append([
        InlineKeyboardButton("1️⃣ التهيئة", callback_data="fortress_1"),
        InlineKeyboardButton("2️⃣ التحضير", callback_data="fortress_2"),
    ])
    rows.append([
        InlineKeyboardButton("3️⃣ الحفظ", callback_data="fortress_3"),
        InlineKeyboardButton("4️⃣ القريب", callback_data="fortress_4"),
        InlineKeyboardButton("5️⃣ البعيد", callback_data="fortress_5"),
    ])

    # ── القسم 4: الإعدادات السريعة ──
    rows.append([
        InlineKeyboardButton("📊 تقدّمي", callback_data="show_progress"),
        InlineKeyboardButton("📜 السجل", callback_data="show_activity_log"),
    ])
    rows.append([
        InlineKeyboardButton("📝 آخر محفوظ", callback_data="set_last_page"),
        InlineKeyboardButton("📊 مقدار يومي", callback_data="set_daily_amount"),
    ])
    rows.append([
        InlineKeyboardButton("📚 مقدار أسبوعي", callback_data="set_weekly_amount"),
        InlineKeyboardButton("⏰ التذكيرات", callback_data="set_reminders"),
    ])

    # ── القسم 5: إجراءات سريعة + المساعدة ──
    rows.append([
        InlineKeyboardButton("💡 اقتراحات ذكية", callback_data="set_suggestions"),
        InlineKeyboardButton("🔔 الإشعارات", callback_data="set_notifications"),
    ])
    rows.append([
        InlineKeyboardButton("❓ المساعدة", callback_data="show_help"),
        InlineKeyboardButton("❌ إغلاق", callback_data="close_inline"),
    ])

    return InlineKeyboardMarkup(rows)


def fortresses_menu_inline() -> InlineKeyboardMarkup:
    """قائمة الحصون الخمسة."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 ورد اليوم", callback_data="today_dashboard")],
        [
            InlineKeyboardButton("🏰 1. التهيئة", callback_data="fortress_1"),
            InlineKeyboardButton("📚 2. التحضير", callback_data="fortress_2"),
        ],
        [
            InlineKeyboardButton("🆕 3. الحفظ", callback_data="fortress_3"),
            InlineKeyboardButton("🔄 4. القريب", callback_data="fortress_4"),
        ],
        [
            InlineKeyboardButton("🛡️ 5. البعيد", callback_data="fortress_5"),
            InlineKeyboardButton("🏠 لوحة التحكم", callback_data="main_panel"),
        ],
    ])


def back_to_today_inline() -> InlineKeyboardMarkup:
    """زر الرجوع لورد اليوم + لوحة التحكم."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 ورد اليوم", callback_data="today_dashboard"),
            InlineKeyboardButton("🏠 لوحة التحكم", callback_data="main_panel"),
        ],
    ])


def onboarding_start_inline() -> InlineKeyboardMarkup:
    """اختيار آخر وجه محفوظ (سور سريعة)."""
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
        [InlineKeyboardButton("✍️ إدخال يدوي", callback_data="ob_manual")],
    ])


def daily_amount_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 وجه/يوم", callback_data="ob_daily_1"),
            InlineKeyboardButton("2 وجه/يوم (موصى)", callback_data="ob_daily_2"),
        ],
        [InlineKeyboardButton("✍️ مخصص", callback_data="ob_daily_custom")],
    ])


def weekly_amount_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("5 أوجه", callback_data="ob_weekly_5"),
            InlineKeyboardButton("7 أوجه (موصى)", callback_data="ob_weekly_7"),
        ],
        [
            InlineKeyboardButton("10 أوجه", callback_data="ob_weekly_10"),
            InlineKeyboardButton("14 وجهًا", callback_data="ob_weekly_14"),
        ],
    ])


def plan_start_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 اليوم (موصى)", callback_data="ob_plan_today")],
        [InlineKeyboardButton("✍️ إدخال تاريخ", callback_data="ob_plan_manual")],
    ])


def reminders_confirm_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ قبول الأوقات الافتراضية", callback_data="ob_reminders_default")],
        [InlineKeyboardButton("⚙️ تخصيص لاحقًا", callback_data="ob_reminders_customize")],
    ])


def settings_panel_inline() -> InlineKeyboardMarkup:
    """لوحة الإعدادات."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 تعديل آخر محفوظ", callback_data="set_last_page"),
            InlineKeyboardButton("📊 مقدار يومي", callback_data="set_daily_amount"),
        ],
        [
            InlineKeyboardButton("📚 مقدار أسبوعي", callback_data="set_weekly_amount"),
            InlineKeyboardButton("📖 حزب القراءة", callback_data="set_reading_hizb"),
        ],
        [
            InlineKeyboardButton("🎧 حزب الاستماع", callback_data="set_listening_hizb"),
            InlineKeyboardButton("🔁 دورة المراجعة البعيدة", callback_data="set_far_cycle"),
        ],
        [
            InlineKeyboardButton("⏰ التذكيرات", callback_data="set_reminders"),
            InlineKeyboardButton("🔔 الإشعارات", callback_data="set_notifications"),
        ],
        [
            InlineKeyboardButton("🏠 لوحة التحكم", callback_data="main_panel"),
            InlineKeyboardButton("❌ إغلاق", callback_data="close_inline"),
        ],
    ])


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
        [InlineKeyboardButton("🏠 لوحة التحكم", callback_data="main_panel")],
    ])


def pre_session_end_inline() -> InlineKeyboardMarkup:
    """زر إنهاء المؤقّت."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ انتهيت، ابدأ الحفظ", callback_data="task_pre_session_prep")],
        [InlineKeyboardButton("🏠 لوحة التحكم", callback_data="main_panel")],
    ])
