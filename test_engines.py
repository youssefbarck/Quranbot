"""
اختبارات شاملة لمنطق الحصون الخمسة.
تغطّي 18+ سيناريو حسب مواصفات المستخدم.

التشغيل: python -m pytest tests/test_engines.py -v
أو: python tests/test_engines.py
"""
import asyncio
import os
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# إعداد المسار
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# فرض استخدام SQLite في الذاكرة للاختبارات (نستخدم override=True لأن load_dotenv()
# في config.py قد يقرأ ملف .env من مجلد أب ويستبدل القيمة)
os.environ["DATABASE_URL"] = ""

import config
from models import User, DailyProgress, MemorizationLog, FarReviewCycle, ActivityLog
from hifz_engine import (
    get_today_hifz_assignment, confirm_memorization, set_last_hifz_page,
)
from revision_engine import (
    get_near_review_range, get_far_review_state, advance_far_review_cycle,
)
from reading_engine import (
    get_reading_assignment, advance_reading, get_reading_cycle_info,
)
from listening_engine import (
    get_listening_assignment, advance_listening, get_listening_cycle_info,
)
from prep_engine import (
    get_weekly_prep_range, get_nightly_prep_pages, get_pre_session_prep_page,
    start_pre_session_timer, end_pre_session_timer,
)
from task_service import toggle_task, update_streak_on_activity, log_activity
from user_service import set_initial_hifz, update_settings
from database import init_db, AsyncSessionLocal, close_db


def make_user(**kwargs):
    """يُنشئ مستخدمًا افتراضيًا للاختبارات."""
    defaults = dict(
        id=1, telegram_id=123456, last_hifz_page=0, next_hifz_page=1,
        daily_hifz_amount=1, weekly_hifz_amount=7,
        plan_start_date=date.today(), onboarding_done=True,
        reading_hizb_current=1, reading_khatmah_count=0,
        listening_hizb_current=1, listening_khatmah_count=0,
        streak_days=0, last_active_date=None, notifications_enabled=True,
    )
    defaults.update(kwargs)
    user = User(**defaults)
    return user


class TestHifzEngine(unittest.IsolatedAsyncioTestCase):
    """اختبارات محرك الحفظ."""

    async def asyncSetUp(self):
        await init_db()

    async def asyncTearDown(self):
        await close_db()

    async def test_user_starts_from_page_1(self):
        """سيناريو 1: مستخدم يبدأ من الوجه 1."""
        user = make_user(last_hifz_page=0, daily_hifz_amount=1)
        a = get_today_hifz_assignment(user)
        self.assertEqual(a["start"], 1)
        self.assertEqual(a["end"], 1)
        self.assertEqual(a["pages"], [1])
        self.assertFalse(a["completed_quran"])

    async def test_user_starts_from_page_40(self):
        """سيناريو 2: مستخدم يبدأ من الوجه 40."""
        user = make_user(last_hifz_page=40, daily_hifz_amount=1)
        a = get_today_hifz_assignment(user)
        self.assertEqual(a["start"], 41)
        self.assertEqual(a["end"], 41)

    async def test_user_starts_from_page_120(self):
        """سيناريو 3: مستخدم يبدأ من الوجه 120."""
        user = make_user(last_hifz_page=120, daily_hifz_amount=1)
        a = get_today_hifz_assignment(user)
        self.assertEqual(a["start"], 121)

    async def test_save_one_page_daily(self):
        """سيناريو 4: حفظ وجه واحد يوميًا."""
        user = make_user(last_hifz_page=40, daily_hifz_amount=1)
        result = confirm_memorization(user)
        self.assertTrue(result["success"])
        self.assertEqual(user.last_hifz_page, 41)
        self.assertEqual(user.next_hifz_page, 42)

    async def test_save_two_pages_daily(self):
        """سيناريو 5: حفظ وجهين يوميًا."""
        user = make_user(last_hifz_page=40, daily_hifz_amount=2)
        a = get_today_hifz_assignment(user)
        self.assertEqual(a["pages"], [41, 42])
        result = confirm_memorization(user)
        self.assertTrue(result["success"])
        self.assertEqual(user.last_hifz_page, 42)
        self.assertEqual(user.next_hifz_page, 43)

    async def test_skip_day_does_not_advance(self):
        """سيناريو 6: تخطي يوم — الوجه المطلوب لا يتغير.
        
        التحقق من القاعدة الحرجة: 'لا تحرّك الحفظ للأمام تلقائيًا'.
        """
        user = make_user(last_hifz_page=40, daily_hifz_amount=1)
        # اليوم الأول: الوجه المطلوب = 41
        a1 = get_today_hifz_assignment(user)
        self.assertEqual(a1["start"], 41)
        # لم يُؤكَّد الإنجاز — في اليوم التالي:
        a2 = get_today_hifz_assignment(user)
        self.assertEqual(a2["start"], 41)  # لا يزال 41!

    async def test_change_daily_amount(self):
        """سيناريو 7: تغيير المقدار اليومي."""
        user = make_user(last_hifz_page=40, daily_hifz_amount=1)
        # تغيير إلى 2 أوجه/يوم
        async with AsyncSessionLocal() as session:
            session.add(user)
            await session.commit()
            await update_settings(session, user, daily_amount=2)
        a = get_today_hifz_assignment(user)
        self.assertEqual(a["pages"], [41, 42])  # الآن يحفظ وجهين

    async def test_complete_page_40_then_move_to_41(self):
        """سيناريو 8: إنهاء الوجه 40 ثم الانتقال إلى 41."""
        user = make_user(last_hifz_page=39, daily_hifz_amount=1)
        a = get_today_hifz_assignment(user)
        self.assertEqual(a["start"], 40)
        confirm_memorization(user)
        self.assertEqual(user.last_hifz_page, 40)
        a2 = get_today_hifz_assignment(user)
        self.assertEqual(a2["start"], 41)


class TestRevisionEngine(unittest.IsolatedAsyncioTestCase):
    """اختبارات محرك المراجعات."""

    async def asyncSetUp(self):
        await init_db()

    async def asyncTearDown(self):
        await close_db()

    async def test_near_review_20_pages(self):
        """سيناريو 9: مراجعة القريب = آخر 20 وجهًا."""
        user = make_user(last_hifz_page=40, daily_hifz_amount=1)
        nr = get_near_review_range(user)
        self.assertTrue(nr["applicable"])
        self.assertEqual(nr["start"], 21)  # 40-19
        self.assertEqual(nr["end"], 40)
        self.assertEqual(nr["count"], 20)

    async def test_near_review_advances_after_new_hifz(self):
        """سيناريو 10: انتقال المراجعة القريبة بعد حفظ وجه جديد."""
        user = make_user(last_hifz_page=40, daily_hifz_amount=1)
        nr1 = get_near_review_range(user)
        self.assertEqual(nr1["end"], 40)
        # حفظ وجه جديد
        confirm_memorization(user)
        nr2 = get_near_review_range(user)
        self.assertEqual(nr2["end"], 41)  # انتقلت
        self.assertEqual(nr2["start"], 22)  # 41-19

    async def test_far_review_40_pages_cycle(self):
        """سيناريو 11: مراجعة البعيد 40 وجهًا.
        
        last=120: 3 دورات (cycle 1 = 81→120, cycle 2 = 41→80, cycle 3 = 1→40).
        """
        async with AsyncSessionLocal() as session:
            user = make_user(last_hifz_page=120, daily_hifz_amount=1)
            session.add(user)
            await session.commit()
            fr = await get_far_review_state(session, user)
        self.assertTrue(fr["applicable"])
        # الدورة 1 = الأحدث: 81→120 (40 وجه)
        self.assertEqual(fr["cycle_start"], 81)
        self.assertEqual(fr["cycle_end"], 120)
        self.assertEqual(fr["current_cycle"], 1)
        self.assertEqual(fr["total_cycles"], 3)  # ceil(120/40) = 3

    async def test_advance_far_review_cycle(self):
        """سيناريو 12: الانتقال من 81→120 إلى 41→80.
        
        مثال المستخدم: 'الدورة الحالية: 80 → 120، بعد إنهائها: 40 → 80'
        (مراعاة أن الأرقام 80/120/40 في المثال هي حدود حدودية غير شاملة،
        لكن منطقياً: 81→120 ثم 41→80)
        """
        async with AsyncSessionLocal() as session:
            user = make_user(last_hifz_page=120, daily_hifz_amount=1)
            session.add(user)
            await session.commit()
            fr1 = await get_far_review_state(session, user)
            self.assertEqual(fr1["cycle_start"], 81)
            # إتمام الدورة 1
            result = await advance_far_review_cycle(session, user)
            self.assertTrue(result["success"])
            fr2 = await get_far_review_state(session, user)
            self.assertEqual(fr2["current_cycle"], 2)
            self.assertEqual(fr2["cycle_start"], 41)
            self.assertEqual(fr2["cycle_end"], 80)

    async def test_far_review_small_pool(self):
        """سيناريو إضافي: محفوظ أقل من 40 وجه.
        
        المحفوظ = 25 → دورة واحدة فقط (1→25)، لا تظهر أوجه غير محفوظة.
        القريب = آخر 20 (6→25).
        """
        async with AsyncSessionLocal() as session:
            user = make_user(last_hifz_page=25, daily_hifz_amount=1)
            session.add(user)
            await session.commit()
            # القريب = 6→25
            nr = get_near_review_range(user)
            self.assertEqual(nr["start"], 6)
            self.assertEqual(nr["end"], 25)
            # البعيد = دورة واحدة = 1→25
            fr = await get_far_review_state(session, user)
            self.assertTrue(fr["applicable"])
            self.assertEqual(fr["total_cycles"], 1)
            self.assertEqual(fr["cycle_start"], 1)
            self.assertEqual(fr["cycle_end"], 25)


class TestReadingEngine(unittest.TestCase):
    """اختبارات محرك القراءة."""

    def test_reading_assignment_2_hizb(self):
        """سيناريو 14: ورد القراءة = حزبان/يوم."""
        user = make_user(reading_hizb_current=21)
        r = get_reading_assignment(user)
        self.assertEqual(r["hizb_list"], [21, 22])
        # الأوجه من 201 إلى 220 (حزبا 21 و 22)
        self.assertEqual(r["pages_start"], 201)
        self.assertEqual(r["pages_end"], 220)

    def test_reading_cycle_after_60(self):
        """سيناريو 14: إعادة دورة القراءة بعد الحزب 60.
        
        القراءة اليومية = حزبان. عندما current=60، قراءة اليوم = 60+1 (التفاف).
        بعد التأكيد، next = 2، ويتم احتساب ختمة كاملة.
        """
        user = make_user(reading_hizb_current=60)
        advance_reading(user)
        # بعد قراءة 60+1، التالي = 2
        self.assertEqual(user.reading_hizb_current, 2)
        self.assertEqual(user.reading_khatmah_count, 1)

    def test_reading_cycle_from_59(self):
        """قراءة اليوم = 59+60، التالي = 1، ختمة كاملة."""
        user = make_user(reading_hizb_current=59)
        advance_reading(user)
        self.assertEqual(user.reading_hizb_current, 1)
        self.assertEqual(user.reading_khatmah_count, 1)

    def test_reading_cycle_info(self):
        """معلومات دورة القراءة."""
        user = make_user(reading_hizb_current=22)
        info = get_reading_cycle_info(user)
        self.assertEqual(info["current_hizb"], 22)
        self.assertEqual(info["completed_in_cycle"], 21)
        self.assertEqual(info["percent"], 35.0)


class TestListeningEngine(unittest.TestCase):
    """اختبارات محرك الاستماع."""

    def test_listening_assignment_1_hizb(self):
        """سيناريو: الاستماع = حزب واحد/يوم."""
        user = make_user(listening_hizb_current=15)
        l = get_listening_assignment(user)
        self.assertEqual(l["hizb"], 15)
        self.assertEqual(l["pages_start"], 141)
        self.assertEqual(l["pages_end"], 150)

    def test_listening_cycle_after_60(self):
        """سيناريو 15: إعادة دورة الاستماع بعد الحزب 60."""
        user = make_user(listening_hizb_current=60)
        advance_listening(user)
        self.assertEqual(user.listening_hizb_current, 1)
        self.assertEqual(user.listening_khatmah_count, 1)

    def test_listening_independent_from_reading(self):
        """الاستماع مستقل تمامًا عن القراءة."""
        user = make_user(reading_hizb_current=20, listening_hizb_current=15)
        advance_reading(user)
        # القراءة انتقلت، الاستماع لم يتأثر
        self.assertEqual(user.reading_hizb_current, 22)  # +2
        self.assertEqual(user.listening_hizb_current, 15)  # لم يتغير
        advance_listening(user)
        self.assertEqual(user.listening_hizb_current, 16)


class TestPrepEngine(unittest.TestCase):
    """اختبارات محرك التحضير."""

    def test_weekly_prep_range(self):
        """سيناريو: التحضير الأسبوعي محسوب ديناميكيًا."""
        user = make_user(last_hifz_page=40, daily_hifz_amount=1, weekly_hifz_amount=7)
        wp = get_weekly_prep_range(user)
        self.assertEqual(wp["start"], 41)
        self.assertEqual(wp["end"], 47)

    def test_weekly_prep_changes_with_daily_amount(self):
        """إذا تغيّر المقدار اليومي، يتغيّر التحضير الأسبوعي."""
        user = make_user(last_hifz_page=40, daily_hifz_amount=2, weekly_hifz_amount=14)
        wp = get_weekly_prep_range(user)
        self.assertEqual(wp["start"], 41)
        self.assertEqual(wp["end"], 54)

    def test_nightly_prep(self):
        """سيناريو: التحضير الليلي = وجه الغد."""
        user = make_user(last_hifz_page=40, daily_hifz_amount=1)
        np_ = get_nightly_prep_pages(user)
        self.assertEqual(np_["pages"], [41])
        self.assertEqual(np_["start"], 41)

    def test_nightly_prep_two_pages(self):
        user = make_user(last_hifz_page=40, daily_hifz_amount=2)
        np_ = get_nightly_prep_pages(user)
        self.assertEqual(np_["pages"], [41, 42])
        self.assertEqual(np_["start"], 41)
        self.assertEqual(np_["end"], 42)

    def test_pre_session_timer(self):
        """مؤقّت التحضير القبلي."""
        user = make_user(last_hifz_page=40, daily_hifz_amount=1)
        self.assertIsNone(user.pre_session_started_at)
        start_pre_session_timer(user)
        self.assertIsNotNone(user.pre_session_started_at)
        minutes = end_pre_session_timer(user)
        self.assertGreaterEqual(minutes, 0)
        self.assertIsNone(user.pre_session_started_at)


class TestTaskService(unittest.IsolatedAsyncioTestCase):
    """اختبارات خدمات المهام."""

    async def asyncSetUp(self):
        await init_db()

    async def asyncTearDown(self):
        await close_db()

    async def test_toggle_task_done(self):
        """تسجيل مهمة ثم التراجع عنها (toggleable)."""
        async with AsyncSessionLocal() as session:
            user = make_user(last_hifz_page=40, daily_hifz_amount=1)
            session.add(user)
            await session.commit()
            progress = DailyProgress(user_id=user.id, progress_date=date.today())
            session.add(progress)
            await session.commit()
            # تسجيل القراءة
            r = await toggle_task(session, user, progress, "reading")
            self.assertTrue(r["success"])
            self.assertEqual(r["action"], "done")
            self.assertTrue(progress.reading_done)
            # التراجع
            r2 = await toggle_task(session, user, progress, "reading")
            self.assertEqual(r2["action"], "undone")
            self.assertFalse(progress.reading_done)

    async def test_streak_first_activity(self):
        """أول نشاط — streak = 1."""
        async with AsyncSessionLocal() as session:
            user = make_user(last_hifz_page=40, daily_hifz_amount=1, streak_days=0, last_active_date=None)
            session.add(user)
            await session.commit()
            await update_streak_on_activity(session, user)
            self.assertEqual(user.streak_days, 1)

    async def test_streak_continuity(self):
        """استمرارية — اليوم بعد الأمس."""
        async with AsyncSessionLocal() as session:
            user = make_user(
                last_hifz_page=40, daily_hifz_amount=1,
                streak_days=3, last_active_date=date.today() - timedelta(days=1),
            )
            session.add(user)
            await session.commit()
            await update_streak_on_activity(session, user)
            self.assertEqual(user.streak_days, 4)

    async def test_streak_break(self):
        """انقطاع — يعود إلى 1."""
        async with AsyncSessionLocal() as session:
            user = make_user(
                last_hifz_page=40, daily_hifz_amount=1,
                streak_days=10, last_active_date=date.today() - timedelta(days=5),
            )
            session.add(user)
            await session.commit()
            await update_streak_on_activity(session, user)
            self.assertEqual(user.streak_days, 1)


class TestUserService(unittest.IsolatedAsyncioTestCase):
    """اختبارات خدمات المستخدم."""

    async def asyncSetUp(self):
        await init_db()

    async def asyncTearDown(self):
        await close_db()

    async def test_set_initial_hifz(self):
        """ضبط نقطة البداية للحفظ."""
        async with AsyncSessionLocal() as session:
            user = make_user(last_hifz_page=0)
            session.add(user)
            await session.commit()
            await set_initial_hifz(session, user, 50)
            self.assertEqual(user.last_hifz_page, 50)
            self.assertEqual(user.next_hifz_page, 51)
            # التحقق من تسجيل الأوجه
            from sqlalchemy import select, func
            count = await session.scalar(
                select(func.count(MemorizationLog.id)).where(MemorizationLog.user_id == user.id)
            )
            self.assertEqual(count, 50)

    async def test_update_settings_recomputes_weekly_prep(self):
        """تغيير المقدار يعيد حساب التحضير الأسبوعي."""
        async with AsyncSessionLocal() as session:
            user = make_user(last_hifz_page=40, daily_hifz_amount=1, weekly_hifz_amount=7)
            session.add(user)
            await session.commit()
            await update_settings(session, user, weekly_amount=14)
            wp = get_weekly_prep_range(user)
            self.assertEqual(wp["end"], 54)  # 41+14-1


class TestMultiUser(unittest.IsolatedAsyncioTestCase):
    """سيناريو 18: تعدد المستخدمين — عزل بيانات كل مستخدم."""

    async def asyncSetUp(self):
        await init_db()

    async def asyncTearDown(self):
        await close_db()

    async def test_two_users_isolated(self):
        """مستخدمان — كل واحد له بياناته المنفصلة."""
        async with AsyncSessionLocal() as session:
            u1 = User(telegram_id=111, last_hifz_page=40, daily_hifz_amount=1, weekly_hifz_amount=7,
                      plan_start_date=date.today(), onboarding_done=True)
            u2 = User(telegram_id=222, last_hifz_page=120, daily_hifz_amount=2, weekly_hifz_amount=14,
                      plan_start_date=date.today(), onboarding_done=True)
            session.add_all([u1, u2])
            await session.commit()

            # u1 يحفظ وجهًا
            confirm_memorization(u1)
            self.assertEqual(u1.last_hifz_page, 41)
            # u2 لم يتأثر
            self.assertEqual(u2.last_hifz_page, 120)

            # u2 يحفظ وجهين
            confirm_memorization(u2)
            self.assertEqual(u2.last_hifz_page, 122)
            # u1 لم يتأثر
            self.assertEqual(u1.last_hifz_page, 41)


class TestPersistence(unittest.IsolatedAsyncioTestCase):
    """سيناريو 16: إعادة تشغيل البوت دون فقدان البيانات."""

    async def asyncSetUp(self):
        await init_db()

    async def asyncTearDown(self):
        await close_db()

    async def test_data_persists_across_sessions(self):
        """البيانات تبقى بعد إغلاق الجلسة."""
        from sqlalchemy import select
        # جلسة 1: إنشاء مستخدم
        async with AsyncSessionLocal() as session:
            user = User(telegram_id=999, last_hifz_page=50, daily_hifz_amount=1, weekly_hifz_amount=7,
                        plan_start_date=date.today(), onboarding_done=True)
            session.add(user)
            await session.commit()

        # جلسة 2: استرجاع المستخدم
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.telegram_id == 999))
            retrieved = result.scalar_one()
            self.assertEqual(retrieved.last_hifz_page, 50)
            self.assertTrue(retrieved.onboarding_done)


class TestEndOfQuran(unittest.IsolatedAsyncioTestCase):
    """سيناريو 13: الوصول إلى نهاية القرآن."""

    async def asyncSetUp(self):
        await init_db()

    async def asyncTearDown(self):
        await close_db()

    async def test_completed_quran(self):
        """المستخدم الذي ختم القرآن."""
        user = make_user(last_hifz_page=config.QURAN_PAGE_COUNT, daily_hifz_amount=1)
        a = get_today_hifz_assignment(user)
        self.assertTrue(a["completed_quran"])
        self.assertEqual(a["pages"], [])

    async def test_save_last_page(self):
        """حفظ آخر وجه في المصحف."""
        user = make_user(last_hifz_page=config.QURAN_PAGE_COUNT - 1, daily_hifz_amount=1)
        result = confirm_memorization(user)
        self.assertTrue(result["success"])
        self.assertEqual(user.last_hifz_page, config.QURAN_PAGE_COUNT)


class TestPostponed(unittest.IsolatedAsyncioTestCase):
    """سيناريو: الأيام الفائتة — لا يتقدّم الحفظ تلقائيًا."""

    async def asyncSetUp(self):
        await init_db()

    async def asyncTearDown(self):
        await close_db()

    async def test_postpone_keeps_state(self):
        """تأجيل اليوم — الحفظ لا يتحرك."""
        user = make_user(last_hifz_page=40, daily_hifz_amount=1)
        # الوجه المطلوب اليوم
        a1 = get_today_hifz_assignment(user)
        self.assertEqual(a1["start"], 41)
        # لم يُنجَز اليوم — في الغد:
        # (لا يوجد "advance automatic" — الوجه لا يزال 41)
        a2 = get_today_hifz_assignment(user)
        self.assertEqual(a2["start"], 41)


def run_all_tests():
    """تشغيل كل الاختبارات."""
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.dirname(__file__), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
