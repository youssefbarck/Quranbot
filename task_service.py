"""
خدمات المهام: تسجيل/إلغاء/تأجيل إنجاز المهام اليومية الـ 8.
"""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import config
from ..models import User, DailyProgress, ActivityLog
from ..engines.hifz_engine import confirm_memorization, set_last_hifz_page
from ..engines.reading_engine import advance_reading
from ..engines.listening_engine import advance_listening
from ..engines.revision_engine import advance_far_review_cycle
from ..engines.prep_engine import start_pre_session_timer, end_pre_session_timer


# خريطة أنواع المهام ← أسماء الحقول في DailyProgress
TASK_FIELD_MAP = {
    "reading":          "reading_done",
    "listening":        "listening_done",
    "weekly_prep":      "weekly_prep_done",
    "nightly_prep":     "nightly_prep_done",
    "pre_session_prep": "pre_session_prep_done",
    "memorize":         "memorize_done",
    "near_review":      "near_review_done",
    "far_review":       "far_review_done",
}


async def get_or_create_progress(
    session: AsyncSession,
    user_id: int,
    progress_date: Optional[date] = None,
) -> DailyProgress:
    """استرجاع أو إنشاء سجل اليوم."""
    progress_date = progress_date or date.today()
    result = await session.execute(
        select(DailyProgress).where(
            DailyProgress.user_id == user_id,
            DailyProgress.progress_date == progress_date,
        )
    )
    progress = result.scalar_one_or_none()
    if progress is None:
        progress = DailyProgress(user_id=user_id, progress_date=progress_date)
        session.add(progress)
        await session.commit()
        await session.refresh(progress)
    return progress


def _compute_task_status(progress: DailyProgress) -> str:
    """احسب الحالة الإجمالية لليوم."""
    tasks = [
        progress.reading_done, progress.listening_done,
        progress.weekly_prep_done, progress.nightly_prep_done,
        progress.pre_session_prep_done, progress.memorize_done,
        progress.near_review_done, progress.far_review_done,
    ]
    completed = sum(1 for t in tasks if t)
    if completed == 8:
        return "completed"
    elif completed >= 1:
        return "partial"
    else:
        return "pending"


async def toggle_task(
    session: AsyncSession,
    user: User,
    progress: DailyProgress,
    task_type: str,
) -> dict:
    """تبديل حالة مهمة (مكتملة ↔ غير مكتملة).
    
    هذا يُمكّن التراجع عن أي ضغطة خاطئة.
    """
    if task_type not in TASK_FIELD_MAP:
        return {"success": False, "reason": "invalid_task_type"}

    field = TASK_FIELD_MAP[task_type]
    currently_done = bool(getattr(progress, field, False))

    if currently_done:
        # === التراجع عن المهمة ===
        if task_type == "pre_session_prep":
            progress.pre_session_duration_min = 0
            user.pre_session_started_at = None
        setattr(progress, field, False)
        await session.commit()
        progress.task_status = _compute_task_status(progress)
        await session.commit()
        await log_activity(session, user.id, f"undo_{task_type}", "تراجع عن المهمة")
        return {"success": True, "action": "undone", "task_type": task_type}
    else:
        # === تسجيل المهمة كمنجزة ===
        if task_type == "memorize":
            result = confirm_memorization(user)
            if not result.get("success"):
                return {"success": False, "reason": result.get("reason"), "message": result.get("message")}
            # تسجيل الأوجه المحفوظة في MemorizationLog
            from ..models import MemorizationLog
            for p in result["memorized_pages"]:
                existing = await session.execute(
                    select(MemorizationLog).where(
                        MemorizationLog.user_id == user.id,
                        MemorizationLog.page_number == p,
                    )
                )
                log = existing.scalar_one_or_none()
                if log is None:
                    session.add(MemorizationLog(
                        user_id=user.id, page_number=p, date_memorized=date.today()
                    ))
                else:
                    log.date_memorized = date.today()
                    log.review_count = 0
            progress.memorize_done = True
            await session.commit()
        elif task_type == "reading":
            advance_reading(user)
            progress.reading_done = True
            await session.commit()
        elif task_type == "listening":
            advance_listening(user)
            progress.listening_done = True
            await session.commit()
        elif task_type == "far_review":
            await advance_far_review_cycle(session, user)
            progress.far_review_done = True
            await session.commit()
        elif task_type == "pre_session_prep":
            # إنهاء المؤقّت وتسجيل المدة
            minutes = end_pre_session_timer(user)
            progress.pre_session_duration_min = minutes or config.PRE_SESSION_MINUTES
            progress.pre_session_prep_done = True
            await session.commit()
        else:
            setattr(progress, field, True)
            await session.commit()

        progress.task_status = _compute_task_status(progress)
        await session.commit()

        # تحديث streak
        await update_streak_on_activity(session, user)
        await log_activity(session, user.id, f"done_{task_type}", f"أنجزت {task_type}")
        return {"success": True, "action": "done", "task_type": task_type}


async def start_pre_session(session: AsyncSession, user: User, progress: DailyProgress) -> dict:
    """بدء مؤقّت التحضير القبلي (15 دقيقة)."""
    start_pre_session_timer(user)
    progress.pre_session_prep_done = False  # لم يكتمل بعد
    await session.commit()
    await log_activity(session, user.id, "pre_session_start", "بدأ التحضير القبلي")
    return {"success": True, "started_at": user.pre_session_started_at}


async def update_streak_on_activity(session: AsyncSession, user: User) -> None:
    """تحديث عدّاد أيام الالتزام المتتالية (streak).
    
    القاعدة: يوم واحد على الأقل مع مهمة مكتملة = يوم التزام.
    إذا انقطع يوم، يُعاد الضبط إلى 0.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    if user.last_active_date == today:
        # نفس اليوم — لا تغيير في الـ streak
        return
    if user.last_active_date == yesterday:
        # استمرارية
        user.streak_days = (user.streak_days or 0) + 1
    else:
        # انقطاع أو أول مرة
        user.streak_days = 1
    user.last_active_date = today
    await session.commit()


async def log_activity(
    session: AsyncSession,
    user_id: int,
    event_type: str,
    description: Optional[str] = None,
) -> None:
    """تسجيل حدث في Activity Log."""
    log = ActivityLog(
        user_id=user_id,
        event_type=event_type,
        description=description,
    )
    session.add(log)
    await session.commit()


async def get_recent_activity(session: AsyncSession, user_id: int, days: int = 14) -> list:
    """آخر سجل النشاط."""
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=days)
    result = await session.execute(
        select(ActivityLog)
        .where(ActivityLog.user_id == user_id, ActivityLog.log_date >= cutoff)
        .order_by(ActivityLog.log_date.desc(), ActivityLog.log_time.desc())
        .limit(100)
    )
    return list(result.scalars().all())
