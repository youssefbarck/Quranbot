"""
نماذج قاعدة البيانات (SQLAlchemy 2.0 — DeclarativeBase)
=====================================================

الجداول:
    User                — المستخدم + الإعدادات + حالة الحفظ
    UserSettings        — أوقات التذكيرات الـ 8 (منفصلة لقابلية التوسع)
    DailyProgress       — حالة إنجاز المهام لكل يوم
    MemorizationLog     — سجل دائم لكل وجه حُفظ (مع التاريخ والمراجعات)
    ActivityLog         — سجل أحداث يومي مختصر
    FarReviewCycle      — حالة دورة المراجعة البعيدة (مستقلة عن الحفظ)
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer, String, Boolean, Text, Float,
    func, UniqueConstraint, select
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

import config


class Base(DeclarativeBase):
    pass


class User(Base):
    """المستخدم الرئيسي — يحمل كل الحالة المركزية للحفظ."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default=config.DEFAULT_TIMEZONE)

    # ====== حالة الحفظ ======
    last_hifz_page: Mapped[int] = mapped_column(Integer, default=0)  # آخر وجه محفوظ
    next_hifz_page: Mapped[int] = mapped_column(Integer, default=1)  # الوجه القادم للحفظ
    daily_hifz_amount: Mapped[int] = mapped_column(Integer, default=config.DEFAULT_DAILY_HIFZ_AMOUNT)
    weekly_hifz_amount: Mapped[int] = mapped_column(Integer, default=config.DEFAULT_WEEKLY_HIFZ_AMOUNT)
    plan_start_date: Mapped[date] = mapped_column(Date, default=date.today)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False)

    # ====== دورة القراءة (الحصن الأول) ======
    reading_hizb_current: Mapped[int] = mapped_column(Integer, default=1)  # الحزب الحالي للقراءة
    reading_khatmah_count: Mapped[int] = mapped_column(Integer, default=0)  # عدد الختمات المنجزة

    # ====== دورة الاستماع (الحصن الأول) ======
    listening_hizb_current: Mapped[int] = mapped_column(Integer, default=1)
    listening_khatmah_count: Mapped[int] = mapped_column(Integer, default=0)

    # ====== الالتزام ======
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_active_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # ====== التحضير الأسبوعي (محسوب ديناميكيًا، يُخزَّن فقط للتسريع) ======
    weekly_prep_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    weekly_prep_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ====== التحضير القبلي ======
    pre_session_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ====== الطوابع الزمنية ======
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # العلاقات
    settings_rel: Mapped[list["UserSettings"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    daily_progress: Mapped[list["DailyProgress"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    far_review_state: Mapped[Optional["FarReviewCycle"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserSettings(Base):
    """أوقات التذكيرات الـ 8 — قابلة للتخصيص لكل مستخدم."""
    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", "reminder_type", name="uq_user_reminder"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reminder_type: Mapped[str] = mapped_column(String(32))  # memorize / reading / ...
    reminder_time: Mapped[str] = mapped_column(String(5))   # HH:MM
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="settings_rel")


class DailyProgress(Base):
    """حالة المهام لكل يوم — يجيب عن: ماذا أنجزت اليوم؟"""
    __tablename__ = "daily_progress"
    __table_args__ = (UniqueConstraint("user_id", "progress_date", name="uq_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    progress_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)

    # المهام الـ 8
    reading_done: Mapped[bool] = mapped_column(Boolean, default=False)
    listening_done: Mapped[bool] = mapped_column(Boolean, default=False)
    weekly_prep_done: Mapped[bool] = mapped_column(Boolean, default=False)
    nightly_prep_done: Mapped[bool] = mapped_column(Boolean, default=False)
    pre_session_prep_done: Mapped[bool] = mapped_column(Boolean, default=False)
    memorize_done: Mapped[bool] = mapped_column(Boolean, default=False)
    near_review_done: Mapped[bool] = mapped_column(Boolean, default=False)
    far_review_done: Mapped[bool] = mapped_column(Boolean, default=False)

    # مدة التحضير القبلي
    pre_session_duration_min: Mapped[int] = mapped_column(Integer, default=0)

    # الحالة الإجمالية: pending / partial / completed / postponed / missed
    task_status: Mapped[str] = mapped_column(String(16), default="pending")

    user: Mapped["User"] = relationship(back_populates="daily_progress")


class MemorizationLog(Base):
    """سجل دائم لكل وجه حُفظ — يُستخدم لحساب المراجعات والاحصائيات."""
    __tablename__ = "memorization_log"
    __table_args__ = (UniqueConstraint("user_id", "page_number", name="uq_user_page"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, index=True)
    date_memorized: Mapped[date] = mapped_column(Date, default=date.today)
    review_count: Mapped[int] = mapped_column(Integer, default=0)


class ActivityLog(Base):
    """سجل مختصر لكل حدث مهم — للعرض التاريخي واكتشاف الأنماط."""
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    log_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    log_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    event_type: Mapped[str] = mapped_column(String(32))  # memorize / reading_done / setting_change / ...
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class FarReviewCycle(Base):
    """حالة دورة المراجعة البعيدة — مستقلة عن الحفظ.
    
    لماذا جدول مستقل؟
    لأن المستخدم قد يواصل الحفظ (يتقدّم last_hifz_page) بينما لا يزال يراجع
    دورة قديمة. لا يمكن اشتقاق هذا من الحفظ فقط.
    """
    __tablename__ = "far_review_cycle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    current_cycle: Mapped[int] = mapped_column(Integer, default=1)
    cycle_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cycle_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_completed_cycle: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="far_review_state")


# ====== Migration statements (آمنة — IF NOT EXISTS) ======
MIGRATION_STATEMENTS = [
    # users
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_hifz_page INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS next_hifz_page INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_hifz_amount INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_hifz_amount INTEGER DEFAULT 7",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_start_date DATE DEFAULT CURRENT_DATE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_done BOOLEAN DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS reading_hizb_current INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS reading_khatmah_count INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS listening_hizb_current INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS listening_khatmah_count INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS streak_days INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_date DATE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS notifications_enabled BOOLEAN DEFAULT TRUE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_prep_start INTEGER",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_prep_end INTEGER",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS pre_session_started_at TIMESTAMP",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) DEFAULT 'Africa/Algiers'",
    # daily_progress
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS weekly_prep_done BOOLEAN DEFAULT FALSE",
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS nightly_prep_done BOOLEAN DEFAULT FALSE",
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS pre_session_prep_done BOOLEAN DEFAULT FALSE",
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS pre_session_duration_min INTEGER DEFAULT 0",
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS near_review_done BOOLEAN DEFAULT FALSE",
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS far_review_done BOOLEAN DEFAULT FALSE",
    "ALTER TABLE daily_progress ADD COLUMN IF NOT EXISTS task_status VARCHAR(16) DEFAULT 'pending'",
]
