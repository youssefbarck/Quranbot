"""
محرك القراءة — الحصن الأول (أ. ختمة القراءة)
==========================================
دورة 30 يومًا، حزبان/يوم = 60 حزبًا = ختمة كاملة.
يبدأ من الحزب 1، بعد الحزب 60 يعود للحزب 1.
يحفظ موضع القراءة الحالي بشكل دائم في user.reading_hizb_current.
"""
from .. import config
from ..models import User


def hizb_to_pages(hizb: int) -> tuple[int, int]:
    """حوّل رقم الحزب (1-60) إلى نطاق الأوجه (10 أوجه لكل حزب)."""
    hizb = max(1, min(hizb, config.QURAN_HIZB_COUNT))
    start = (hizb - 1) * config.DAILY_LISTENING_PAGES + 1
    end = start + config.DAILY_LISTENING_PAGES - 1
    return start, end


def get_reading_assignment(user: User) -> dict:
    """الورد اليومي للقراءة: حزبان متتاليان (مع لفّ دائري)."""
    start_hizb = user.reading_hizb_current or 1
    h1 = max(1, min(start_hizb, config.QURAN_HIZB_COUNT))
    h2 = (h1 % config.QURAN_HIZB_COUNT) + 1  # حزب اليوم التالي (مع لفّ)

    p1_start, p1_end = hizb_to_pages(h1)
    p2_start, p2_end = hizb_to_pages(h2)

    return {
        "hizb_list": [h1, h2],
        "pages_start": p1_start,
        "pages_end": p2_end,
        "current_hizb": h1,
        "next_hizb": (h2 % config.QURAN_HIZB_COUNT) + 1,
    }


def advance_reading(user: User) -> bool:
    """تأكيد إنجاز القراءة — ينتقل للحزب التالي (مع لفّ بعد 60).
    
    قراءة اليوم = current_hizb و second_hizb (الذي قد يلتف).
    إذا تضمّنت قراءة اليوم الحزب 60، تُحسب ختمة كاملة.
    """
    current = user.reading_hizb_current or 1
    # الحزبان اللذان قُرئا اليوم: current و (current % 60) + 1
    second_hizb = (current % config.QURAN_HIZB_COUNT) + 1
    # إذا ضمّت القراءة الحزب 60 → ختمة كاملة
    completed_khatmah = (current == config.QURAN_HIZB_COUNT) or (second_hizb == config.QURAN_HIZB_COUNT)

    # الحزب التالي = current + 2 (مع لفّ)
    next_hizb = ((current + config.DAILY_READING_HIZB - 1) % config.QURAN_HIZB_COUNT) + 1
    user.reading_hizb_current = next_hizb

    if completed_khatmah:
        user.reading_khatmah_count = (user.reading_khatmah_count or 0) + 1
        return True
    return False


def get_reading_cycle_info(user: User) -> dict:
    """معلومات الدورة: أي حزب نحن فيه، نسبة الإنجاز في الختمة الحالية."""
    current = user.reading_hizb_current or 1
    completed_hizb = current - 1
    total_hizb = config.QURAN_HIZB_COUNT
    percent = (completed_hizb / total_hizb) * 100
    khatmah_count = user.reading_khatmah_count or 0
    return {
        "current_hizb": current,
        "completed_in_cycle": completed_hizb,
        "total_in_cycle": total_hizb,
        "percent": round(percent, 1),
        "khatmah_count": khatmah_count,
        "current_khatmah_number": khatmah_count + 1,
    }
