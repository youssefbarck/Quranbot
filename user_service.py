"""
خدمات المستخدم: إنشاء، استرجاع، تحديث، onboarding.
"""
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from models import User, MemorizationLog
from database import ensure_default_reminders


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
) -> User:
    """استرجاع أو إنشاء مستخدم جديد."""
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        today = date.today()
        user = User(
            telegram_id=telegram_id, username=username, full_name=full_name,
            plan_start_date=today, last_active_date=today,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        # إنشاء التذكيرات الافتراضية
        await ensure_default_reminders(user.id)
    elif (username != user.username) or (full_name != user.full_name):
        user.username = username
        user.full_name = full_name
        await session.commit()
    return user


async def update_user_activity(session: AsyncSession, user: User) -> None:
    """تحديث آخر نشاط للمستخدم."""
    today = date.today()
    if user.last_active_date != today:
        user.last_active_date = today
        await session.commit()


async def set_initial_hifz(session: AsyncSession, user: User, last_page: int) -> None:
    """ضبط نقطة البداية للحفظ عند الـ onboarding.
    
    هذه الدالة تُسجّل كل الأوجه من 1 إلى last_page كمحفوظة (للاستخدام في الإحصائيات).
    """
    last_page = max(0, min(int(last_page), config.QURAN_PAGE_COUNT))
    user.last_hifz_page = last_page
    user.next_hifz_page = last_page + 1 if last_page < config.QURAN_PAGE_COUNT else last_page
    # التحضير الأسبوعي = الأسبوع القادم (بعد تجاوز مقدار الأسبوع الحالي)
    weekly_amount = user.weekly_hifz_amount or config.DEFAULT_WEEKLY_HIFZ_AMOUNT
    this_week_start = last_page + 1 if last_page < config.QURAN_PAGE_COUNT else last_page
    user.weekly_prep_start = this_week_start + weekly_amount
    user.weekly_prep_end = min(
        config.QURAN_PAGE_COUNT,
        user.weekly_prep_start + weekly_amount - 1,
    )
    # حذف أي سجل سابق للمحفوظ (إذا أعاد المستخدم الضبط)
    await session.execute(
        MemorizationLog.__table__.delete().where(MemorizationLog.user_id == user.id)
    )
    today = date.today()
    if last_page > 0:
        # تسجيل الأوجه المحفوظة دفعة واحدة (تحسين: bulk insert)
        for p in range(1, last_page + 1):
            session.add(MemorizationLog(
                user_id=user.id, page_number=p, date_memorized=today, review_count=5
            ))
    await session.commit()


async def update_settings(
    session: AsyncSession,
    user: User,
    *,
    daily_amount: Optional[int] = None,
    weekly_amount: Optional[int] = None,
    timezone: Optional[str] = None,
    plan_start_date: Optional[date] = None,
    notifications: Optional[bool] = None,
) -> User:
    """تحديث إعدادات المستخدم — يُعيد حساب الاشتقاقات (مثل weekly_prep)."""
    if daily_amount is not None:
        user.daily_hifz_amount = max(1, min(int(daily_amount), config.QURAN_PAGE_COUNT))
        # لا يتأثر التحضير الأسبوعي بالمقدار اليومي مباشرةً — يعتمد على المقدار الأسبوعي فقط
        # (يُعاد حسابه عند تغيير weekly_amount أو تأكيد الحفظ)
    if weekly_amount is not None:
        user.weekly_hifz_amount = max(1, min(int(weekly_amount), config.QURAN_PAGE_COUNT))
        last = user.last_hifz_page or 0
        if last < config.QURAN_PAGE_COUNT:
            # التحضير الأسبوعي = الأسبوع القادم (بعد تجاوز مقدار الأسبوع الحالي)
            this_week_start = last + 1
            user.weekly_prep_start = this_week_start + user.weekly_hifz_amount
            user.weekly_prep_end = min(
                config.QURAN_PAGE_COUNT,
                user.weekly_prep_start + user.weekly_hifz_amount - 1,
            )
    if timezone is not None:
        user.timezone = timezone
    if plan_start_date is not None:
        user.plan_start_date = plan_start_date
    if notifications is not None:
        user.notifications_enabled = notifications
    await session.commit()
    return user
