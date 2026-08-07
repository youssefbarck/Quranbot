"""
منطق العمليات — طريقة الحصون الخمسة
===================================
يحسب وينسق:
- الحصن 1: الحفظ اليومي (صفحة جديدة)
- الحصن 2: المراجعة اليومية (ما حُفظ اليوم)
- الحصن 3: الحفظ الأسبوعي (آخر 7 أيام)
- الحصن 4: المراجعة الأسبوعية (5 مواعيد)
- الحصن 5: المراجعة الشهرية
- القراءة الصباحية: حزبين
- الاستماع الظهيري: حزب
"""
import re
from datetime import date, timedelta
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User, Memorization, WeeklyReview, MonthlyReview, DailyProgress
from . import quran_data


# ====== المستخدم ======

async def get_or_create_user(session: AsyncSession, telegram_id: int,
                              username: str | None = None,
                              full_name: str | None = None) -> User:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif (username != user.username) or (full_name != user.full_name):
        user.username = username
        user.full_name = full_name
        await session.commit()
    return user


# ====== استخراج الصفحة من نص المستخدم ======

async def parse_memorization_input(text: str) -> dict:
    """
    يحلل نص إدخال المستخدم لمعرفة ما حفظه.
    يدعم:
      - "صفحة 50" / "صفحة 50-60" / "الصفحة 50"
      - "جزء 3" / "جزء 30"
      - "سورة البقرة" / "سورة الكهف"
      - "حفظت كل القرآن"
      - رقم مباشر: "50"
    """
    text = text.strip()
    result = {"type": None, "value": None, "page": None, "raw": text}

    # حفظ كل القرآن
    if "كل القرآن" in text or "كامل القرآن" in text or "ختمت" in text:
        result.update({"type": "all", "value": "all", "page": quran_data.TOTAL_PAGES})
        return result

    # جزء
    m = re.search(r"جزء\s*(\d+)", text)
    if m:
        juz = int(m.group(1))
        if 1 <= juz <= 30:
            start, end = quran_data.juz_pages(juz)
            result.update({"type": "juz", "value": juz, "page": end})
            return result

    # سورة
    m = re.search(r"سورة\s+(.+)", text)
    if m:
        surah_name = m.group(1).strip()
        surah = quran_data.get_surah_by_name(surah_name)
        if surah:
            # آخر صفحة في السورة = أول صفحة في السورة التالية - 1
            if surah.number < 114:
                next_surah = quran_data.get_surah_by_number(surah.number + 1)
                last_page = next_surah.page_start - 1
            else:
                last_page = quran_data.TOTAL_PAGES
            result.update({"type": "surah", "value": surah.name_ar, "page": last_page})
            return result

    # صفحة (مع نطاق)
    m = re.search(r"صفحة\s*(\d+)\s*[-–]\s*(\d+)", text)
    if m:
        start_p = int(m.group(1))
        end_p = int(m.group(2))
        if 1 <= end_p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page_range", "value": (start_p, end_p), "page": end_p})
            return result

    m = re.search(r"صفحة\s*(\d+)", text)
    if m:
        p = int(m.group(1))
        if 1 <= p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page", "value": p, "page": p})
            return result

    # رقم مباشر
    m = re.match(r"^\s*(\d+)\s*$", text)
    if m:
        p = int(m.group(1))
        if 1 <= p <= quran_data.TOTAL_PAGES:
            result.update({"type": "page", "value": p, "page": p})
            return result

    return result


# ====== تسجيل ما حفظه المستخدم (عند البداية) ======

async def set_memorized_up_to(session: AsyncSession, user: User, page: int) -> None:
    """يسجل أن المستخدم حفظ من الصفحة 1 إلى page (عند البداية)"""
    # نحذف أي سجلات سابقة
    await session.execute(
        Memorization.__table__.delete().where(Memorization.user_id == user.id)
    )
    # نسجل كل صفحة من 1 إلى page
    today = date.today()
    # نضع تواريخ متفاوتة لمحاكاة أيام سابقة (آخر صفحة لها تاريخ اليوم)
    for p in range(1, page + 1):
        # نعطيهم تاريخ اليوم تقريباً (لن نعرف متى حفظت كل صفحة بدقة)
        memo = Memorization(
            user_id=user.id,
            page_number=p,
            date_memorized=today,
            review_count=5,  # نعتبرها مراجعة لأنها حفظ قديم
        )
        session.add(memo)

    user.current_page = page + 1 if page < quran_data.TOTAL_PAGES else quran_data.TOTAL_PAGES
    user.start_page = 1
    user.total_memorized = page
    user.onboarding_done = True
    await session.commit()


# ====== الحصن 1: الحفظ اليومي ======

def get_today_memorize_page(user: User) -> int:
    """صفحة الحفظ الجديد اليوم"""
    return user.current_page


async def mark_memorized(session: AsyncSession, user: User, page: int) -> Memorization:
    """يسجل أن المستخدم حفظ صفحة جديدة"""
    # تحقق من عدم تكرار
    result = await session.execute(
        select(Memorization).where(
            and_(
                Memorization.user_id == user.id,
                Memorization.page_number == page,
            )
        )
    )
    memo = result.scalar_one_or_none()
    if memo is None:
        memo = Memorization(
            user_id=user.id,
            page_number=page,
            date_memorized=date.today(),
            review_count=0,
        )
        session.add(memo)
        # نضيف سجل المراجعة الأسبوعية (5 مواعيد) للحصن 4
        weekly = WeeklyReview(
            user_id=user.id,
            page_number=page,
            date_memorized=date.today(),
            review_1_layla=date.today(),  # ليلة الحفظ (نفس اليوم مساءً)
        )
        session.add(weekly)
    else:
        memo.date_memorized = date.today()
        memo.review_count = 0

    # تقدم الصفحة الحالية
    if user.current_page <= page:
        user.current_page = min(page + 1, quran_data.TOTAL_PAGES)
    user.total_memorized = await count_memorized(session, user.id)

    await session.commit()
    await session.refresh(memo)
    return memo


async def count_memorized(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count(Memorization.id)).where(Memorization.user_id == user_id)
    )
    return result.scalar() or 0


# ====== الحصن 2: المراجعة اليومية ======

async def get_today_review_pages(session: AsyncSession, user_id: int) -> list[int]:
    """يرجع الصفحات المحفوظة اليوم (للمراجعة اليومية)"""
    today = date.today()
    result = await session.execute(
        select(Memorization).where(
            and_(
                Memorization.user_id == user_id,
                Memorization.date_memorized == today,
            )
        ).order_by(Memorization.page_number)
    )
    return [m.page_number for m in result.scalars().all()]


# ====== الحصن 3: الحفظ الأسبوعي ======

async def get_weekly_review_pages(session: AsyncSession, user_id: int) -> list[int]:
    """يرجع الصفحات المحفوظة في آخر 7 أيام (للحفظ الأسبوعي)"""
    week_ago = date.today() - timedelta(days=7)
    result = await session.execute(
        select(Memorization).where(
            and_(
                Memorization.user_id == user_id,
                Memorization.date_memorized >= week_ago,
            )
        ).order_by(Memorization.page_number)
    )
    return [m.page_number for m in result.scalars().all()]


# ====== الحصن 4: المراجعة الأسبوعية (5 مواعيد) ======

async def get_today_weekly_review(session: AsyncSession, user_id: int) -> list[dict]:
    """
    يرجع الصفحات التي يجب مراجعتها اليوم حسب المراجعة الأسبوعية.
    كل صفحة لها 5 مواعيد للمراجعة، نتحقق أيها مستحقة اليوم.
    """
    today = date.today()
    result = await session.execute(
        select(WeeklyReview).where(WeeklyReview.user_id == user_id)
        .order_by(WeeklyReview.date_memorized.desc())
    )
    reviews = result.scalars().all()

    today_tasks = []
    for r in reviews:
        # تحديد المراجعة المستحقة اليوم (أول مراجعة لم تُجرَ ووقتها حل)
        # ترتيب المراجعات: ليلة، ليل، ثلث، اربعاء، خميس
        # موعد كل مراجعة = تاريخ الحفظ + n أيام
        days = [(0, "review_1_layla", "done_1", "ليلة"),
                (1, "review_2_layl", "done_2", "ليل"),
                (2, "review_3_thuluth", "done_3", "ثلث"),
                (3, "review_4_arbain", "done_4", "اربعاء"),
                (4, "review_5_khamis", "done_5", "خميس")]

        for day_offset, _, done_field, label in days:
            review_date = r.date_memorized + timedelta(days=day_offset)
            if review_date == today:
                is_done = getattr(r, done_field)
                if not is_done:
                    today_tasks.append({
                        "page": r.page_number,
                        "label": label,
                        "done_field": done_field,
                        "review_id": r.id,
                    })
                    break
    return today_tasks


async def mark_weekly_review_done(session: AsyncSession, review_id: int,
                                   done_field: str) -> None:
    """يسجل إتمام مراجعة أسبوعية"""
    result = await session.execute(
        select(WeeklyReview).where(WeeklyReview.id == review_id)
    )
    review = result.scalar_one_or_none()
    if review:
        setattr(review, done_field, True)
        await session.commit()


# ====== الحصن 5: المراجعة الشهرية ======

async def get_monthly_review(session: AsyncSession, user_id: int,
                              year: int, month: int) -> MonthlyReview | None:
    """يجلب أو ينشئ سجل المراجعة الشهرية"""
    result = await session.execute(
        select(MonthlyReview).where(
            and_(
                MonthlyReview.user_id == user_id,
                MonthlyReview.year == year,
                MonthlyReview.month == month,
            )
        )
    )
    review = result.scalar_one_or_none()
    if review is None:
        # نجمع كل صفحات الشهر
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        pages_result = await session.execute(
            select(Memorization).where(
                and_(
                    Memorization.user_id == user_id,
                    Memorization.date_memorized >= start_date,
                    Memorization.date_memorized <= end_date,
                )
            ).order_by(Memorization.page_number)
        )
        pages = [str(m.page_number) for m in pages_result.scalars().all()]
        review = MonthlyReview(
            user_id=user_id,
            year=year,
            month=month,
            pages_reviewed=",".join(pages),
        )
        session.add(review)
        await session.commit()
        await session.refresh(review)
    return review


# ====== تتبع المهام اليومية ======

async def get_or_create_progress(session: AsyncSession, user_id: int,
                                  progress_date: date | None = None) -> DailyProgress:
    progress_date = progress_date or date.today()
    result = await session.execute(
        select(DailyProgress).where(
            and_(
                DailyProgress.user_id == user_id,
                DailyProgress.progress_date == progress_date,
            )
        )
    )
    progress = result.scalar_one_or_none()
    if progress is None:
        progress = DailyProgress(user_id=user_id, progress_date=progress_date)
        session.add(progress)
        await session.commit()
        await session.refresh(progress)
    return progress


# ====== القراءة الصباحية (حزبين) ======

def get_morning_reading_pages(user: User) -> tuple[int, int]:
    """يقرأ حزبين (20 صفحة) يومياً، يتقدم دورياً"""
    day_of_year = date.today().timetuple().tm_yday
    start_page = ((day_of_year - 1) * 20 % quran_data.TOTAL_PAGES) + 1
    end_page = start_page + 19
    if end_page > quran_data.TOTAL_PAGES:
        end_page = quran_data.TOTAL_PAGES
    return start_page, end_page


# ====== الاستماع الظهيري (حزب) ======

def get_midday_listening_pages(user: User) -> tuple[int, int]:
    """يستمع لحزب (10 صفحات) يومياً"""
    day_of_year = date.today().timetuple().tm_yday
    start_page = (((day_of_year + 5) * 10) % quran_data.TOTAL_PAGES) + 1
    end_page = start_page + 9
    if end_page > quran_data.TOTAL_PAGES:
        end_page = quran_data.TOTAL_PAGES
    return start_page, end_page


# ====== تتبع التقدم ======

async def mark_progress_done(session: AsyncSession, user_id: int,
                              task_type: str) -> None:
    """يسجل إتمام مهمة يومية: reading / listening / memorize / daily_review"""
    progress = await get_or_create_progress(session, user_id)
    if task_type == "reading":
        progress.reading_done = True
    elif task_type == "listening":
        progress.listening_done = True
    elif task_type == "memorize":
        progress.memorize_done = True
    elif task_type == "daily_review":
        progress.daily_review_done = True
    await session.commit()


async def get_memorization_history(session: AsyncSession, user_id: int) -> list[Memorization]:
    result = await session.execute(
        select(Memorization)
        .where(Memorization.user_id == user_id)
        .order_by(Memorization.date_memorized.asc())
    )
    return list(result.scalars().all())
