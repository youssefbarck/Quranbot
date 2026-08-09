"""
طبقة قاعدة البيانات: إنشاء المحرك، الجلسات، التهيئة الآمنة.
"""
import logging
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine
)

import config
from models import Base, UserSettings, MIGRATION_STATEMENTS
import config as cfg

logger = logging.getLogger(__name__)

# إزالة المعلمات غير المتوافقة مع asyncpg
_FORBIDDEN_PARAMS = {"sslmode", "channel_binding", "sslrootcert", "sslcert", "sslkey"}


def _strip_forbidden_params(url: str) -> str:
    if not url.startswith("postgresql://"):
        return url
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    for key in _FORBIDDEN_PARAMS:
        query.pop(key, None)
    new_query = urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


def _build_async_url() -> str:
    url = config.DATABASE_URL
    if not url:
        return "sqlite+aiosqlite:///:memory:"  # in-memory
    if url.startswith("postgresql://"):
        url = _strip_forbidden_params(url)
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("file:"):
        return url.replace("file:", "sqlite+aiosqlite:///", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


DB_ASYNC_URL = _build_async_url()

# محرك قاعدة البيانات
# ملاحظة: SQLite في الذاكرة لا يدعم pool_size — نستخدم StaticPool لإبقاء الاتصال واحدًا
_is_sqlite_mem = ":memory:" in DB_ASYNC_URL or DB_ASYNC_URL.endswith("sqlite+aiosqlite://")


def _create_engine():
    """يُنشئ محرك قاعدة بيانات جديد — يُستدعى عند التهيئة وإعادة التهيئة للاختبارات."""
    if _is_sqlite_mem:
        from sqlalchemy.pool import StaticPool
        return create_async_engine(
            DB_ASYNC_URL,
            echo=False,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    return create_async_engine(
        DB_ASYNC_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


# المحرك الافتراضي (يُعاد إنشاؤه عند الطلب في init_db إذا كان مُغلَّلاً)
engine = _create_engine()
_disposed = False

# AsyncSessionLocal المُعاد تصديره — نستخدم دالة بديلة لإعادة التقييم ديناميكيًا
# (لأن الاختبارات تستورده مرة واحدة، ثم تستدعي close_db/init_db بين الاختبارات)
_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class _SessionLocalProxy:
    """وسيط ديناميكي يُعيد توجيه الاستدعاءات إلى أحدث AsyncSessionLocal."""
    def __call__(self, *args, **kwargs):
        return _session_maker(*args, **kwargs)
    def __getattr__(self, name):
        return getattr(_session_maker, name)


# الواجهة العامة (تُحدَّث عند إعادة التهيئة)
AsyncSessionLocal = _SessionLocalProxy()


async def init_db():
    """إنشاء الجداول وتطبيق migrations الآمنة. يعيد إنشاء المحرك إذا كان مُغلقًا."""
    global engine, _session_maker, _disposed
    if _disposed:
        engine = _create_engine()
        _session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        _disposed = False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # تطبيق migrations (لإضافة الأعمدة الجديدة لقواعد قديمة)
        if config.is_postgres():
            for stmt in MIGRATION_STATEMENTS:
                try:
                    await conn.execute(__import__("sqlalchemy").text(stmt))
                except Exception as e:
                    logger.debug(f"migration skip: {e}")
    logger.info("✅ تم تهيئة قاعدة البيانات")


async def close_db():
    global _disposed
    await engine.dispose()
    _disposed = True
    logger.info("✅ تم إغلاق قاعدة البيانات")


async def ensure_default_reminders(user_id: int):
    """تأكد من وجود 8 تذكيرات افتراضية لكل مستخدم."""
    from models import User, UserSettings
    from sqlalchemy import select, delete
    import config as cfg

    async with AsyncSessionLocal() as session:
        # هل توجد تذكيرات أصلاً؟
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        existing = result.scalars().all()
        if existing:
            return  # تذكيرات موجودة بالفعل

        # إنشاء التذكيرات الافتراضية
        for reminder_type, default_time in cfg.DEFAULT_REMINDER_TIMES.items():
            session.add(UserSettings(
                user_id=user_id,
                reminder_type=reminder_type,
                reminder_time=default_time,
                enabled=True,
            ))
        await session.commit()
