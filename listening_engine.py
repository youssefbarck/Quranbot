"""
محرك الاستماع — الحصن الأول (ب. ختمة الاستماع)
=============================================
دورة 60 يومًا، حزب/يوم = 60 حزبًا = ختمة كاملة.
مستقلة تمامًا عن القراءة.
"""
from .. import config
from ..models import User
from .reading_engine import hizb_to_pages


def get_listening_assignment(user: User) -> dict:
    """الاستماع اليومي: حزب واحد (مع لفّ دائري)."""
    hizb = user.listening_hizb_current or 1
    h = max(1, min(hizb, config.QURAN_HIZB_COUNT))
    p_start, p_end = hizb_to_pages(h)

    return {
        "hizb": h,
        "pages_start": p_start,
        "pages_end": p_end,
        "next_hizb": (h % config.QURAN_HIZB_COUNT) + 1,
    }


def advance_listening(user: User) -> bool:
    """تأكيد إنجاز الاستماع — ينتقل للحزب التالي."""
    next_hizb = ((user.listening_hizb_current or 1) % config.QURAN_HIZB_COUNT) + 1
    user.listening_hizb_current = next_hizb

    if next_hizb == 1:
        user.listening_khatmah_count = (user.listening_khatmah_count or 0) + 1
        return True
    return False


def get_listening_cycle_info(user: User) -> dict:
    """معلومات دورة الاستماع."""
    current = user.listening_hizb_current or 1
    completed = current - 1
    total = config.QURAN_HIZB_COUNT
    percent = (completed / total) * 100
    khatmah = user.listening_khatmah_count or 0
    return {
        "current_hizb": current,
        "completed_in_cycle": completed,
        "total_in_cycle": total,
        "percent": round(percent, 1),
        "khatmah_count": khatmah,
        "current_khatmah_number": khatmah + 1,
    }
