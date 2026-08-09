"""
محرك التحضير — الحصن الثاني (أسبوعي + ليلي + قبلي)
==================================================

التحضير الأسبوعي:
    - نطاق الأوجه التي سيحفظها المستخدم خلال الأسبوع القادم (وليس الأسبوع الحالي)
    - محسوب ديناميكيًا من next_hifz_page + weekly_hifz_amount
    - يُحدَّث تلقائيًا عند تغيير weekly_hifz_amount أو تأكيد الحفظ

    القاعدة الحسابية:
        this_week_start = last_hifz_page + 1        (= next_hifz_page)
        this_week_end   = this_week_start + weekly_hifz_amount - 1
        weekly_prep_start = this_week_start + weekly_hifz_amount
        weekly_prep_end   = weekly_prep_start + weekly_hifz_amount - 1

    مثال: last_hifz=127, weekly=5
        → هذا الأسبوع: 128 → 132
        → تحضير الأسبوع القادم: 133 → 137

التحضير الليلي:
    - الأوجه المطلوب حفظها غدًا (= مهمة الحفظ القادمة)
    - "قبل النوم، اقرأ الوجه X"

التحضير القبلي:
    - قبل جلسة الحفظ مباشرة
    - مؤقت 15 دقيقة، ثم "ابدأ الحفظ"
"""
from datetime import datetime, timedelta

import config
from models import User


def get_weekly_prep_range(user: User) -> dict:
    """نطاق التحضير الأسبوعي = أوجه الأسبوع القادم المتوقَّع حفظها.

    مهم: التحضير دائمًا للأسبوع القادم، وليس للأسبوع الحالي.
    الأسبوع الحالي يبدأ من next_hifz_page، والأسبوع القادم يبدأ من
    next_hifz_page + weekly_hifz_amount.

    مثال: last_hifz=40, weekly=7
        → هذا الأسبوع: 41 → 47
        → تحضير الأسبوع القادم: 48 → 54

    مثال: last_hifz=127, weekly=5  (حالة المستخدم)
        → هذا الأسبوع: 128 → 132
        → تحضير الأسبوع القادم: 133 → 137  ✅
    """
    last = user.last_hifz_page or 0
    weekly_amount = user.weekly_hifz_amount or config.DEFAULT_WEEKLY_HIFZ_AMOUNT

    if last >= config.QURAN_PAGE_COUNT:
        return {"start": None, "end": None, "amount": 0, "completed_quran": True}

    # بداية الأسبوع الحالي = الوجه القادم للحفظ
    this_week_start = last + 1
    # بداية الأسبوع القادم = بعد تجاوز كامل مقدار الحفظ الأسبوعي الحالي
    start = this_week_start + weekly_amount

    # إذا تجاوز البدء نهاية القرآن، فلا تحضير متبقٍّ
    if start > config.QURAN_PAGE_COUNT:
        return {
            "start": None,
            "end": None,
            "amount": 0,
            "completed_quran": False,
            "note": "no_next_week_pages",
        }

    end = min(config.QURAN_PAGE_COUNT, start + weekly_amount - 1)
    amount = end - start + 1
    return {
        "start": start,
        "end": end,
        "amount": amount,
        "completed_quran": False,
    }


def get_nightly_prep_pages(user: User) -> dict:
    """أوجه الغد = مهمة الحفظ القادمة.
    
    "قبل النوم: اقرأ الوجه X (أو الوجهين X و Y) استعدادًا لحفظه غدًا."
    """
    last = user.last_hifz_page or 0
    amount = max(1, user.daily_hifz_amount or 1)

    if last >= config.QURAN_PAGE_COUNT:
        return {"pages": [], "start": None, "end": None, "completed_quran": True}

    next_page = last + 1
    pages = list(range(next_page, min(next_page + amount, config.QURAN_PAGE_COUNT + 1)))
    return {
        "pages": pages,
        "start": pages[0] if pages else None,
        "end": pages[-1] if pages else None,
        "amount": len(pages),
        "completed_quran": False,
    }


def get_pre_session_prep_page(user: User) -> dict:
    """وجه التحضير القبلي = نفس وجه الحفظ القادم.
    
    يبدأ المستخدم المؤقّت (15 دقيقة)، ثم يبدأ الحفظ.
    """
    nightly = get_nightly_prep_pages(user)
    return nightly  # نفس الأوجه


def start_pre_session_timer(user: User) -> datetime:
    """بدء مؤقّت التحضير القبلي."""
    user.pre_session_started_at = datetime.utcnow()
    return user.pre_session_started_at


def end_pre_session_timer(user: User) -> int:
    """إنهاء المؤقّت — يُعيد عدد الدقائق المنقضية."""
    if not user.pre_session_started_at:
        return 0
    duration = (datetime.utcnow() - user.pre_session_started_at).total_seconds() / 60.0
    minutes = int(duration)
    user.pre_session_started_at = None
    return minutes


def get_pre_session_elapsed_minutes(user: User) -> int:
    """الوقت المنقضي منذ بدء المؤقّت (دقائق)."""
    if not user.pre_session_started_at:
        return 0
    duration = (datetime.utcnow() - user.pre_session_started_at).total_seconds() / 60.0
    return int(duration)


def is_pre_session_active(user: User) -> bool:
    """هل المؤقّت قيد التشغيل؟"""
    return user.pre_session_started_at is not None
