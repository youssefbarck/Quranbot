"""
محرك التحضير — الحصن الثاني (أسبوعي + ليلي + قبلي)
==================================================

التحضير الأسبوعي:
    - نطاق الأوجه التي سيحفظها المستخدم خلال الأسبوع القادم
    - محسوب ديناميكيًا من last_hifz_page + daily_hifz_amount
    - يُحدَّث تلقائيًا عند تغيير daily_hifz_amount

التحضير الليلي:
    - الأوجه المطلوب حفظها غدًا (= مهمة الحفظ القادمة)
    - "قبل النوم، اقرأ الوجه X"

التحضير القبلي:
    - قبل جلسة الحفظ مباشرة
    - مؤقت 15 دقيقة، ثم "ابدأ الحفظ"
"""
from datetime import datetime, timedelta

from .. import config
from ..models import User


def get_weekly_prep_range(user: User) -> dict:
    """نطاق التحضير الأسبوعي = أوجه الأسبوع القادم المتوقَّع حفظها.
    
    مثال: last_hifz=40, daily_amount=1, weekly_amount=7
        → 41→47 (سيلي الحفظ خلال الأسبوع القادم)
    مثال: last_hifz=40, daily_amount=2, weekly_amount=14
        → 41→54
    """
    last = user.last_hifz_page or 0
    weekly_amount = user.weekly_hifz_amount or config.DEFAULT_WEEKLY_HIFZ_AMOUNT

    if last >= config.QURAN_PAGE_COUNT:
        return {"start": None, "end": None, "amount": 0, "completed_quran": True}

    start = last + 1
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
