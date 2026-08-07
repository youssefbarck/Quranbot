"""
نماذج قاعدة البيانات — طريقة الحصون الخمسة
==========================================
5 جداول:
1. users               - المستخدمون وإعداداتهم
2. memorization        - سجل الصفحات المحفوظة (للحصن 1: الحفظ اليومي)
3. weekly_reviews      - المراجعات الأسبوعية (للحصن 4: 5 مواعيد)
4. monthly_reviews     - المراجعات الشهرية (للحصن 5)
5. daily_progress      - تتبع المهام اليومية (قراءة، استماع، حفظ)
"""
from datetime import date
from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer, String, Boolean,
    func, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    """مستخدم البوت"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # نقطة البداية للحفظ
    current_page: Mapped[int] = mapped_column(Integer, default=1)  # الصفحة التالية للحفظ
    start_page: Mapped[int] = mapped_column(Integer, default=1)   # أول صفحة حفظها
    total_memorized: Mapped[int] = mapped_column(Integer, default=0)

    # حالة التهيئة (هل أبلغت البوت بما حفظته؟)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False)

    # الإعدادات
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Algiers")
    morning_time: Mapped[str] = mapped_column(String(5), default="08:00")
    midday_time: Mapped[str] = mapped_column(String(5), default="13:00")
    evening_time: Mapped[str] = mapped_column(String(5), default="20:00")

    created_at: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    memorization: Mapped[list["Memorization"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    weekly_reviews: Mapped[list["WeeklyReview"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    monthly_reviews: Mapped[list["MonthlyReview"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    daily_progress: Mapped[list["DailyProgress"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Memorization(Base):
    """
    سجل الصفحات المحفوظة — يخدم:
    - الحصن 1: الحفظ اليومي (آخر صفحة)
    - الحصن 2: المراجعة اليومية (نفس اليوم)
    - الحصن 3: الحفظ الأسبوعي (آخر 7 أيام)
    """
    __tablename__ = "memorization"
    __table_args__ = (UniqueConstraint("user_id", "page_number", name="uq_user_page"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, index=True)
    date_memorized: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    # عدد مرات المراجعة
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reviewed: Mapped[date | None] = mapped_column(Date, nullable=True)

    user: Mapped["User"] = relationship(back_populates="memorization")


class WeeklyReview(Base):
    """
    الحصن 4: المراجعة الأسبوعية — 5 مواعيد
    - ليلة: ليلة الحفظ (نفس اليوم مساءً)
    - ليل: اليوم التالي
    - ثلث: اليوم الثالث
    - اربعاء: اليوم الرابع
    - خميس: اليوم الخامس
    """
    __tablename__ = "weekly_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "page_number", name="uq_weekly_user_page"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, index=True)

    # 5 مواعيد مراجعة (التواريخ)
    review_1_layla: Mapped[date | None] = mapped_column(Date, nullable=True)   # ليلة
    review_2_layl: Mapped[date | None] = mapped_column(Date, nullable=True)   # ليل
    review_3_thuluth: Mapped[date | None] = mapped_column(Date, nullable=True) # ثلث
    review_4_arbain: Mapped[date | None] = mapped_column(Date, nullable=True)  # اربعاء
    review_5_khamis: Mapped[date | None] = mapped_column(Date, nullable=True) # خميس

    # حالة كل مراجعة (تمت أم لا)
    done_1: Mapped[bool] = mapped_column(Boolean, default=False)
    done_2: Mapped[bool] = mapped_column(Boolean, default=False)
    done_3: Mapped[bool] = mapped_column(Boolean, default=False)
    done_4: Mapped[bool] = mapped_column(Boolean, default=False)
    done_5: Mapped[bool] = mapped_column(Boolean, default=False)

    date_memorized: Mapped[date] = mapped_column(Date, server_default=func.current_date())

    user: Mapped["User"] = relationship(back_populates="weekly_reviews")


class MonthlyReview(Base):
    """
    الحصن 5: المراجعة الشهرية — كل نهاية شهر نراجع كل ما حفظناه في الشهر
    """
    __tablename__ = "monthly_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "year", "month", name="uq_monthly_user_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)  # 1-12

    pages_reviewed: Mapped[str] = mapped_column(String(512), default="")  # قائمة الصفحات
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    review_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    user: Mapped["User"] = relationship(back_populates="monthly_reviews")


class DailyProgress(Base):
    """تتبع المهام اليومية: قراءة حزبين + استماع حزب + حفظ"""
    __tablename__ = "daily_progress"
    __table_args__ = (UniqueConstraint("user_id", "progress_date", name="uq_progress_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    progress_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())

    # الصباح: قراءة حزبين
    reading_done: Mapped[bool] = mapped_column(Boolean, default=False)
    reading_pages: Mapped[str] = mapped_column(String(32), default="")

    # منتصف النهار: استماع حزب
    listening_done: Mapped[bool] = mapped_column(Boolean, default=False)
    listening_pages: Mapped[str] = mapped_column(String(32), default="")

    # الحفظ اليومي
    memorize_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memorize_done: Mapped[bool] = mapped_column(Boolean, default=False)

    # المراجعة اليومية (لما حُفظ اليوم)
    daily_review_done: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="daily_progress")
