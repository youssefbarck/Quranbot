"""
المحرك الموحَّد — يجمع كل الحصون الخمسة في واجهة واحدة.
كل التابع يقبل user ويُعيد "خطة اليوم" الكاملة.
"""
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession

from .. import config
from ..models import User, DailyProgress
from .reading_engine import get_reading_assignment, get_reading_cycle_info
from .listening_engine import get_listening_assignment, get_listening_cycle_info
from .hifz_engine import get_today_hifz_assignment
from .revision_engine import get_near_review_range, get_far_review_state
from .prep_engine import (
    get_weekly_prep_range, get_nightly_prep_pages,
    get_pre_session_prep_page, is_pre_session_active,
    get_pre_session_elapsed_minutes,
)


async def compute_today_plan(session: AsyncSession, user: User, progress: DailyProgress) -> dict:
    """الحساب الكامل لخطة اليوم بناءً على حالة المستخدم.
    
    هذه هي الواجهة المركزية:
        USER STATE → Hifz Engine → TODAY'S PLAN → Telegram UI
    """
    reading = get_reading_assignment(user)
    reading_info = get_reading_cycle_info(user)
    listening = get_listening_assignment(user)
    listening_info = get_listening_cycle_info(user)

    weekly_prep = get_weekly_prep_range(user)
    nightly_prep = get_nightly_prep_pages(user)
    pre_session = get_pre_session_prep_page(user)
    pre_session_active = is_pre_session_active(user)
    pre_session_elapsed = get_pre_session_elapsed_minutes(user)

    hifz = get_today_hifz_assignment(user)
    near = get_near_review_range(user)
    far = await get_far_review_state(session, user)

    # عدّاد الإنجاز
    completed_count = sum([
        bool(progress.reading_done), bool(progress.listening_done),
        bool(progress.weekly_prep_done), bool(progress.nightly_prep_done),
        bool(progress.pre_session_prep_done), bool(progress.memorize_done),
        bool(progress.near_review_done), bool(progress.far_review_done),
    ])

    return {
        "user": user,
        "progress": progress,
        "reading": reading,
        "reading_info": reading_info,
        "listening": listening,
        "listening_info": listening_info,
        "weekly_prep": weekly_prep,
        "nightly_prep": nightly_prep,
        "pre_session": pre_session,
        "pre_session_active": pre_session_active,
        "pre_session_elapsed": pre_session_elapsed,
        "hifz": hifz,
        "near_review": near,
        "far_review": far,
        "completed_count": completed_count,
        "total_tasks": 8,
    }
