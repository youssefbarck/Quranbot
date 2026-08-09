"""
محرك المراجعات — الحصن الرابع (القريب) + الحصن الخامس (البعيد)
=============================================================

الحصن الرابع: نافذة متحركة آخر 20 وجهًا من المحفوظ.
    near_start = max(1, last_hifz_page - 19)
    near_end   = last_hifz_page

الحصن الخامس: 40 وجهًا لكل دورة، مستقلة عن الحفظ.
    نحفظ حالة الدورة في جدول FarReviewCycle.
    عند الإنتهاء، ننتقل للدورة التالية (ننزل في الأرقام).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import User, FarReviewCycle, MemorizationLog
from hifz_engine import get_today_hifz_assignment


# ====== الحصن الرابع: مراجعة القريب ======

def get_near_review_range(user: User) -> dict:
    """نطاق مراجعة القريب = آخر 20 وجهًا من المحفوظ.
    
    إذا كان المحفوظ أقل من 20 وجه، يبدأ من 1.
    إذا لم يحفظ المستخدم شيئًا، يعود None.
    """
    last = user.last_hifz_page or 0
    if last == 0:
        return {"applicable": False, "start": None, "end": None, "count": 0}

    near_start = max(1, last - (config.NEAR_REVISION_SIZE - 1))
    near_end = last
    count = near_end - near_start + 1
    return {
        "applicable": True,
        "start": near_start,
        "end": near_end,
        "count": count,
    }


# ====== الحصن الخامس: مراجعة البعيد ======

def _compute_total_far_cycles(last_hifz_page: int) -> int:
    """عدد دورات المراجعة البعيدة الكلية.
    
    القاعدة: كل دورة = 40 وجه. الدورة 1 = الأحدث (آخر 40 محفوظ).
    دورات البعيد تبدأ من آخر وجه محفوظ وتنزل للوراء.
    مثال: last=120 → 3 دورات (81→120, 41→80, 1→40)
    مثال: last=40 → 1 دورة (1→40)
    مثال: last=25 → 1 دورة (1→25)
    """
    if last_hifz_page <= 0:
        return 0
    cycles = (last_hifz_page + config.FAR_REVISION_SIZE - 1) // config.FAR_REVISION_SIZE
    return cycles


def _compute_cycle_range(last_hifz_page: int, cycle_number: int) -> tuple[int, int]:
    """احسب نطاق دورة بعيدة معيّنة.
    
    الترتيب: الدورة 1 = الأحدث (تنتهي عند last_hifz_page)، الدورة N = الأقدم (تبدأ من 1).
    
    مثال: last=120، FAR_SIZE=40
      الدورة 1 = 81→120  (الأحدث)
      الدورة 2 = 41→80
      الدورة 3 = 1→40    (الأقدم)
    """
    if last_hifz_page <= 0:
        return (None, None)

    # نهاية الدورة N = last - (N-1) * 40
    end_of_cycle = last_hifz_page - (cycle_number - 1) * config.FAR_REVISION_SIZE
    start_of_cycle = end_of_cycle - config.FAR_REVISION_SIZE + 1

    # قص على الحدود
    start_of_cycle = max(1, start_of_cycle)
    end_of_cycle = max(start_of_cycle, end_of_cycle)

    return (start_of_cycle, end_of_cycle)


async def get_far_review_state(session: AsyncSession, user: User) -> dict:
    """يُعيد حالة دورة المراجعة البعيدة كاملة.
    
    إذا لم يكن للمستخدم حالة بعد، نُنشئها تلقائيًا.
    """
    last = user.last_hifz_page or 0
    if last == 0:
        return {
            "applicable": False,
            "current_cycle": 0,
            "total_cycles": 0,
            "cycle_start": None,
            "cycle_end": None,
            "last_completed_cycle": 0,
        }

    result = await session.execute(
        select(FarReviewCycle).where(FarReviewCycle.user_id == user.id)
    )
    state = result.scalar_one_or_none()

    total_cycles = _compute_total_far_cycles(last)
    if total_cycles == 0:
        return {
            "applicable": False,
            "current_cycle": 0,
            "total_cycles": 0,
            "cycle_start": None,
            "cycle_end": None,
            "last_completed_cycle": 0,
        }

    if state is None:
        # إنشاء الحالة الافتراضية: الدورة 1 (الأحدث)
        state = FarReviewCycle(
            user_id=user.id,
            current_cycle=1,
            last_completed_cycle=0,
        )
        session.add(state)
        await session.commit()
        await session.refresh(state)

    # التحقق من صحة current_cycle ضمن النطاق
    if state.current_cycle > total_cycles:
        state.current_cycle = 1  # إعادة الضبط للدورة الأولى
        await session.commit()

    cycle_start, cycle_end = _compute_cycle_range(last, state.current_cycle)

    return {
        "applicable": True,
        "current_cycle": state.current_cycle,
        "total_cycles": total_cycles,
        "cycle_start": cycle_start,
        "cycle_end": cycle_end,
        "last_completed_cycle": state.last_completed_cycle,
    }


async def advance_far_review_cycle(session: AsyncSession, user: User) -> dict:
    """إتمام دورة المراجعة البعيدة الحالية — الانتقال للدورة التالية.
    
    الترتيب: 1 → 2 → ... → N → 1 (دائري).
    """
    state_info = await get_far_review_state(session, user)
    if not state_info["applicable"]:
        return {"success": False, "reason": "not_applicable"}

    total = state_info["total_cycles"]
    current = state_info["current_cycle"]

    result = await session.execute(
        select(FarReviewCycle).where(FarReviewCycle.user_id == user.id)
    )
    state = result.scalar_one_or_none()
    if state is None:
        return {"success": False, "reason": "no_state"}

    state.last_completed_cycle = current
    state.current_cycle = (current % total) + 1  # دوري
    new_start, new_end = _compute_cycle_range(user.last_hifz_page or 0, state.current_cycle)
    state.cycle_start = new_start
    state.cycle_end = new_end
    await session.commit()
    await session.refresh(state)

    return {
        "success": True,
        "new_cycle": state.current_cycle,
        "new_cycle_start": new_start,
        "new_cycle_end": new_end,
    }
