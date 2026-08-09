"""
خدمات ذكية — تحليل سلوك المستخدم واقتراح تحسينات (لا تغيير تلقائي!).
"""
from datetime import datetime, timedelta, date
from collections import Counter
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, ActivityLog, DailyProgress


async def analyze_user_patterns(session: AsyncSession, user_id: int) -> dict:
    """تحليل أنماط سلوك المستخدم:
    - أوقات النشاط المعتادة (الساعة الأكثر إنجازًا)
    - كثرة التأجيل
    - أكثر الأيام التزامًا
    - المهام الفائتة باستمرار
    """
    cutoff = date.today() - timedelta(days=30)
    result = await session.execute(
        select(ActivityLog).where(
            ActivityLog.user_id == user_id,
            ActivityLog.log_date >= cutoff,
        ).order_by(ActivityLog.log_date.desc())
    )
    logs = list(result.scalars().all())

    # الساعات الأكثر إنجازًا
    hours = [log.log_time.hour for log in logs if log.event_type.startswith("done_")]
    hour_counts = Counter(hours)
    most_active_hour = hour_counts.most_common(1)[0][0] if hour_counts else None

    # المهام الأكثر إنجازًا
    done_tasks = [log.event_type.replace("done_", "") for log in logs if log.event_type.startswith("done_")]
    done_counts = Counter(done_tasks)

    # المهام الأكثر تراجعًا
    undone = [log.event_type.replace("undo_", "") for log in logs if log.event_type.startswith("undo_")]
    undone_counts = Counter(undone)

    # عدد أيام الالتزام
    active_days = set(log.log_date for log in logs if log.event_type.startswith("done_"))

    return {
        "most_active_hour": most_active_hour,
        "most_done_task": done_counts.most_common(1)[0][0] if done_counts else None,
        "most_undone_task": undone_counts.most_common(1)[0][0] if undone_counts else None,
        "active_days_count": len(active_days),
        "total_done": len(done_tasks),
        "total_undone": len(undone),
    }


async def generate_suggestions(session: AsyncSession, user: User) -> list[str]:
    """توليد اقتراحات ذكية بناءً على السلوك (لا تُطبَّق تلقائيًا)."""
    patterns = await analyze_user_patterns(session, user.id)
    suggestions = []

    if patterns["most_active_hour"] is not None:
        # نُحدِّد أيّ تذكير يقترح تغيير وقته
        hour = patterns["most_active_hour"]
        import config
        # الحفظ غالبًا يتم في هذه الساعة
        suggestions.append(
            f"💡 لاحظتُ أنك غالبًا تنجز مهامك الساعة {hour:02d}:00. "
            f"هل تريد جعل هذا وقت تذكير الحفظ الافتراضي؟"
        )

    if patterns["most_undone_task"]:
        import config
        task_label = config.REMINDER_LABELS_AR.get(patterns["most_undone_task"], patterns["most_undone_task"])
        suggestions.append(
            f"📊 لاحظتُ أنك غالبًا تتراجع عن '{task_label}'. "
            f"هل تريد تعديل وقتها أو مراجعة الهدف منها؟"
        )

    if patterns["active_days_count"] < 10 and patterns["total_done"] > 0:
        suggestions.append(
            "🔥 الالتزام الحالي أقل من 10 أيام في الشهر الماضي. "
            "جرّبي تقليل مقدار الحفظ اليومي قليلاً حتى تترسخ العادة."
        )

    return suggestions
