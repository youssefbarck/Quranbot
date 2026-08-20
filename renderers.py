"""
العارضات النصية — كل HTML يُبنى هنا بسلامة (HTML escaping تلقائي).
"""
import html
from datetime import date

import config
from models import User, DailyProgress
import quran_data


def esc(text) -> str:
    """HTML-escape لأي نص."""
    if text is None:
        return ""
    return html.escape(str(text))


def bold(text) -> str:
    return f"<b>{esc(text)}</b>"


def code(text) -> str:
    return f"<code>{esc(text)}</code>"


def fmt_range(start, end) -> str:
    """تنسيق نطاق أوجه."""
    if start is None or end is None:
        return "—"
    if end < start:
        return f"{start}→{quran_data.TOTAL_PAGES} + 1→{end}"
    if start == end:
        return f"{start}"
    return f"{start}–{end}"


def render_today_dashboard(plan: dict) -> str:
    """عرض ورد اليوم — مرتّب بالحصون مع أوضح تعليمات.
    
    التصميم الجديد:
    - ملخّص علوي سريع (التاريخ + الالتزام + شريط الإنجاز)
    - كل حصن بقسم منفصل مع عنوان واضح
    - تعليمات مختصرة تشرح ما يجب فعله
    """
    user: User = plan["user"]
    progress: DailyProgress = plan["progress"]
    completed = plan["completed_count"]

    today_str = date.today().strftime("%Y-%m-%d")
    days_since = max(0, (date.today() - user.plan_start_date).days) + 1 if user.plan_start_date else 0
    streak = user.streak_days or 0

    # شريط إنجاز يومي (8 مهام)
    bar_filled = completed
    bar = "●" * bar_filled + "○" * (8 - bar_filled)

    # بيانات الحصن الأول
    r = plan["reading"]
    r_info = plan["reading_info"]
    l = plan["listening"]
    l_info = plan["listening_info"]

    # بيانات الحصن الثاني
    wp = plan["weekly_prep"]
    np_ = plan["nightly_prep"]
    ps = plan["pre_session"]

    # بيانات الحصن الثالث
    h = plan["hifz"]

    # بيانات الحصن الرابع والخامس
    nr = plan["near_review"]
    fr = plan["far_review"]

    # بناء الرسالة
    parts = [
        f"📋 <b>ورد اليوم — {esc(today_str)}</b>",
        f"يوم رقم {bold(str(days_since))} | streak {bold(str(streak))} يوم",
        f"الإنجاز: <code>{bar}</code> {bold(f'{completed}/8')}",
        "",
    ]

    # ── الحصن الأول: التهيئة ──
    parts.append("📖 <b>الحصن الأول — التهيئة</b>")
    r_hizb_str = '+'.join(str(h_) for h_ in r["hizb_list"])
    parts.append(
        f"   قراءة: حزبان {bold(r_hizb_str)} | الأوجه {bold(fmt_range(r['pages_start'], r['pages_end']))}"
    )
    parts.append(
        f"   استماع: حزب {bold(str(l['hizb']))} | الأوجه {bold(fmt_range(l['pages_start'], l['pages_end']))}"
    )
    parts.append(
        f"   📖 ختمة قراءة #{r_info['current_khatmah_number']} ({r_info['percent']}%) | "
        f"🎧 ختمة استماع #{l_info['current_khatmah_number']} ({l_info['percent']}%)"
    )
    parts.append("")

    # ── الحصن الثاني: التحضير ──
    parts.append("📚 <b>الحصن الثاني — التحضير</b>")
    if wp["start"] is not None:
        parts.append(f"   أسبوعي: الأوجه {bold(fmt_range(wp['start'], wp['end']))} ({wp['amount']} وجه)")
    else:
        parts.append("   أسبوعي: <i>أكملتِ القرآن — لا تحضير مطلوب</i>")
    if np_["pages"]:
        np_desc = f"الوجه {bold(str(np_['start']))}" if len(np_["pages"]) == 1 else f"الأوجه {bold(fmt_range(np_['start'], np_['end']))}"
        parts.append(f"   ليلي: اقرأ {np_desc} قبل النوم")
    else:
        parts.append("   ليلي: <i>لا يوجد</i>")
    if ps["pages"]:
        ps_extra = ""
        if plan["pre_session_active"]:
            ps_extra = f" ⏱️ <i>جاري — {plan['pre_session_elapsed']} دقيقة</i>"
        elif progress.pre_session_duration_min > 0:
            ps_extra = f" (آخر مرة: {progress.pre_session_duration_min} دقيقة)"
        parts.append(f"   قبلي: الوجه {bold(str(ps['start']))} — {config.PRE_SESSION_MINUTES} دقيقة{ps_extra}")
    else:
        parts.append("   قبلي: <i>لا يوجد</i>")
    parts.append("")

    # ── الحصن الثالث: الحفظ ──
    parts.append("🆕 <b>الحصن الثالث — الحفظ الجديد</b>")
    if h["pages"]:
        h_desc = f"الوجه {bold(str(h['start']))}" if len(h["pages"]) == 1 else f"الأوجه {bold(fmt_range(h['start'], h['end']))}"
        surah = quran_data.page_to_surah(h["start"])
        parts.append(f"   احفظ اليوم: {h_desc}")
        if surah:
            parts.append(f"   📖 من سورة {bold(surah.name_ar)} | مقدارك: {user.daily_hifz_amount} وجه/يوم")
    else:
        parts.append("   <i>أكملتِ القرآن كاملًا! 🎉</i>")
    parts.append("")

    # ── الحصن الرابع: مراجعة القريب ──
    parts.append("🔄 <b>الحصن الرابع — مراجعة القريبة</b>")
    if nr["applicable"]:
        parts.append(f"   الأوجه {bold(fmt_range(nr['start'], nr['end']))} — {nr['count']} وجه")
    else:
        parts.append("   <i>سيُفعَّل بعد حفظ أول وجه</i>")
    parts.append("")

    # ── الحصن الخامس: مراجعة البعيد ──
    parts.append("🔁 <b>الحصن الخامس — مراجعة البعيدة</b>")
    if fr["applicable"]:
        parts.append(
            f"   الأوجه {bold(fmt_range(fr['cycle_start'], fr['cycle_end']))} — "
            f"الدورة {fr['current_cycle']}/{fr['total_cycles']}"
        )
    else:
        parts.append("   <i>سيُفعَّل بعد حفظ 20+ وجه</i>")

    # تذييل
    parts.extend([
        "",
        "━━━━━━━━━━━━━━━━",
        "💡 <i>اضغطي ⬜ لتسجيل إنجاز المهمة، أو ✅ للتراجع. التغيّر يظهر فورًا.</i>",
    ])

    return "\n".join(parts)


def render_progress_dashboard(user: User, plan: dict, total_memorized: int) -> str:
    """عرض شاشة التقدم."""
    h = plan["hifz"]
    r_info = plan["reading_info"]
    l_info = plan["listening_info"]
    nr = plan["near_review"]
    fr = plan["far_review"]

    pages_total = config.QURAN_PAGE_COUNT
    percent = (total_memorized / pages_total * 100) if pages_total > 0 else 0
    bar_filled = int(percent / 5)  # 20 حرف
    bar = "█" * bar_filled + "░" * (20 - bar_filled)

    parts = [
        "📊 <b>تقدّمك في حفظ القرآن</b>",
        "",
        f"<code>{bar}</code>",
        f"📖 المحفوظ: <b>{total_memorized} / {pages_total}</b> وجه ({esc(f'{percent:.1f}')}%)",
        f"📍 آخر وجه محفوظ: <b>{user.last_hifz_page or 0}</b>",
        f"🆕 الوجه القادم: <b>{user.next_hifz_page or 1}</b>",
        f"📊 المقدار اليومي: <b>{user.daily_hifz_amount} وجه</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        "📖 <b>دورة القراءة</b>",
        f"   الحزب {r_info['current_hizb']} / {r_info['total_in_cycle']} ({r_info['percent']}%)",
        f"   ختمة #{r_info['current_khatmah_number']} — منجزة: {r_info['khatmah_count']}",
        "",
        "🎧 <b>دورة الاستماع</b>",
        f"   الحزب {l_info['current_hizb']} / {l_info['total_in_cycle']} ({l_info['percent']}%)",
        f"   ختمة #{l_info['current_khatmah_number']} — منجزة: {l_info['khatmah_count']}",
        "",
        "━━━━━━━━━━━━━━━━",
        "🔄 <b>الحصن الرابع (القريب)</b>",
    ]
    if nr["applicable"]:
        parts.append(f"   {nr['count']} وجه قيد المراجعة ({nr['start']}→{nr['end']})")
    else:
        parts.append("   <i>لا ينطبق بعد</i>")

    parts.append("")
    parts.append("🔁 <b>الحصن الخامس (البعيد)</b>")
    if fr["applicable"]:
        parts.append(f"   الدورة {fr['current_cycle']}/{fr['total_cycles']} ({fr['cycle_start']}→{fr['cycle_end']})")
    else:
        parts.append("   <i>لا ينطبق بعد</i>")

    parts.extend([
        "",
        "━━━━━━━━━━━━━━━━",
        f"🔥 الالتزام: <b>{user.streak_days or 0} يوم متتالي</b>",
        f"✅ مهام اليوم: <b>{plan['completed_count']}/8</b>",
        f"⏳ المتبقي اليوم: <b>{8 - plan['completed_count']} مهام</b>",
    ])

    return "\n".join(parts)


def render_fortress_1(plan: dict) -> str:
    """الحصن الأول — التهيئة."""
    r = plan["reading"]
    r_info = plan["reading_info"]
    l = plan["listening"]
    l_info = plan["listening_info"]
    parts = [
        "📖 <b>الحصن الأول — التهيئة المستمرة</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        "📅 <b>القراءة اليوم</b>",
        f"   حزبا القراءة: <b>{'+'.join(str(h) for h in r['hizb_list'])}</b>",
        f"   الأوجه: <b>{fmt_range(r['pages_start'], r['pages_end'])}</b>",
        f"   الدورة: {r_info['current_hizb']}/{r_info['total_in_cycle']} ({r_info['percent']}%)",
        f"   ختمة رقم: <b>{r_info['current_khatmah_number']}</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        "🎧 <b>الاستماع اليوم</b>",
        f"   حزب اليوم: <b>{l['hizb']}</b>",
        f"   الأوجه: <b>{fmt_range(l['pages_start'], l['pages_end'])}</b>",
        f"   الدورة: {l_info['current_hizb']}/{l_info['total_in_cycle']} ({l_info['percent']}%)",
        f"   ختمة رقم: <b>{l_info['current_khatmah_number']}</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        "💡 <i>دورة القراءة 30 يومًا (حزبان/يوم)، ودورة الاستماع 60 يومًا (حزب/يوم). "
        "كل واحدة مستقلة تمامًا عن الأخرى.</i>",
    ]
    return "\n".join(parts)


def render_fortress_2(plan: dict) -> str:
    """الحصن الثاني — التحضير."""
    wp = plan["weekly_prep"]
    np_ = plan["nightly_prep"]
    ps = plan["pre_session"]
    user = plan["user"]
    progress = plan["progress"]
    parts = [
        "📚 <b>الحصن الثاني — التحضير</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        "📅 <b>التحضير الأسبوعي</b>",
    ]
    if wp["start"] is not None:
        parts.append(f"   الأوجه: <b>{fmt_range(wp['start'], wp['end'])}</b>")
        parts.append(f"   المقدار: <b>{user.weekly_hifz_amount} وجه/أسبوع</b>")
    else:
        parts.append("   <i>أكملتِ القرآن</i>")

    parts.extend(["", "━━━━━━━━━━━━━━━━", "🌙 <b>التحضير الليلي</b>"])
    if np_["pages"]:
        if len(np_["pages"]) == 1:
            parts.append(f"   اقرأ الوجه <b>{np_['start']}</b> قبل النوم")
        else:
            parts.append(f"   اقرأ الأوجه <b>{fmt_range(np_['start'], np_['end'])}</b> قبل النوم")
    else:
        parts.append("   <i>لا يوجد</i>")

    parts.extend(["", "━━━━━━━━━━━━━━━━", "⏱️ <b>التحضير القبلي</b>"])
    if ps["pages"]:
        parts.append(f"   الوجه <b>{ps['start']}</b>")
        parts.append(f"   المدة: <b>{config.PRE_SESSION_MINUTES} دقيقة</b>")
        if plan["pre_session_active"]:
            parts.append(f"   <i>⏱️ قيد التشغيل — {plan['pre_session_elapsed']} دقيقة مرّت</i>")
        elif progress.pre_session_duration_min > 0:
            parts.append(f"   <i>آخر مدة: {progress.pre_session_duration_min} دقيقة</i>")
    else:
        parts.append("   <i>لا يوجد</i>")

    parts.extend([
        "",
        "━━━━━━━━━━━━━━━━",
        "💡 <i>اضغطي زر ⏱️ التحضير القبلي في ورد اليوم لبدء المؤقّت، ثم اضغطيه مرة أخرى عند الانتهاء.</i>",
    ])
    return "\n".join(parts)


def render_fortress_3(plan: dict) -> str:
    """الحصن الثالث — الحفظ الجديد."""
    h = plan["hifz"]
    user = plan["user"]
    parts = [
        "🆕 <b>الحصن الثالث — الحفظ الجديد</b>",
        "",
        "━━━━━━━━━━━━━━━━",
    ]
    if h["pages"]:
        parts.append(f"📍 الأوجه المطلوبة: <b>{fmt_range(h['start'], h['end'])}</b>")
        surah = quran_data.page_to_surah(h["start"])
        juz = quran_data.page_to_juz(h["start"])
        parts.append(f"📖 السورة: <b>{esc(surah.name_ar)}</b>")
        parts.append(f"📚 الجزء: <b>{juz}</b>")
        parts.append(f"📊 المقدار: <b>{user.daily_hifz_amount} وجه/يوم</b>")
    else:
        parts.append("🎉 <b>أكملتِ القرآن كاملًا!</b>")

    parts.extend([
        "",
        "━━━━━━━━━━━━━━━━",
        "💡 <b>طريقة الحفظ:</b>",
        "• اقرئي كل آية 10 مرات",
        "• اربطي الآيات حتى تُحفظ الصفحة كاملة",
        "• لا تنتقلي لوجه جديد حتى تُتقني الحالي",
        "• بعد الحفظ، اضغطي 🆕 حفظ في ورد اليوم",
        "",
        "🤲 <i>اللهم اجعل القرآن ربيع قلوبنا</i>",
    ])
    return "\n".join(parts)


def render_fortress_4(plan: dict) -> str:
    """الحصن الرابع — مراجعة القريب."""
    nr = plan["near_review"]
    parts = [
        "🔄 <b>الحصن الرابع — مراجعة القريب</b>",
        "",
        "━━━━━━━━━━━━━━━━",
    ]
    if nr["applicable"]:
        parts.append(f"📍 الأوجه <b>{fmt_range(nr['start'], nr['end'])}</b> (آخر 20 وجه محفوظ)")
        start_surah = quran_data.page_to_surah(nr["start"])
        end_surah = quran_data.page_to_surah(nr["end"])
        parts.append(f"📖 السور: {esc(start_surah.name_ar)} ← {esc(end_surah.name_ar)}")
        parts.append(f"📊 العدد: <b>{nr['count']} وجه</b>")
        parts.extend([
            "",
            "💡 <i>تُراجع يومياً كاملة. هذا أقوى الحصون ضد النسيان.</i>",
            "🤲 <i>اقرئيها من المصحف ثم من ذاكرتك</i>",
        ])
    else:
        parts.append("⏸️ <i>لا ينطبق الآن — سيُفعَّل بعد حفظ أول وجه</i>")
    return "\n".join(parts)


def render_fortress_5(plan: dict) -> str:
    """الحصن الخامس — مراجعة البعيد."""
    fr = plan["far_review"]
    parts = [
        "🛡️ <b>الحصن الخامس — مراجعة البعيد</b>",
        "",
        "━━━━━━━━━━━━━━━━",
    ]
    if fr["applicable"]:
        parts.append(f"📍 الأوجه <b>{fmt_range(fr['cycle_start'], fr['cycle_end'])}</b>")
        start_surah = quran_data.page_to_surah(fr["cycle_start"])
        end_surah = quran_data.page_to_surah(fr["cycle_end"])
        parts.append(f"📖 السور: {esc(start_surah.name_ar)} ← {esc(end_surah.name_ar)}")
        parts.append(f"🔄 الدورة: <b>{fr['current_cycle']}/{fr['total_cycles']}</b>")
        parts.extend([
            "",
            "💡 <i>تُقسَّم على أيام الأسبوع. الهدف التذكير لا الإتقان التام.</i>",
            "✅ عند إتمام الدورة، اضغطي زر 🔁 مراجعة بعيد لانتقال للدورة التالية.",
        ])
    else:
        parts.append("⏸️ <i>لا ينطبق الآن — سيُفعَّل بعد حفظ 20+ وجه</i>")
    return "\n".join(parts)


def render_settings_panel(user: User, settings_list: list) -> str:
    """عرض لوحة الإعدادات."""
    parts = [
        "⚙️ <b>الإعدادات</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        f"📍 آخر وجه محفوظ: <b>{user.last_hifz_page or 0}</b>",
        f"📊 المقدار اليومي: <b>{user.daily_hifz_amount} وجه</b>",
        f"📚 المقدار الأسبوعي: <b>{user.weekly_hifz_amount} وجه</b>",
        f"📖 حزب القراءة الحالي: <b>{user.reading_hizb_current}</b>",
        f"🎧 حزب الاستماع الحالي: <b>{user.listening_hizb_current}</b>",
        f"🔔 الإشعارات: <b>{'مفعّلة' if user.notifications_enabled else 'معطّلة'}</b>",
        f"🌍 المنطقة الزمنية: <b>{esc(user.timezone)}</b>",
        "",
        "━━━━━━━━━━━━━━━━",
        "⏰ <b>أوقات التذكيرات:</b>",
    ]
    import config
    labels = config.REMINDER_LABELS_AR
    settings_by_type = {s.reminder_type: s for s in settings_list}
    for rtype in config.REMINDER_TYPES:
        s = settings_by_type.get(rtype)
        time_str = s.reminder_time if s else config.DEFAULT_REMINDER_TIMES[rtype]
        enabled = "✅" if (s and s.enabled) else "❌"
        parts.append(f"   {enabled} {labels[rtype]}: <code>{esc(time_str)}</code>")
    parts.extend(["", "👇 اختر ما تريد تعديله:"])
    return "\n".join(parts)


def render_activity_log(logs: list) -> str:
    """عرض سجل النشاط."""
    if not logs:
        return "📅 <b>سجل النشاط</b>\n\n<i>لا يوجد نشاط مسجَّل بعد.</i>"
    parts = ["📅 <b>سجل النشاط (آخر 14 يومًا)</b>", ""]
    current_date = None
    for log in logs:
        if log.log_date != current_date:
            current_date = log.log_date
            parts.append(f"\n━━ <b>{esc(log.log_date.strftime('%Y-%m-%d'))}</b> ━━")
        time_str = log.log_time.strftime("%H:%M") if log.log_time else ""
        parts.append(f"  {time_str} — {esc(log.event_type)} {esc(log.description or '')}")
    return "\n".join(parts)


def render_suggestions(suggestions: list) -> str:
    """عرض الاقتراحات الذكية."""
    if not suggestions:
        return "💡 <b>اقتراحات ذكية</b>\n\n<i>لا توجد اقتراحات حالياً — استمر في الالتزام! 🌟</i>"
    parts = ["💡 <b>اقتراحات ذكية بناءً على سلوكك</b>", ""]
    for s in suggestions:
        parts.append(f"• {esc(s)}")
    parts.extend(["", "<i>لن تُطبَّق هذه الاقتراحات تلقائيًا — القرار لك.</i>"])
    return "\n".join(parts)


def render_main_panel(user: User, plan: dict, total_memorized: int) -> str:
    """لوحة التحكم — نفس ورد اليوم (تم الدمج لتقليل التعقيد)."""
    return render_today_dashboard(plan)


def render_help() -> str:
    """شاشة المساعدة — مبسّطة ومباشرة."""
    return (
        "❓ <b>كيف تستخدمين البوت؟</b>\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ <b>كل يوم يظهر وردك</b> (قراءة + استماع + حفظ + مراجعة)\n\n"
        "2️⃣ <b>اضغطي زر ⬜</b> عند إنجاز أي مهمة — يتحوّل لـ ✅\n\n"
        "3️⃣ <b>اضغطي زر ✅</b> مرة أخرى للتراجع (إذا ضغطتِ بالخطأ)\n\n"
        "4️⃣ <b>القراءة والاستماع يتقدّمان</b> عند الضغط على ⬜ — كل يوم حزب جديد!\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🏰 <b>الحصون الخمسة (باختصار):</b>\n"
        "   1️⃣ التهيئة — قراءة 2 حزب + استماع 1 حزب يوميًا\n"
        "   2️⃣ التحضير — أسبوعي + ليلي + قبلي (15 د)\n"
        "   3️⃣ الحفظ — الوجه الجديد\n"
        "   4️⃣ مراجعة قريبة — آخر 20 وجه\n"
        "   5️⃣ مراجعة بعيدة — 40 وجه/دورة\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <b>يمكنك أيضًا الكتابة بالعربية:</b>\n"
        "   «وش نحفظ اليوم؟» → ورد اليوم\n"
        "   «وين وصلت؟» → التقدّم\n"
        "   «حفظت الوجه 41» → تسجيل الحفظ\n"
        "   «قريت الورد» → تسجيل القراءة\n\n"
        "<i>🤲 اللهم اجعل القرآن ربيع قلوبنا</i>"
    )
