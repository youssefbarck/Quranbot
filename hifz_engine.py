"""
محرك الحفظ — الحصن الثالث
========================
القواعد الديترمية:
    next_hifz_page = last_hifz_page + 1  (أو 1 إذا لم يسبق الحفظ)
    إذا daily_hifz_amount = 1: نحفظ الوجه next_hifz_page
    إذا daily_hifz_amount = 2: نحفظ الوجهين next_hifz_page و next_hifz_page+1

بعد تأكيد الحفظ:
    last_hifz_page += daily_hifz_amount
    next_hifz_page = last_hifz_page + 1

لا يتم تحريك الحفظ تلقائيًا إذا فات المستخدم يومًا — يبقى نفس الوجه مطلوبًا.
"""
from .. import config
from ..models import User


def get_today_hifz_assignment(user: User) -> dict:
    """المطلوب حفظه اليوم بناءً على حالة المستخدم."""
    last = user.last_hifz_page or 0
    amount = max(1, user.daily_hifz_amount or 1)
    next_page = last + 1

    if last >= config.QURAN_PAGE_COUNT:
        return {
            "pages": [],
            "start": None,
            "end": None,
            "completed_quran": True,
            "last_hifz_page": last,
            "next_hifz_page": None,
        }

    pages = list(range(next_page, min(next_page + amount, config.QURAN_PAGE_COUNT + 1)))
    end_page = pages[-1] if pages else None

    return {
        "pages": pages,
        "start": pages[0] if pages else None,
        "end": end_page,
        "completed_quran": False,
        "last_hifz_page": last,
        "next_hifz_page": next_page,
    }


def confirm_memorization(user: User) -> dict:
    """تأكيد الحفظ — يحرّك last_hifz_page للأمام بمقدار daily_hifz_amount.
    
    ملاحظة: لا نحذف last_hifz_page أبدًا — فقط نتقدّم للأمام.
    إذا أراد المستخدم التراجع، يُعدّل يدويًا من لوحة "تعديل التقدم".
    """
    assignment = get_today_hifz_assignment(user)
    if assignment["completed_quran"]:
        return {"success": False, "reason": "completed_quran", "message": "أكملتِ القرآن كله 🎉"}

    amount = len(assignment["pages"])
    if amount == 0:
        return {"success": False, "reason": "no_pages", "message": "لا توجد أوجه للحفظ"}

    new_last = assignment["end"]
    user.last_hifz_page = new_last
    user.next_hifz_page = new_last + 1
    # تحديث نطاق التحضير الأسبوعي القادم
    user.weekly_prep_start = new_last + 1
    user.weekly_prep_end = min(config.QURAN_PAGE_COUNT, new_last + (user.weekly_hifz_amount or 7))

    return {
        "success": True,
        "memorized_pages": assignment["pages"],
        "new_last_page": new_last,
        "next_hifz_page": new_last + 1,
    }


def set_last_hifz_page(user: User, page: int) -> dict:
    """تعديل يدوي لآخر وجه محفوظ — يُعيد حساب كل المهام المعتمدة عليه."""
    page = max(0, min(int(page), config.QURAN_PAGE_COUNT))
    user.last_hifz_page = page
    user.next_hifz_page = page + 1 if page < config.QURAN_PAGE_COUNT else page
    user.weekly_prep_start = page + 1 if page < config.QURAN_PAGE_COUNT else page
    user.weekly_prep_end = min(
        config.QURAN_PAGE_COUNT,
        user.weekly_prep_start + (user.weekly_hifz_amount or 7) - 1,
    )
    return {
        "last_hifz_page": user.last_hifz_page,
        "next_hifz_page": user.next_hifz_page,
        "weekly_prep_start": user.weekly_prep_start,
        "weekly_prep_end": user.weekly_prep_end,
    }
